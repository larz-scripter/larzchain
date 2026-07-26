"""
larzchain.node — a full node: chain + mempool + HTTP/JSON API + P2P network.

Nodes form a self-forming mesh over HTTP/JSON:
  * identity: every peer must share NETWORK_ID *and* the genesis hash
  * bootstrap: contact seed nodes + a published seeds.txt, then peer-exchange
  * handshake: POST /hello advertises a node's public URL (two-way discovery)
  * gossip new blocks/txs; pull-sync the most-work chain (incremental)
  * observability: structured logs, an error ring-buffer, /health /metrics /debug
  * updates: checks a published version.txt and surfaces "update available"
             (never auto-updates); optional opt-in telemetry to a report URL

Pure stdlib (http.server + urllib + logging); thread-safe via a lock.
"""

import os
import json
import time
import logging
import threading
import urllib.request
from collections import deque
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler

from .chain import Blockchain, ValidationError
from .block import Block
from .tx import Transaction
from .miner import assemble_block, mine
from . import consensus as K
from . import __version__
from . import crypto as _crypto

MAX_BODY = 4 * 1024 * 1024          # 4 MB cap on any POST body
RATE_WINDOW = 60                    # seconds
RATE_MAX = 240                      # write requests per IP per window
PEER_BAN_FAILS = 8                  # consecutive failures before a peer is dropped
REORG_BUFFER = 25                   # how far back to re-pull for reorg safety


