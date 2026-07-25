"""
LarzChain testnet demo — run the whole stack locally and eyeball it.

    python3 examples/demo_testnet.py

Starts two P2P nodes (A auto-mines, B syncs), a block explorer, and the airdrop
claim service, then prints the URLs. Ctrl-C to stop.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from larzchain.node import Node
from larzchain.wallet import Wallet
from larzchain import explorer, airdrop
from larzchain.tx import COIN

miner = Wallet()
a = Node(port=9333, miner_address=miner.address)
b = Node(port=9334, miner_address=Wallet().address)
a.start(); b.start()
a.add_peer("127.0.0.1:9334"); b.add_peer("127.0.0.1:9333")

# explorer + airdrop as Larz web apps, on their own ports
def serve(app, port):
    app.run(host="127.0.0.1", port=port)

airdrop.EXPLORER_PORT = 9500
ex = explorer.build_app(a)
ad, _ = airdrop.build_app(a)
threading.Thread(target=serve, args=(ex, 9500), daemon=True).start()
threading.Thread(target=serve, args=(ad, 9600), daemon=True).start()

def mine_loop():
    while True:
        a.mine_one()
        time.sleep(3)
threading.Thread(target=mine_loop, daemon=True).start()

print("""
  LarzChain testnet is live:
    node A (mining)   http://127.0.0.1:9333/info
    node B (syncing)  http://127.0.0.1:9334/info
    block explorer    http://127.0.0.1:9500/
    airdrop claim      http://127.0.0.1:9600/
    miner address     %s

  Ctrl-C to stop.
""" % miner.address)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    a.stop(); b.stop()
