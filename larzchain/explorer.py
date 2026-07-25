"""
larzchain.explorer — a block explorer + web wallet, built on the Larz framework.

Reads a live Node: chain stats, blocks, transactions, address balances, mempool.
The wallet page generates a key, shows balance, and sends LARZ. Dogfoods Larz.
"""

from larz import Larz, Response         # pip install larz
from . import consensus as K, crypto
from .wallet import Wallet
from .tx import COIN


def _larz(sparks):
    return "%.8f" % (sparks / COIN)


def build_app(node):
    app = Larz(secret="larz-explorer", debug=True)

    def shell(title, body):
        return Response(
            "<!doctype html><meta charset=utf-8><title>%s · LarzChain</title>"
            "<style>body{font:15px/1.5 system-ui;max-width:820px;margin:1.5rem auto;"
            "padding:0 1rem;color:#111}a{color:#0a7;text-decoration:none}"
            "h1{margin:.2em 0}.card{border:1px solid #e3e3e3;border-radius:10px;"
            "padding:12px 16px;margin:10px 0}.mono{font-family:ui-monospace,monospace;"
            "font-size:13px;word-break:break-all}table{width:100%%;border-collapse:collapse}"
            "td,th{text-align:left;padding:6px 10px;border-bottom:1px solid #eee}"
            ".pill{background:#e6f7f0;color:#067a52;border-radius:999px;padding:2px 8px;"
            "font-size:12px}</style>"
            "<p><b>⚡ LarzChain Explorer</b> · <a href='/'>chain</a> · "
            "<a href='/mempool'>mempool</a> · <a href='/wallet'>wallet</a> · "
            "<a href='/pool'>airdrop pool</a></p><h1>%s</h1>%s" % (title, title, body))

    @app.get("/")
    def home(req):
        info = node.info()
        rows = ""
        with node.lock:
            for b in reversed(node.chain.blocks[-15:]):
                hgt = node.chain.heights[b.hash]
                rows += ("<tr><td><a href='/block/%s'>#%d</a></td>"
                         "<td class='mono'>%s…</td><td>%d tx</td>"
                         "<td>%s LARZ</td></tr>"
                         % (b.hash, hgt, b.hash[:16], len(b.transactions),
                            _larz(sum(o.amount for t in b.transactions for o in t.outputs))))
        return shell("Chain",
            "<div class=card>Height <b>%d</b> · Supply <b>%s LARZ</b> / 100,000,000 "
            "· Mempool <b>%d</b> · Peers <b>%d</b></div>"
            "<table><tr><th>Block</th><th>Hash</th><th>Txs</th><th>Value</th></tr>%s</table>"
            % (info["height"], _larz(info["supply"]), info["mempool"],
               len(info["peers"]), rows))

    @app.get("/block/<h>")
    def block(req):
        b = node.chain.get_block(req.params["h"])
        if not b:
            return shell("Block", "<p>Not found.</p>"), 404
        hgt = node.chain.heights[b.hash]
        txs = ""
        for t in b.transactions:
            outs = "".join("<li class=mono>%s LARZ → %s</li>"
                           % (_larz(o.amount), o.address) for o in t.outputs)
            kind = "<span class=pill>coinbase</span>" if t.is_coinbase else ""
            txs += ("<div class=card><div class=mono>%s %s</div><ul>%s</ul></div>"
                    % (t.txid[:24] + "…", kind, outs))
        return shell("Block #%d" % hgt,
            "<div class=card class=mono>hash %s<br>prev %s<br>time %d · nonce %d · "
            "bits 0x%08x</div>%s" % (b.hash, b.header.prev_hash, b.header.timestamp,
                                     b.header.nonce, b.header.bits, txs))

    @app.get("/address/<addr>")
    def address(req):
        a = req.params["addr"]
        bal = node.chain.balance(a)
        utxos = "".join("<tr><td class=mono>%s:%d</td><td>%s LARZ</td></tr>"
                        % (op[0][:20] + "…", op[1], _larz(o.amount))
                        for op, o in node.chain.utxos_for(a))
        return shell("Address",
            "<div class=card class=mono>%s</div><div class=card>Balance: <b>%s LARZ</b></div>"
            "<table><tr><th>UTXO</th><th>Value</th></tr>%s</table>" % (a, _larz(bal), utxos))

    @app.get("/pool")
    def pool(req):
        bal = node.chain.balance(K.AIRDROP_POOL_ADDRESS)
        return shell("Estate Airdrop Pool",
            "<div class=card>The community pool receives <b>10%%</b> of every block "
            "subsidy and pays welcome grants. Fully on-chain.</div>"
            "<div class=card class=mono>%s</div>"
            "<div class=card>Balance: <b>%s LARZ</b></div>"
            "<p><a href='/address/%s'>view UTXOs</a></p>"
            % (K.AIRDROP_POOL_ADDRESS, _larz(bal), K.AIRDROP_POOL_ADDRESS))

    @app.get("/mempool")
    def mempool(req):
        rows = "".join("<div class=card class=mono>%s → %s outputs, %s LARZ</div>"
                       % (t.txid[:24] + "…", len(t.outputs), _larz(t.total_out()))
                       for t in node.mempool.values()) or "<p>Empty.</p>"
        return shell("Mempool (%d)" % len(node.mempool), rows)

    # --- minimal web wallet ---------------------------------------------- #
    @app.get("/wallet")
    def wallet_home(req):
        priv = req.session.get("wpriv")
        if not priv:
            w = Wallet(); req.session["wpriv"] = w.keys[w.address]
            addr = w.address
        else:
            addr = Wallet([priv]).address
        bal = node.chain.balance(addr)
        return shell("Wallet",
            "<div class=card>Your address<br><b class=mono>%s</b></div>"
            "<div class=card>Balance: <b>%s LARZ</b></div>"
            "<form method=post action=/wallet/send>"
            "<p><input name=to placeholder='recipient L... address' "
            "style='width:100%%;padding:8px'></p>"
            "<p><input name=amount placeholder='amount (LARZ)' "
            "style='width:100%%;padding:8px'></p>"
            "<button style='background:#0a7;color:#fff;border:0;padding:10px 16px;"
            "border-radius:8px'>Send</button></form>" % (addr, _larz(bal)))

    @app.post("/wallet/send")
    def wallet_send(req):
        priv = req.session.get("wpriv")
        if not priv:
            return Response.redirect("/wallet")
        w = Wallet([priv])
        to = req.form.get("to", "")
        try:
            sparks = int(round(float(req.form.get("amount", "0")) * COIN))
            tx = w.send(node.chain, to, sparks)
        except Exception as e:
            return shell("Send failed", "<p>%s</p><p><a href='/wallet'>back</a></p>" % e)
        node.submit_tx(tx)
        return shell("Sent",
            "<p>Broadcast <span class=mono>%s LARZ</span> to<br><span class=mono>%s</span>"
            "</p><p>Confirms next block. <a href='/wallet'>back</a></p>"
            % (_larz(sparks), to))

    return app
