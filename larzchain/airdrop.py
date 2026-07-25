"""
larzchain.airdrop — the Estate Airdrop claim service (a Larz-framework app).

Verified LarzOS / EarnifyHub / CryptoLarz accounts claim a one-time welcome grant
of LARZ, paid from the on-chain Estate Airdrop Pool. Everything is transparent:
the pool address, its inflows (10% of every block subsidy), and every grant it
pays out are all visible in the block explorer.

Sybil resistance: a claim requires a verified estate account id (checked by
`verify_account`, stubbed here) and is one-per-account. Real deployment wires
`verify_account` to the estate's account/session system.
"""

from larz import Larz, Response         # pip install larz
from . import consensus as K, crypto
from .wallet import Wallet
from .tx import COIN


def pool_wallet():
    return Wallet([K._pool_privkey()])


def verify_account(account_id):
    """STUB: return True if `account_id` is a real verified estate account.
    Wire this to LarzOS/EarnifyHub/CryptoLarz account verification in production."""
    return bool(account_id) and len(account_id) >= 4


def build_app(node):
    """node: a larzchain.node.Node this service submits grant txs to."""
    app = Larz(secret="larz-airdrop", debug=True)
    claimed = set()                       # account_id already granted (demo store)
    pool = pool_wallet()

    def page(body):
        return Response("<style>body{font:16px system-ui;max-width:560px;margin:2rem "
                        "auto;padding:0 1rem}a{color:#0a7}input{padding:8px;width:100%%;"
                        "margin:6px 0}.b{background:#0a7;color:#fff;border:0;padding:10px "
                        "16px;border-radius:8px}</style>" + body)

    @app.get("/")
    def home(req):
        pool_bal = node.chain.balance(K.AIRDROP_POOL_ADDRESS)
        return page(
            "<h1>⚡ LarzCoin Estate Airdrop</h1>"
            "<p>Verified estate accounts claim a one-time <b>%d LARZ</b> welcome "
            "grant, paid from the on-chain community pool.</p>"
            "<p>Pool balance: <b>%.4f LARZ</b> · <a href='http://127.0.0.1:%d'>explorer</a></p>"
            "<form method=post action=/claim>"
            "<input name=account placeholder='your estate account id'>"
            "<input name=address placeholder='your LarzCoin address (L...)'>"
            "<button class=b>Claim %d LARZ</button></form>"
            "<p><small>Experimental. LARZ is earned, not sold, and may be worth "
            "nothing. This is a free airdrop, not an investment.</small></p>"
            % (K.AIRDROP_WELCOME_GRANT // COIN, pool_bal / COIN,
               EXPLORER_PORT, K.AIRDROP_WELCOME_GRANT // COIN))

    @app.post("/claim")
    def claim(req):
        f = req.form
        account, address = f.get("account", ""), f.get("address", "")
        if not verify_account(account):
            return page("<h1>✗ Not verified</h1><p>That estate account can't be "
                        "verified.</p><p><a href='/'>back</a></p>"), 403
        if account in claimed:
            return page("<h1>Already claimed</h1><p>One grant per account.</p>"
                        "<p><a href='/'>back</a></p>")
        if not crypto.is_valid_address(address):
            return page("<h1>Bad address</h1><p>Enter a valid L... address.</p>"
                        "<p><a href='/'>back</a></p>"), 400
        if node.chain.balance(K.AIRDROP_POOL_ADDRESS) < K.AIRDROP_WELCOME_GRANT:
            return page("<h1>Pool refilling</h1><p>The pool is temporarily empty; "
                        "try again as more blocks are mined.</p>")
        tx = pool.send(node.chain, address, K.AIRDROP_WELCOME_GRANT)
        if not node.submit_tx(tx):
            return page("<h1>Try again</h1><p>Grant not accepted (pool UTXOs may be "
                        "mid-confirmation).</p>")
        claimed.add(account)
        return page("<h1>✅ Claimed!</h1><p>%d LARZ is on its way to<br><code>%s</code>"
                    "</p><p>It confirms in the next block. "
                    "<a href='http://127.0.0.1:%d/address/%s'>track it</a></p>"
                    % (K.AIRDROP_WELCOME_GRANT // COIN, address, EXPLORER_PORT, address))

    return app, claimed


EXPLORER_PORT = 9500
