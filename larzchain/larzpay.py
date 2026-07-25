"""
larzchain.larzpay — pay for Larz-framework @app.paid routes with LARZ.

Plugs LarzCoin into the Larz framework's money layer as a PaymentProvider, so a
plain `@app.paid("$5")` route can be unlocked by an on-chain LARZ payment:

    from larzchain.larzpay import enable as enable_larzpay
    enable_larzpay(app, node, merchant_wallet, base_url="http://127.0.0.1:8000")

    @app.paid("$5")                    # 5 LARZ (see pricing note below)
    @app.get("/pro")
    def pro(req): ...

Flow: an unpaid visitor is redirected to a pay page showing a UNIQUE deposit
address and the LARZ amount. A background watcher sees the confirmed on-chain
payment and grants the entitlement; the visitor is bounced back, now served.

Pricing note: the money layer denominates prices in its "$" unit. LarzPay maps
**1 price-unit = 1 LARZ** — this is a unit convention for ecosystem-native
pricing, NOT a claim that LARZ is worth any number of dollars.
"""

import time
import uuid
import threading

from larz import Response
from larz.providers import PaymentProvider
from .tx import COIN


class LarzCoinProvider(PaymentProvider):
    name = "larzcoin"

    def __init__(self, node, merchant_wallet):
        self.node = node
        self.merchant = merchant_wallet
        self.pending = {}          # cid -> {subject, sku, sparks, address, done, success}
        self.by_addr = {}          # deposit address -> cid
        self.base_url = ""
        self.store = None          # money store, set by enable()

    def create_checkout(self, subject, sku, cents, success_url, cancel_url):
        sparks = cents * COIN // 100                 # 1 price-unit == 1 LARZ
        address = self.merchant.new_address()        # fresh per checkout
        cid = uuid.uuid4().hex[:12]
        self.pending[cid] = {"subject": subject, "sku": sku, "sparks": sparks,
                             "address": address, "done": False,
                             "success": success_url}
        self.by_addr[address] = cid
        return self.base_url + "/larzpay/pay/" + cid

    def parse_webhook(self, req):
        return None                                  # on-chain, not webhook-based

    # -- confirmation ------------------------------------------------------ #
    def settle(self):
        """One watcher pass: grant entitlements for confirmed deposits.
        Returns the number of newly-settled checkouts."""
        n = 0
        for cid, p in self.pending.items():
            if p["done"]:
                continue
            if self.node.chain.balance(p["address"]) >= p["sparks"]:
                self.store.grant(p["subject"], p["sku"])
                self.store.record_payment("larz_" + cid, p["subject"], p["sku"],
                                          p["sparks"], "larzcoin")
                p["done"] = True
                n += 1
        return n

    def watch(self, interval=1.5):
        def loop():
            while True:
                try:
                    self.settle()
                except Exception:
                    pass
                time.sleep(interval)
        threading.Thread(target=loop, daemon=True).start()


def enable(app, node, merchant_wallet, base_url="http://127.0.0.1:8000",
           db="larzpay_money.db", background=True):
    """Wire LarzCoin payments into a Larz app's money layer."""
    import larz.money as money
    provider = LarzCoinProvider(node, merchant_wallet)
    m = money.enable(app, provider=provider, base_url=base_url, db=db)
    provider.base_url = base_url.rstrip("/")
    provider.store = m.store

    def _larz(sparks):
        return "%.8f" % (sparks / COIN)

    @app.get("/larzpay/pay/<cid>", sitemap=False)
    def pay_page(req):
        p = provider.pending.get(req.params["cid"])
        if not p:
            return Response("unknown checkout", status=404)
        if p["done"]:
            return Response.redirect(p["success"])
        return Response(
            "<meta http-equiv=refresh content='3'>"
            "<style>body{font:16px system-ui;max-width:480px;margin:3rem auto;"
            "padding:0 1rem;text-align:center}code{background:#f4f4f4;padding:6px 10px;"
            "border-radius:6px;word-break:break-all}</style>"
            "<h1>Pay with LARZ ⚡</h1>"
            "<p>Send exactly <b>%s LARZ</b> to:</p><p><code>%s</code></p>"
            "<p>Waiting for confirmation… this page refreshes automatically.</p>"
            "<p><small>Once the payment confirms on-chain you'll be unlocked "
            "automatically.</small></p>" % (_larz(p["sparks"]), p["address"]))

    @app.get("/larzpay/status/<cid>", sitemap=False)
    def status(req):
        p = provider.pending.get(req.params["cid"])
        if not p:
            return Response.json({"error": "unknown"}, status=404)
        return Response.json({"paid": p["done"], "address": p["address"],
                              "sparks": p["sparks"]})

    if background:
        provider.watch()
    return provider
