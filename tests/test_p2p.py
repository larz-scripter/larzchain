"""
LarzChain P2P test — 3 real nodes over HTTP, converging on one chain, plus a
reorg. Runs locally on loopback ports. `python3 tests/test_p2p.py`.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from larzchain.node import Node
from larzchain.wallet import Wallet

PASS = [0]; FAIL = [0]
def check(name, cond):
    if cond: PASS[0] += 1; print("  ok   " + name)
    else:    FAIL[0] += 1; print("  FAIL " + name)

def wait_until(fn, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if fn():
            return True
        time.sleep(0.4)
    return False


def main():
    w = Wallet()
    a = Node(port=9401, miner_address=w.address)
    b = Node(port=9402, miner_address=w.address)
    c = Node(port=9403, miner_address=w.address)
    for n in (a, b, c):
        n.start(sync_interval=1)
    # wire a mesh
    a.add_peer("127.0.0.1:9402"); a.add_peer("127.0.0.1:9403")
    b.add_peer("127.0.0.1:9401"); b.add_peer("127.0.0.1:9403")
    c.add_peer("127.0.0.1:9401"); c.add_peer("127.0.0.1:9402")

    try:
        # node A mines 4 blocks; B and C should sync to the same tip
        for _ in range(4):
            a.mine_one()
        check("A at height 4", a.chain.height == 4)
        ok = wait_until(lambda: b.chain.height == 4 and c.chain.height == 4)
        check("B and C synced to height 4", ok)
        check("all three share the same tip",
              a.chain.tip.hash == b.chain.tip.hash == c.chain.tip.hash)

        # a transaction gossips: A sends to a new address, B should see tip advance
        recipient = Wallet().address
        tx = w.send(a.chain, recipient, 5 * 100_000_000)
        a.submit_tx(tx)
        ok = wait_until(lambda: tx.txid in b.mempool or tx.txid in c.mempool)
        check("transaction gossiped to peers", ok)
        a.mine_one()
        ok = wait_until(lambda: b.chain.balance(recipient) == 5 * 100_000_000)
        check("payment confirmed across the network", ok)

        # reorg: C mines two blocks in isolation (peers cleared), builds more work,
        # then rejoins — A and B must reorg onto C's heavier chain.
        h0 = a.chain.height
        c.peers.clear()
        for _ in range(3):
            c.mine_one()
        check("C built a longer isolated chain", c.chain.height == h0 + 3)
        # meanwhile A mines just one
        a.peers.discard("127.0.0.1:9403")
        b.peers.discard("127.0.0.1:9403")
        a.mine_one()
        # reconnect C
        c.add_peer("127.0.0.1:9401"); c.add_peer("127.0.0.1:9402")
        a.add_peer("127.0.0.1:9403"); b.add_peer("127.0.0.1:9403")
        # drive convergence deterministically instead of waiting on the 1s loop
        ok = False
        for _ in range(120):
            for n in (a, b, c):
                n.sync_once()
            if a.chain.tip.hash == c.chain.tip.hash == b.chain.tip.hash:
                ok = True
                break
            time.sleep(0.25)
        check("A and B reorged onto C's heavier chain", ok)
    finally:
        for n in (a, b, c):
            n.stop()

    print("\n  %d passed, %d failed" % (PASS[0], FAIL[0]))
    return 1 if FAIL[0] else 0


if __name__ == "__main__":
    sys.exit(main())
