"""
Airdrop + explorer test: fund the on-chain pool by mining, then claim a welcome
grant through the Larz-framework airdrop app, and confirm it on-chain.
"""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from larzchain.node import Node
from larzchain import consensus as K, airdrop, explorer
from larzchain.wallet import Wallet
from larzchain.tx import COIN

PASS = [0]; FAIL = [0]
def check(name, cond):
    if cond: PASS[0] += 1; print("  ok   " + name)
    else:    FAIL[0] += 1; print("  FAIL " + name)


class Client:
    """Tiny in-process WSGI client with cookie persistence."""
    def __init__(self, app): self.app = app; self.cookie = None
    def req(self, method, path, form=None):
        body = b""
        if form is not None:
            from urllib.parse import urlencode
            body = urlencode(form).encode()
        env = {"REQUEST_METHOD": method, "PATH_INFO": path.split("?")[0],
               "QUERY_STRING": path.split("?")[1] if "?" in path else "",
               "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
               "HTTP_USER_AGENT": "Mozilla/5.0", "REMOTE_ADDR": "127.0.0.1",
               "CONTENT_TYPE": "application/x-www-form-urlencoded"}
        if self.cookie: env["HTTP_COOKIE"] = self.cookie
        sh = {}
        def sr(s, h): sh["c"] = int(s.split()[0]); sh["h"] = h
        raw = b"".join(self.app(env, sr))
        for k, v in sh["h"]:
            if k == "Set-Cookie": self.cookie = v.split(";")[0]
        return sh["c"], raw.decode("utf-8", "replace")


def main():
    node = Node(port=9600, miner_address=Wallet().address)
    # mine enough to fund a 100 LARZ grant (pool gets 5 LARZ/block -> need >=20)
    for _ in range(25):
        node.mine_one()
    pool_bal = node.chain.balance(K.AIRDROP_POOL_ADDRESS)
    check("pool funded by 10%% split (25*5=125 LARZ)", pool_bal == 25 * 5 * COIN)

    app, claimed = airdrop.build_app(node)
    c = Client(app)
    user = Wallet()

    # unverified account rejected
    code, _ = c.req("POST", "/claim", {"account": "", "address": user.address})
    check("empty account rejected (403)", code == 403)

    # valid claim
    code, body = c.req("POST", "/claim",
                       {"account": "estate-user-1234", "address": user.address})
    check("valid claim accepted", code == 200 and "Claimed" in body)
    check("grant tx now in mempool", len(node.mempool) == 1)

    # confirm on-chain
    node.mine_one()
    check("user received 100 LARZ grant",
          node.chain.balance(user.address) == K.AIRDROP_WELCOME_GRANT)
    check("pool debited by the grant",
          node.chain.balance(K.AIRDROP_POOL_ADDRESS)
          == (25 + 1) * 5 * COIN - K.AIRDROP_WELCOME_GRANT)

    # one-per-account
    code, body = c.req("POST", "/claim",
                       {"account": "estate-user-1234", "address": user.address})
    check("second claim from same account blocked", "Already claimed" in body)

    # explorer renders
    ex = explorer.build_app(node)
    ec = Client(ex)
    code, home = ec.req("GET", "/")
    check("explorer home renders chain", code == 200 and "LarzChain Explorer" in home)
    code, apage = ec.req("GET", "/address/" + user.address)
    check("explorer shows user's 100 LARZ", "100.00000000 LARZ" in apage)
    code, ppage = ec.req("GET", "/pool")
    check("explorer shows the airdrop pool", "Airdrop Pool" in ppage)

    node.stop()
    print("\n  %d passed, %d failed" % (PASS[0], FAIL[0]))
    return 1 if FAIL[0] else 0


if __name__ == "__main__":
    sys.exit(main())
