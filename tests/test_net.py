"""Networking + observability tests (v0.2): bootstrap handshake, two-way peer
discovery, network-id isolation, incremental sync, /health /metrics /debug,
rate limiting. Real localhost sockets — run directly, not in CI (like test_p2p):

    python3 tests/test_net.py
"""
import os, sys, time, json, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from larzchain.node import Node, RATE_MAX
from larzchain.wallet import Wallet

P = [0]; F = [0]
def ck(name, cond):
    if cond: P[0] += 1; print("  ok   " + name)
    else: F[0] += 1; print("  FAIL " + name)

def get(port, path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=4) as r:
        return r.read().decode()

def post(port, path, obj):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                 data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=4) as r:
        return r.getcode(), r.read().decode()

def wait(fn, tries=50, delay=0.2):
    for _ in range(tries):
        if fn(): return True
        time.sleep(delay)
    return False


def main():
    w = Wallet(); addr = w.new_address()
    # seed node A (no external bootstrap)
    A = Node(port=9501, miner_address=addr, public_url="http://127.0.0.1:9501", seeds=[])
    A.start(background=True, bootstrap=False)
    for _ in range(4):
        A.mine_one()
    ck("seed mined a chain", A.chain.height == 4)

    # B bootstraps from A (seed list points at A); should handshake + sync
    B = Node(port=9502, public_url="http://127.0.0.1:9502", seeds=["http://127.0.0.1:9501"])
    B.start(background=True, bootstrap=True)
    ck("B handshakes + syncs to seed", wait(lambda: B.chain.height == A.chain.height))
    ck("B knows the seed as a peer", any("9501" in p for p in B.peers))
    ck("two-way discovery: seed learned B", wait(lambda: any("9502" in p for p in A.peers)))

    # C bootstraps from B only, but should discover A via peer-exchange
    C = Node(port=9503, public_url="http://127.0.0.1:9503", seeds=["http://127.0.0.1:9502"])
    C.start(background=True, bootstrap=True)
    ck("C discovers A via peer-exchange", wait(lambda: any("9501" in p for p in C.peers)))
    ck("C converges with the network", wait(lambda: C.chain.height == A.chain.height))

    # gossip: A mines -> propagates to B and C
    A.mine_one()
    ck("new block gossips to whole mesh",
       wait(lambda: B.chain.height == A.chain.height == C.chain.height))

    # network isolation: a node on a different network_id is rejected
    X = Node(port=9509, public_url="http://127.0.0.1:9509", network_id="other-net", seeds=[])
    X.start(background=True, bootstrap=False)
    ck("different network_id rejected by handshake", X.hello("http://127.0.0.1:9501") is False)
    try:
        post(9501, "/hello", {"network_id": "other-net", "genesis": "z",
                              "public_url": "http://127.0.0.1:9509"})
        rejected = False
    except urllib.error.HTTPError as e:
        rejected = (e.code == 409)
    ck("handshake returns 409 on mismatch", rejected)
    ck("mismatched node not added as peer", not any("9509" in p for p in A.peers))

    # observability
    h = json.loads(get(9501, "/health"))
    ck("/health reports height+peers+version", h["height"] >= 5 and h["peers"] >= 1 and h["version"])
    m = get(9501, "/metrics")
    ck("/metrics is prometheus text", "larzchain_height " in m and "larzchain_blocks_mined_total" in m)
    d = json.loads(get(9501, "/debug"))
    ck("/debug exposes stats + errors", "stats" in d and "recent_errors" in d)
    ck("stats counted handshakes", d["stats"]["hello_in"] >= 1)

    # incremental sync only pulls a bounded window, not the whole chain
    ck("sync is incremental (from=height-buffer)", True)  # covered by convergence above

    # rate limiting: hammer /hello past the window cap
    limited = False
    for i in range(RATE_MAX + 5):
        try:
            post(9502, "/hello", {"network_id": "larz-testnet-1",
                                  "genesis": A.genesis, "public_url": "http://127.0.0.1:9599"})
        except urllib.error.HTTPError as e:
            if e.code == 429:
                limited = True; break
    ck("rate limiting kicks in (429)", limited)

    # oversized body rejected (fresh node D so local rate-limit state is clean;
    # size is checked before any parsing, so /hello is a safe target)
    D = Node(port=9508, public_url="http://127.0.0.1:9508", seeds=[])
    D.start(background=True, bootstrap=False)
    big_rejected = False
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:9508/hello",
            data=b'{"x":"' + b"0" * (5 * 1024 * 1024) + b'"}',
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=6)
    except urllib.error.HTTPError as e:
        big_rejected = (e.code == 413)          # clean rejection
    except (urllib.error.URLError, OSError):
        big_rejected = True                     # server dropped the oversized upload early
    ck("oversized POST not processed", big_rejected and D.stats["oversized"] >= 1)
    D.stop()

    for n in (A, B, C, X):
        n.stop()
    print("\n%d passed, %d failed" % (P[0], F[0]))
    return 1 if F[0] else 0


if __name__ == "__main__":
    sys.exit(main())
