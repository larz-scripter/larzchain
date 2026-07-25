"""
Pay-with-LARZ test: a Larz-framework @app.paid route unlocked by an on-chain
LarzCoin payment. Ties the framework and the blockchain together.
Needs the larz framework importable (`pip install larz`).
"""
import sys, os, io, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from larz import Larz, Response
from larzchain.node import Node
from larzchain.wallet import Wallet
from larzchain.larzpay import enable as enable_larzpay
from larzchain.tx import COIN

PASS = [0]; FAIL = [0]
def check(name, cond):
    if cond: PASS[0] += 1; print("  ok   " + name)
    else:    FAIL[0] += 1; print("  FAIL " + name)


class Client:
    def __init__(self, app): self.app = app; self.cookie = None
    def get(self, path, follow=False, _d=0):
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": path.split("?")[0],
               "QUERY_STRING": "", "CONTENT_LENGTH": "0",
               "wsgi.input": io.BytesIO(b""), "HTTP_USER_AGENT": "Mozilla/5.0"}
        if self.cookie: env["HTTP_COOKIE"] = self.cookie
        sh = {}
        def sr(s, h): sh["c"] = int(s.split()[0]); sh["h"] = h
        raw = b"".join(self.app(env, sr))
        for k, v in sh["h"]:
            if k == "Set-Cookie": self.cookie = v.split(";")[0]
        loc = dict(sh["h"]).get("Location")
        if follow and sh["c"] in (301, 302, 303) and loc and _d < 6:
            p = loc.split("://", 1)[-1]; p = p[p.find("/"):] if "/" in p else "/"
            return self.get(p, follow=True, _d=_d + 1)
        return sh["c"], raw.decode("utf-8", "replace"), loc


def main(db):
    # a node with a user who has mined some LARZ, and a merchant wallet
    user = Wallet()
    node = Node(port=9700, miner_address=user.address)
    for _ in range(3):
        node.mine_one()                              # user now holds 3*45 LARZ
    check("user funded by mining", node.chain.balance(user.address) == 3 * 45 * COIN)

    merchant = Wallet()
    app = Larz(secret="larzpay-test")
    provider = enable_larzpay(app, node, merchant, base_url="http://x",
                              db=db, background=False)

    @app.paid("$5")                                  # 5 LARZ
    @app.get("/pro")
    def pro(req):
        return "UNLOCKED"

    c = Client(app)
    # 1. unpaid -> redirected to a LARZ pay page
    code, body, loc = c.get("/pro", follow=False)
    check("unpaid route redirects to pay page", code == 302 and "/larzpay/pay/" in loc)

    # 2. the pay page shows a deposit address + the 5 LARZ amount
    code, page, _ = c.get(loc[loc.find("/larzpay"):])
    check("pay page asks for 5 LARZ", "5.00000000 LARZ" in page)
    m = re.search(r"<code>(L[0-9A-Za-z]+)</code>", page)
    check("pay page shows a deposit address", bool(m))
    deposit = m.group(1)

    # 3. user pays on-chain, miner confirms it
    tx = user.send(node.chain, deposit, 5 * COIN)
    node.submit_tx(tx)
    node.mine_one()
    check("merchant deposit address received 5 LARZ",
          node.chain.balance(deposit) == 5 * COIN)

    # 4. watcher settles -> entitlement granted
    settled = provider.settle()
    check("watcher settled the payment", settled == 1)

    # 5. the paid route now serves
    code, body, _ = c.get("/pro", follow=False)
    check("route unlocked after LARZ payment", code == 200 and body == "UNLOCKED")

    node.stop()
    print("\n  %d passed, %d failed" % (PASS[0], FAIL[0]))
    return 1 if FAIL[0] else 0


if __name__ == "__main__":
    import tempfile
    sys.exit(main(os.path.join(tempfile.mkdtemp(), "lp.db")))
