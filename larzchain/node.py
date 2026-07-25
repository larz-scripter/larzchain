"""
larzchain.node — a full node: chain + mempool + HTTP/JSON API + P2P sync.

Peers gossip new blocks and transactions, and every node pull-syncs from its
peers (asks their height, fetches missing blocks) so the network converges on
the most-work chain. Pure stdlib (http.server + urllib); thread-safe via a lock.
"""

import json
import time
import threading
import urllib.request
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler

from .chain import Blockchain, ValidationError
from .block import Block
from .tx import Transaction
from .miner import assemble_block, mine
from . import consensus as K


class Node:
    def __init__(self, host="127.0.0.1", port=9333, miner_address=None):
        self.host = host
        self.port = port
        self.chain = Blockchain()
        self.mempool = {}                # txid -> Transaction
        self.peers = set()               # "host:port"
        self.miner_address = miner_address
        self.lock = threading.RLock()
        self._httpd = None
        self._stop = False

    @property
    def url(self):
        return "http://%s:%d" % (self.host, self.port)

    # -- peer helpers ------------------------------------------------------ #
    def add_peer(self, peer):
        if peer and peer != "%s:%d" % (self.host, self.port):
            self.peers.add(peer)

    def _get(self, peer, path):
        with urllib.request.urlopen("http://%s%s" % (peer, path), timeout=4) as r:
            return json.loads(r.read().decode())

    def _post(self, peer, path, obj):
        data = json.dumps(obj).encode()
        req = urllib.request.Request("http://%s%s" % (peer, path), data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.loads(r.read().decode())

    # -- core operations --------------------------------------------------- #
    def submit_tx(self, tx, gossip=True):
        with self.lock:
            if tx.txid in self.mempool:
                return False
            # light check: inputs exist & signed against current UTXO set
            try:
                self.chain._validate_tx(tx, self.chain.utxos, set())
            except ValidationError:
                return False
            self.mempool[tx.txid] = tx
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
        if added and gossip:
            self._gossip("/block", block.to_dict())
        return added

    def mine_one(self, note=""):
        with self.lock:
            txs = list(self.mempool.values())
            blk = assemble_block(self.chain, self.miner_address, txs,
                                 timestamp=int(time.time()), note=note)
        mine(blk)                                    # PoW outside the lock
        self.receive_block(blk)
        return blk

    # -- gossip + sync ----------------------------------------------------- #
    def _gossip(self, path, obj):
        for peer in list(self.peers):
            try:
                self._post(peer, path, obj)
            except Exception:
                pass

    def sync_once(self):
        for peer in list(self.peers):
            try:
                info = self._get(peer, "/info")
            except Exception:
                continue
            for p in info.get("peers", []):          # peer exchange
                self.add_peer(p)
            if info["work"] > self.chain.work[self.chain.tip.hash]:
                self._pull_blocks(peer)

    def _pull_blocks(self, peer):
        try:
            data = self._get(peer, "/blocks?from=0")
        except Exception:
            return
        for bd in data["blocks"]:
            try:
                self.receive_block(Block.from_dict(bd), gossip=False)
            except Exception:
                pass

    def _sync_loop(self, interval):
        while not self._stop:
            try:
                self.sync_once()
            except Exception:
                pass
            time.sleep(interval)

    # -- server ------------------------------------------------------------ #
    def info(self):
        with self.lock:
            tip = self.chain.tip
            return {"height": self.chain.height, "tip": tip.hash,
                    "work": self.chain.work[tip.hash],
                    "supply": self.chain.total_supply(),
                    "mempool": len(self.mempool),
                    "peers": list(self.peers),
                    "url": self.url}

    def start(self, sync_interval=2, background=True):
        node = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):            # quiet
                pass

            def _send(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path
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
                return self._send(404, {"error": "unknown path"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n).decode()) if n else {}
                if self.path.startswith("/tx"):
                    ok = node.submit_tx(Transaction.from_dict(body))
                    return self._send(200, {"accepted": ok})
                if self.path.startswith("/block"):
                    ok = node.receive_block(Block.from_dict(body))
                    return self._send(200, {"accepted": ok})
                if self.path.startswith("/peers"):
                    node.add_peer(body.get("peer"))
                    return self._send(200, {"peers": list(node.peers)})
                return self._send(404, {"error": "unknown path"})

        class Server(ThreadingMixIn, HTTPServer):
            daemon_threads = True

        self._httpd = Server((self.host, self.port), Handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._sync_loop, args=(sync_interval,),
                         daemon=True).start()
        if not background:
            try:
                while not self._stop:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        return self

    def stop(self):
        self._stop = True
        if self._httpd:
            self._httpd.shutdown()