class Node:
    def __init__(self, host="127.0.0.1", port=K.DEFAULT_PORT, miner_address=None,
                 persist_path=None, faucet_wallet=None, faucet_amount=2500000000,
                 public_url=None, network_id=None, seeds=None, report_url=None,
                 max_peers=32, log_path=None):
        self.host = host
        self.port = port
        self.chain = Blockchain()
        self.mempool = {}                # txid -> Transaction
        self.peers = set()               # full base URLs, e.g. "http://1.2.3.4:9333"
        self._peer_fails = {}            # peer -> consecutive failures
        self.miner_address = miner_address
        self.lock = threading.RLock()
        self._httpd = None
        self._stop = False
        self.persist_path = persist_path
        self.peers_path = (persist_path + ".peers") if persist_path else None
        self.faucet_wallet = faucet_wallet
        self.faucet_amount = faucet_amount
        self._faucet_seen = {}
        # networking identity
        self.network_id = network_id or K.NETWORK_ID
        self.protocol_version = K.PROTOCOL_VERSION
        self.public_url = public_url.rstrip("/") if public_url else None
        self.seeds = list(seeds) if seeds is not None else list(K.SEED_NODES)
        self.max_peers = max_peers
        self.report_url = report_url.rstrip("/") if report_url else None
        # observability
        self.started_at = time.time()
        self.errors = deque(maxlen=200)          # recent {t, where, msg}
        self.stats = dict(blocks_recv=0, blocks_mined=0, txs_recv=0, hello_in=0,
                          hello_out=0, gossip_out=0, sync_ok=0, sync_fail=0,
                          rejected_net=0, rate_limited=0, oversized=0, errors=0)
        self.update_available = None             # newer version string, if any
        self.peer_versions = {}                  # peer -> reported version
        self.log = self._make_logger(log_path)
        self.genesis = self.chain.blocks[0].hash
        # rate limiting / bans
        self._hits = {}                          # ip -> deque[timestamps]
        self.banned = set()
        if persist_path:
            self._load()
        if self.peers_path:
            self._load_peers()

    # -- observability helpers -------------------------------------------- #
    def _make_logger(self, log_path):
        lg = logging.getLogger("larzchain.node.%d" % self.port)
        lg.setLevel(logging.INFO)
        if not lg.handlers:
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            lg.addHandler(sh)
            if log_path:
                try:
                    fh = logging.FileHandler(log_path)
                    fh.setFormatter(fmt)
                    lg.addHandler(fh)
                except Exception:
                    pass
        return lg

    def _err(self, where, exc):
        self.stats["errors"] += 1
        msg = "%s: %s" % (type(exc).__name__, exc)
        self.errors.append({"t": time.time(), "where": where, "msg": msg})
        self.log.warning("[%s] %s", where, msg)

    def _bump(self, key, n=1):
        self.stats[key] = self.stats.get(key, 0) + n

    # -- faucet ------------------------------------------------------------ #
    def faucet_send(self, address):
        if not self.faucet_wallet:
            return {"error": "faucet disabled"}
        now = time.time()
        with self.lock:
            last = self._faucet_seen.get(address, 0)
            if now - last < 3600:
                return {"error": "rate limited", "retry_after": int(3600 - (now - last))}
            try:
                tx = self.faucet_wallet.send(self.chain, address, self.faucet_amount)
            except ValueError as e:
                return {"error": "faucet empty: %s" % e}
            self._faucet_seen[address] = now
        if self.submit_tx(tx):
            return {"sent": self.faucet_amount, "txid": tx.txid, "address": address}
        return {"error": "not accepted (faucet utxos may be unconfirmed)"}

    # -- persistence ------------------------------------------------------- #
    def _load(self):
        if not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path) as f:
                blocks = json.load(f)
            for bd in blocks:
                try:
                    self.chain.add_block(Block.from_dict(bd))
                except Exception:
                    pass
        except Exception as e:
            self._err("load_chain", e)

    def _save(self):
        if not self.persist_path:
            return
        import tempfile
        try:
            data = [b.to_dict() for b in self.chain.blocks[1:]]
            d = os.path.dirname(self.persist_path) or "."
            fd, tmp = tempfile.mkstemp(dir=d)
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.persist_path)
        except Exception as e:
            self._err("save_chain", e)

    def _load_peers(self):
        try:
            if os.path.exists(self.peers_path):
                with open(self.peers_path) as f:
                    for p in json.load(f):
                        self.add_peer(p)
        except Exception as e:
            self._err("load_peers", e)

    def _save_peers(self):
        if not self.peers_path:
            return
        import tempfile
        try:
            d = os.path.dirname(self.peers_path) or "."
            fd, tmp = tempfile.mkstemp(dir=d)
            with os.fdopen(fd, "w") as f:
                json.dump(sorted(self.peers), f)
            os.replace(tmp, self.peers_path)
        except Exception as e:
            self._err("save_peers", e)

    @property
    def url(self):
        return self.public_url or ("http://%s:%d" % (self.host, self.port))

    # -- peer helpers ------------------------------------------------------ #
    @staticmethod
    def _norm(peer):
        if not peer:
            return None
        peer = peer.strip().rstrip("/")
        if "://" not in peer:
            peer = "http://" + peer
        return peer

    def add_peer(self, peer):
        peer = self._norm(peer)
        if not peer or peer == self.url or peer in self.banned:
            return
        with self.lock:
            if peer not in self.peers and len(self.peers) < self.max_peers:
                self.peers.add(peer)

    def _drop_peer(self, peer):
        with self.lock:
            self.peers.discard(peer)
            self._peer_fails.pop(peer, None)

    def _peer_ok(self, peer):
        self._peer_fails[peer] = 0

    def _peer_bad(self, peer):
        n = self._peer_fails.get(peer, 0) + 1
        self._peer_fails[peer] = n
        if n >= PEER_BAN_FAILS:
            self._drop_peer(peer)

    _UA = "larzchain/%s" % __version__

    def _get(self, peer, path):
        req = urllib.request.Request(peer + path, headers={"User-Agent": self._UA})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())

    def _post(self, peer, path, obj):
        data = json.dumps(obj).encode()
        req = urllib.request.Request(peer + path, data=data,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": self._UA})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())

    # -- network envelope (identity check) -------------------------------- #
    def _envelope(self, data):
        return {"network_id": self.network_id, "genesis": self.genesis,
                "version": self.protocol_version, "data": data}

    def _same_network(self, obj):
        """True if an incoming envelope is on our network+genesis (or is legacy
        with no envelope — lenient for backward compat on read-only gossip)."""
        if not isinstance(obj, dict) or "network_id" not in obj:
            return True, obj
        if obj.get("network_id") != self.network_id or obj.get("genesis") != self.genesis:
            self._bump("rejected_net")
            return False, None
        return True, obj.get("data", {})

    # -- handshake + bootstrap -------------------------------------------- #
    def hello(self, peer):
        """Introduce ourselves to a peer; learn its peers. Returns True on success."""
        peer = self._norm(peer)
        if not peer or peer == self.url:
            return False
        try:
            payload = {"network_id": self.network_id, "genesis": self.genesis,
                       "version": self.protocol_version, "public_url": self.url,
                       "height": self.chain.height}
            resp = self._post(peer, "/hello", payload)
            self._bump("hello_out")
            if resp.get("network_id") != self.network_id or resp.get("genesis") != self.genesis:
                self._bump("rejected_net")
                return False
            self.add_peer(peer)
            self._peer_ok(peer)
            if resp.get("version"):
                self.peer_versions[peer] = resp["version"]
            for p in resp.get("peers", []):
                self.add_peer(p)
            return True
        except Exception as e:
            self._err("hello", e)
            self._peer_bad(peer)
            return False

    def bootstrap(self):
        """Find the network: persisted peers + seeds.txt + built-in seeds, then
        handshake with each."""
        candidates = list(self.peers) + list(self.seeds)
        # fetch the published seed list (best-effort)
        try:
            with urllib.request.urlopen(urllib.request.Request(K.SEEDS_URL, headers={"User-Agent": self._UA}), timeout=5) as r:
                for line in r.read().decode().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        candidates.append(line)
        except Exception as e:
            self._err("fetch_seeds", e)
        seen, connected = set(), 0
        for c in candidates:
            c = self._norm(c)
            if not c or c in seen or c == self.url:
                continue
            seen.add(c)
            if self.hello(c):
                connected += 1
        self.log.info("bootstrap: %d peers connected (from %d candidates)",
                      connected, len(seen))
        self._save_peers()
        return connected

    # -- core operations --------------------------------------------------- #
    def submit_tx(self, tx, gossip=True):
        with self.lock:
            if tx.txid in self.mempool:
                return False
            try:
                self.chain._validate_tx(tx, self.chain.utxos, set())
            except ValidationError:
                return False
            self.mempool[tx.txid] = tx
        self._bump("txs_recv")
        if gossip:
            self._gossip("/tx", tx.to_dict())
        return True

    def receive_block(self, block, gossip=True):
        with self.lock:
            try:
                added = self.chain.add_block(block)
            except ValidationError:
                return False
            if added:
                for tx in block.transactions:
                    self.mempool.pop(tx.txid, None)
                self._save()
        if added:
            self._bump("blocks_recv")
            self.genesis = self.chain.blocks[0].hash
            if gossip:
                self._gossip("/block", block.to_dict())
        return added

    def mine_one(self, note=""):
        with self.lock:
            txs = list(self.mempool.values())
            blk = assemble_block(self.chain, self.miner_address, txs,
                                 timestamp=int(time.time()), note=note)
        mine(blk)
        self.receive_block(blk)
        self._bump("blocks_mined")
        return blk

    # -- gossip + sync ----------------------------------------------------- #
    def _gossip(self, path, obj):
        for peer in list(self.peers):
            try:
                self._post(peer, path, self._envelope(obj))
                self._bump("gossip_out")
                self._peer_ok(peer)
            except Exception:
                self._peer_bad(peer)

    def sync_once(self):
        for peer in list(self.peers):
            try:
                info = self._get(peer, "/info")
                self._peer_ok(peer)
                self._bump("sync_ok")
            except Exception:
                self._peer_bad(peer)
                self._bump("sync_fail")
                continue
            if info.get("network_id") not in (None, self.network_id):
                continue
            if info.get("version"):
                self.peer_versions[peer] = info["version"]
            for p in info.get("peers", []):
                self.add_peer(p)
            try:
                if info["work"] > self.chain.work[self.chain.tip.hash]:
                    self._pull_blocks(peer)
            except Exception as e:
                self._err("sync_compare", e)

    def _pull_blocks(self, peer):
        frm = max(0, self.chain.height - REORG_BUFFER)
        try:
            data = self._get(peer, "/blocks?from=%d" % frm)
        except Exception:
            self._peer_bad(peer)
            return
        for bd in data.get("blocks", []):
            try:
                self.receive_block(Block.from_dict(bd), gossip=False)
            except Exception:
                pass

    def _version_check(self):
        try:
            with urllib.request.urlopen(urllib.request.Request(K.VERSION_URL, headers={"User-Agent": self._UA}), timeout=5) as r:
                latest = r.read().decode().strip().split()[0]
            if latest and latest != __version__ and self._newer(latest, __version__):
                if self.update_available != latest:
                    self.log.warning("update available: %s (running %s)", latest, __version__)
                self.update_available = latest
        except Exception:
            pass

    @staticmethod
    def _newer(a, b):
        def parse(v):
            return [int(x) for x in v.split(".") if x.isdigit()]
        try:
            return parse(a) > parse(b)
        except Exception:
            return False

    def _sync_loop(self, interval):
        ticks = 0
        while not self._stop:
            try:
                self.sync_once()
                if not self.peers:                    # lost the network -> re-seed
                    self.bootstrap()
                ticks += 1
                if ticks % 30 == 0:                   # ~every 30 cycles
                    self._version_check()
                    self._save_peers()
            except Exception as e:
                self._err("sync_loop", e)
            time.sleep(interval)

    def _report_loop(self, interval=60):
        """Opt-in telemetry: POST a health summary to report_url. Off unless the
        operator sets --report-url. Keeps the 'no phone-home by default' promise."""
        while not self._stop and self.report_url:
            try:
                self._post(self.report_url, "/report", {
                    "url": self.url, "health": self.health(),
                    "recent_errors": list(self.errors)[-10:]})
            except Exception:
                pass
            time.sleep(interval)

    # -- introspection ----------------------------------------------------- #
    def info(self):
        with self.lock:
            tip = self.chain.tip
            return {"network_id": self.network_id, "genesis": self.genesis,
                    "version": __version__, "protocol": self.protocol_version,
                    "height": self.chain.height, "tip": tip.hash,
                    "work": self.chain.work[tip.hash],
                    "supply": self.chain.total_supply(),
                    "mempool": len(self.mempool),
                    "peers": list(self.peers), "url": self.url, "backend": _crypto.backend(),
                    "update_available": self.update_available}

    def health(self):
        return {"ok": True, "version": __version__, "network_id": self.network_id,
                "height": self.chain.height, "peers": len(self.peers),
                "mempool": len(self.mempool), "uptime_s": int(time.time() - self.started_at),
                "errors": self.stats["errors"], "backend": _crypto.backend(),
                "update_available": self.update_available}

    def debug(self):
        return {"stats": dict(self.stats), "peers": sorted(self.peers),
                "peer_fails": self._peer_fails, "peer_versions": self.peer_versions,
                "banned": sorted(self.banned),
                "recent_errors": list(self.errors)[-50:]}

    def metrics_text(self):
        """Prometheus-style exposition so operators can scrape with standard tools."""
        h = self.health()
        lines = [
            "# HELP larzchain_height Current chain height",
            "larzchain_height %d" % h["height"],
            "larzchain_peers %d" % h["peers"],
            "larzchain_mempool %d" % h["mempool"],
            "larzchain_uptime_seconds %d" % h["uptime_s"],
            "larzchain_update_available %d" % (1 if h["update_available"] else 0),
        ]
        for k, v in self.stats.items():
            lines.append("larzchain_%s_total %d" % (k, v))
        return "\n".join(lines) + "\n"

    # -- rate limiting ----------------------------------------------------- #
    def _rate_ok(self, ip):
        if ip in self.banned:
            return False
        now = time.time()
        dq = self._hits.setdefault(ip, deque())
        while dq and now - dq[0] > RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_MAX:
            self._bump("rate_limited")
            return False
        dq.append(now)
        return True

    # -- server ------------------------------------------------------------ #
    def start(self, sync_interval=2, background=True, bootstrap=True):
        node = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                body = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type",
                                 "text/plain" if isinstance(obj, str) else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except Exception:
                    pass

            def do_GET(self):
                path = self.path
                try:
                    if path.startswith("/health"):
                        return self._send(200, node.health())
                    if path.startswith("/metrics"):
                        return self._send(200, node.metrics_text())
                    if path.startswith("/debug"):
                        return self._send(200, node.debug())
                    if path.startswith("/info"):
                        return self._send(200, node.info())
                    if path.startswith("/height"):
                        return self._send(200, {"height": node.chain.height})
                    if path.startswith("/peers"):
                        return self._send(200, {"peers": list(node.peers)})
                    if path.startswith("/blocks"):
                        frm = 0
                        if "from=" in path:
                            try: frm = int(path.split("from=")[1].split("&")[0])
                            except ValueError: frm = 0
                        with node.lock:
                            blocks = [b.to_dict() for b in node.chain.blocks[frm:]]
                        return self._send(200, {"blocks": blocks})
                    if path.startswith("/headers"):
                        frm = 0
                        if "from=" in path:
                            try: frm = int(path.split("from=")[1].split("&")[0])
                            except ValueError: frm = 0
                        with node.lock:
                            hdrs = [{"height": i, "hash": b.hash,
                                     "prev": b.header.prev_hash, "time": b.header.timestamp}
                                    for i, b in enumerate(node.chain.blocks) if i >= frm]
                        return self._send(200, {"headers": hdrs})
                    if path.startswith("/block/"):
                        b = node.chain.get_block(path.split("/block/")[1])
                        return self._send(200 if b else 404,
                                          b.to_dict() if b else {"error": "not found"})
                    if path.startswith("/balance/"):
                        addr = path.split("/balance/")[1]
                        return self._send(200, {"address": addr,
                                                "balance": node.chain.balance(addr)})
                    if path.startswith("/utxos/"):
                        addr = path.split("/utxos/")[1]
                        with node.lock:
                            utxos = [{"txid": op[0], "index": op[1], "amount": o.amount}
                                     for op, o in node.chain.utxos_for(addr)]
                        return self._send(200, {"address": addr, "utxos": utxos,
                                                "balance": sum(u["amount"] for u in utxos)})
                    if path.startswith("/history/"):
                        addr = path.split("/history/")[1].split("?")[0]
                        hist = []
                        with node.lock:
                            for h, b in enumerate(node.chain.blocks):
                                for tx in b.transactions:
                                    recv = sum(o.amount for o in tx.outputs if o.address == addr)
                                    if recv:
                                        hist.append({"txid": tx.txid, "height": h,
                                                     "amount": recv, "type": "receive",
                                                     "time": b.header.timestamp,
                                                     "coinbase": tx.is_coinbase})
                        return self._send(200, {"address": addr, "history": hist[-50:][::-1]})
                    if path.startswith("/mempool"):
                        return self._send(200, {"txs": [t.to_dict() for t in node.mempool.values()]})
                    if path.startswith("/faucet/"):
                        addr = path.split("/faucet/")[1].split("?")[0]
                        return self._send(200, node.faucet_send(addr))
                    return self._send(404, {"error": "unknown path"})
                except Exception as e:
                    node._err("GET " + path.split("?")[0], e)
                    return self._send(500, {"error": "internal"})

            def do_POST(self):
                ip = self.client_address[0]
                if not node._rate_ok(ip):
                    return self._send(429, {"error": "rate limited"})
                try:
                    n = int(self.headers.get("Content-Length", 0))
                except ValueError:
                    n = 0
                if n > MAX_BODY:
                    node._bump("oversized")
                    return self._send(413, {"error": "body too large"})
                try:
                    body = json.loads(self.rfile.read(n).decode()) if n else {}
                except Exception:
                    return self._send(400, {"error": "bad json"})
                try:
                    if self.path.startswith("/hello"):
                        if (body.get("network_id") != node.network_id
                                or body.get("genesis") != node.genesis):
                            node._bump("rejected_net")
                            return self._send(409, {"error": "network mismatch",
                                                    "network_id": node.network_id,
                                                    "genesis": node.genesis})
                        node._bump("hello_in")
                        pu = body.get("public_url")
                        if pu:
                            node.add_peer(pu)
                            if body.get("version"):
                                node.peer_versions[node._norm(pu)] = body["version"]
                        import random
                        sample = list(node.peers)
                        random.shuffle(sample)
                        return self._send(200, {"network_id": node.network_id,
                                                "genesis": node.genesis,
                                                "version": __version__,
                                                "protocol": node.protocol_version,
                                                "height": node.chain.height,
                                                "url": node.url, "peers": sample[:16]})
                    if self.path.startswith("/report"):
                        return self._send(200, {"ok": True})   # collector override
                    if self.path.startswith("/tx"):
                        ok, data = node._same_network(body)
                        if not ok:
                            return self._send(409, {"error": "network mismatch"})
                        accepted = node.submit_tx(Transaction.from_dict(data))
                        return self._send(200, {"accepted": accepted})
                    if self.path.startswith("/block"):
                        ok, data = node._same_network(body)
                        if not ok:
                            return self._send(409, {"error": "network mismatch"})
                        accepted = node.receive_block(Block.from_dict(data))
                        return self._send(200, {"accepted": accepted})
                    if self.path.startswith("/peers"):
                        node.add_peer(body.get("peer"))
                        return self._send(200, {"peers": list(node.peers)})
                    return self._send(404, {"error": "unknown path"})
                except Exception as e:
                    node._err("POST " + self.path.split("?")[0], e)
                    return self._send(500, {"error": "internal"})

        class Server(ThreadingMixIn, HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self._httpd = Server((self.host, self.port), Handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._sync_loop, args=(sync_interval,), daemon=True).start()
        if self.report_url:
            threading.Thread(target=self._report_loop, daemon=True).start()
        self.log.info("node up at %s (network=%s genesis=%s crypto=%s)",
                      self.url, self.network_id, self.genesis[:12], _crypto.backend())
        if bootstrap and (self.seeds or self.peers):
            threading.Thread(target=self.bootstrap, daemon=True).start()
        if not background:
            try:
                while not self._stop:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        return self

    def stop(self):
        self._stop = True
        self._save_peers()
        if self._httpd:
            self._httpd.shutdown()
