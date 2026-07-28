"""
Tests for larzchain.larzscript_settlement — Larzscript payments settling on-chain.

These need `larzscript` importable; if it isn't, the whole module is skipped so
larzchain's own suite stays green without the language installed. When run from
a dev checkout, larzscript is picked up from a sibling directory.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _cand in ("../larzscript", "../../larzscript"):
    _p = os.path.abspath(os.path.join(os.path.dirname(__file__), _cand))
    if os.path.isdir(os.path.join(_p, "larzscript")):
        sys.path.insert(0, _p)
        break

try:
    from larzscript import run
    from larzscript.errors import SettlementError
    _HAVE_LZ = True
except Exception:                                    # pragma: no cover
    _HAVE_LZ = False

from larzchain.node import Node
from larzchain.wallet import Wallet
from larzchain.tx import COIN

if _HAVE_LZ:
    from larzchain.larzscript_settlement import (LarzChainSettlement,
                                                 cents_to_sparks)


def _fresh_settlement(port):
    treasury = Wallet()
    node = Node(port=port, miner_address=treasury.address, faucet_wallet=treasury)
    settle = LarzChainSettlement(node)
    settle.mine_reward(1)                             # 45 LARZ to the treasury
    return settle


@unittest.skipUnless(_HAVE_LZ, "larzscript not importable")
class TestUnitConversion(unittest.TestCase):
    def test_cents_map_to_sparks_one_dollar_is_one_larz(self):
        self.assertEqual(cents_to_sparks(100), COIN)       # $1.00 == 1 LARZ
        self.assertEqual(cents_to_sparks(350), 350 * COIN // 100)


@unittest.skipUnless(_HAVE_LZ, "larzscript not importable")
class TestOnChainSettlement(unittest.TestCase):
    def test_a_pay_settles_on_chain(self):
        s = _fresh_settlement(port=19801)
        s.fund("customer", 20)
        run("wallet customer = $20.00\nwallet shop\n"
            "pay $12.00 from customer to shop\n", settlement=s)
        self.assertEqual(s.onchain_balance("customer"), 8 * COIN)
        self.assertEqual(s.onchain_balance("shop"), 12 * COIN)
        self.assertEqual(len(s.broadcast), 1)          # one real tx broadcast

    def test_identity_not_label_pays_from_the_right_wallet(self):
        # inside `fn buy(buyer)` the pay label is "buyer", but the funded
        # identity is "customer" - settlement must follow the wallet, not the label.
        s = _fresh_settlement(port=19802)
        s.fund("customer", 20)
        run("wallet customer = $20.00\nwallet store\n"
            "fn buy(buyer) { pay $5.00 from buyer to store }\n"
            "buy(customer)\n", settlement=s)
        self.assertEqual(s.onchain_balance("customer"), 15 * COIN)
        self.assertEqual(s.onchain_balance("store"), 5 * COIN)

    def test_a_subscription_settles_on_chain(self):
        s = _fresh_settlement(port=19803)
        s.fund("customer", 20)
        run("wallet customer = $20.00\nwallet platform\n"
            "paywall pro = $9.00 / month to platform\n"
            "subscribe customer to pro\n", settlement=s)
        self.assertEqual(s.onchain_balance("platform"), 9 * COIN)
        self.assertEqual(s.onchain_balance("customer"), 11 * COIN)


@unittest.skipUnless(_HAVE_LZ, "larzscript not importable")
class TestDecline(unittest.TestCase):
    def test_overspend_is_declined_and_moves_no_money(self):
        s = _fresh_settlement(port=19804)
        s.fund("customer", 5)                          # only 5 LARZ on-chain
        before_c = s.onchain_balance("customer")
        with self.assertRaises(SettlementError):
            run("wallet customer = $5.00\nwallet shop\n"
                "pay $9.00 from customer to shop\n", settlement=s)
        # declined before any move: balances unchanged, nothing broadcast
        self.assertEqual(s.onchain_balance("customer"), before_c)
        self.assertEqual(s.onchain_balance("shop"), 0)
        self.assertEqual(s.broadcast, [])


if __name__ == "__main__":
    unittest.main()
