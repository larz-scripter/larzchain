"""
Settle a Larzscript program on the LarzChain — end to end, in one process.

A money-native `.lz` program runs unchanged, but every `pay`/`subscribe` is
authorized against real on-chain LARZ and broadcast as a real signed
transaction. Run:

    python3 examples/larzscript_onchain.py

Requires `larzscript` importable (this demo adds the sibling repo to the path
if it lives next to larzchain).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))                       # larzchain repo
for cand in ("../larzscript", "../../larzscript"):              # sibling checkout
    p = os.path.abspath(os.path.join(_HERE, cand))
    if os.path.isdir(os.path.join(p, "larzscript")):
        sys.path.insert(0, p)
        break

from larzscript import run
from larzchain.node import Node
from larzchain.wallet import Wallet
from larzchain.tx import COIN
from larzchain.larzscript_settlement import LarzChainSettlement

# A money-native program. It has no idea it's about to settle on a blockchain.
PROGRAM = """
    wallet customer = $50.00
    wallet store
    wallet creator

    price plan = $12.00

    fn buy(buyer) {
        require buyer.balance >= plan, "not enough funds"
        pay plan from buyer to store
        pay plan * 0.25 from store to creator     # a 25% revenue split, on-chain
    }

    buy(customer)
    print("in-program store balance:", store.balance)
    print("in-program creator balance:", creator.balance)
"""


def main():
    treasury = Wallet()
    node = Node(port=19733, miner_address=treasury.address, faucet_wallet=treasury)

    settle = LarzChainSettlement(node)         # auto_mine: each pay confirms
    settle.mine_reward(5)                       # mine ~75 LARZ to the treasury
    settle.fund("customer", 50)                 # 50 LARZ -> the "customer" wallet

    print("on-chain BEFORE:", _fmt(settle.balances()))

    result = run(PROGRAM, settlement=settle)    # <-- the same program, on-chain
    print(result.output)

    print("on-chain AFTER: ", _fmt(settle.balances()))
    print("settled txids:  ", [t[:12] + "..." for t in settle.broadcast])
    print("chain height:   ", node.chain.height)

    # The two ledgers agree: the in-program wallet and the real chain match.
    store_larz = node.chain.balance(settle.address_of("store")) / COIN
    creator_larz = node.chain.balance(settle.address_of("creator")) / COIN
    assert abs(store_larz - 9.0) < 1e-9, store_larz        # $12 in, $3 split out
    assert abs(creator_larz - 3.0) < 1e-9, creator_larz    # 25% of $12
    print("\nOK - in-memory program and on-chain settlement agree.")


def _fmt(bals):
    return {k: ("%.2f LARZ" % v) for k, v in bals.items()}


if __name__ == "__main__":
    main()
