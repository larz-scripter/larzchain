"""
larzchain.cli — the `larzchain` command.

  larzchain wallet-new
  larzchain node    --port 9333 [--peer host:port ...] [--mine] [--address L..]
  larzchain balance --node http://127.0.0.1:9333 --address L..
  larzchain send    --node URL --key <privhex> --to L.. --amount <LARZ>
  larzchain explorer --port 9500 --node-obj (in-process; see demo)
  larzchain version

Run via `python -m larzchain ...`.
"""
import sys
import time
import json
import argparse
import threading
import urllib.request

from . import crypto, consensus as K
from .wallet import Wallet
from .tx import Transaction, COIN
from .node import Node
from . import __version__


def _rpc_get(url, path):
    with urllib.request.urlopen(url + path, timeout=5) as r:
        return json.loads(r.read().decode())


def _rpc_post(url, path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(url + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def cmd_wallet_new(a):
    priv = crypto.gen_privkey()
    addr = crypto.pubkey_to_address(crypto.privkey_to_pubkey(priv))
    print("address:  " + addr)
    print("privkey:  %064x" % priv)
    print("\nKeep the private key secret. Anyone with it controls the coins.")


def cmd_node(a):
    addr = a.address or Wallet().address
    seeds = None
    if a.seeds is not None:
        seeds = [s for s in a.seeds.split(",") if s.strip()]
    node = Node(port=a.port, miner_address=addr, public_url=a.public_url,
                persist_path=a.persist, seeds=seeds, report_url=a.report_url,
                log_path=a.log)
    for p in (a.peer or []):
        node.add_peer(p)
    node.start(background=True, bootstrap=not a.no_bootstrap)
    print("LarzChain node on %s  (miner -> %s)" % (node.url, addr))
    print("  network=%s  genesis=%s" % (node.network_id, node.genesis[:12]))
    if not a.no_bootstrap:
        print("  bootstrapping from seeds: %s" % (", ".join(node.seeds) or "(none)"))
    if a.mine:
        print("auto-mining every ~%ds..." % K.TARGET_BLOCK_TIME)
        def loop():
            while True:
                b = node.mine_one()
                print("mined #%d %s  supply=%.2f LARZ"
                      % (node.chain.height, b.hash[:16],
                         node.chain.total_supply() / COIN))
        threading.Thread(target=loop, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()


def cmd_balance(a):
    print("%s : %.8f LARZ" % (a.address,
          _rpc_get(a.node, "/balance/" + a.address)["balance"] / COIN))


def cmd_send(a):
    priv = int(a.key, 16)
    w = Wallet([priv])
    # pull the chain to build the tx locally
    data = _rpc_get(a.node, "/blocks?from=0")
    from .chain import Blockchain
    from .block import Block
    chain = Blockchain()
    for bd in data["blocks"][1:]:
        chain.add_block(Block.from_dict(bd))
    tx = w.send(chain, a.to, int(round(a.amount * COIN)))
    res = _rpc_post(a.node, "/tx", tx.to_dict())
    print("submitted %s -> %s : %s" % (tx.txid[:16], a.to, res))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(prog="larzchain")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("version")
    sub.add_parser("wallet-new")

    pn = sub.add_parser("node")
    pn.add_argument("--port", type=int, default=9333)
    pn.add_argument("--peer", action="append")
    pn.add_argument("--address")
    pn.add_argument("--mine", action="store_true")
    pn.add_argument("--public-url", help="the URL peers dial back (e.g. https://node.example.com)")
    pn.add_argument("--seeds", help="comma-separated seed node URLs (overrides built-in)")
    pn.add_argument("--persist", help="path to persist the chain + peers")
    pn.add_argument("--report-url", help="opt-in: POST health/errors here (off by default)")
    pn.add_argument("--log", help="also write logs to this file")
    pn.add_argument("--no-bootstrap", action="store_true", help="do not contact seeds on start")


    pb = sub.add_parser("balance")
    pb.add_argument("--node", required=True)
    pb.add_argument("--address", required=True)

    ps = sub.add_parser("send")
    ps.add_argument("--node", required=True)
    ps.add_argument("--key", required=True)
    ps.add_argument("--to", required=True)
    ps.add_argument("--amount", type=float, required=True)

    args = p.parse_args(argv)
    if args.cmd == "version":
        print("larzchain " + __version__)
    elif args.cmd == "wallet-new":
        cmd_wallet_new(args)
    elif args.cmd == "node":
        cmd_node(args)
    elif args.cmd == "balance":
        cmd_balance(args)
    elif args.cmd == "send":
        cmd_send(args)
    else:
        p.print_help()
    return 0
