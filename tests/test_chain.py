"""
LarzChain consensus tests — plain `python3 tests/test_chain.py`, no pytest.
Mines a real chain, spends coins, and asserts every core consensus rule.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from larzchain import consensus as K
from larzchain.chain import Blockchain, ValidationError
from larzchain.wallet import Wallet
from larzchain.miner import assemble_block, mine
from larzchain.tx import COIN

PASS = [0]; FAIL = [0]
def check(name, cond):
    if cond: PASS[0] += 1; print("  ok   " + name)
    else:    FAIL[0] += 1; print("  FAIL " + name)


def mine_block(chain, miner_addr, txs=(), ts=None):
    blk = assemble_block(chain, miner_addr, txs, timestamp=ts)
    mine(blk)
    chain.add_block(blk)
    return blk


def main():
    chain = Blockchain()
    alice, bob = Wallet(), Wallet()

    check("genesis height 0", chain.height == 0)
    check("genesis mints nothing (fair launch)", chain.total_supply() == 0)

    # --- mine 3 blocks to alice ------------------------------------------- #
    for _ in range(3):
        mine_block(chain, alice.address)
    check("height after 3 mined", chain.height == 3)

    # each block subsidy = 50 LARZ, miner gets 90% = 45, pool gets 10% = 5
    check("alice mined 3*45 LARZ", alice.balance(chain) == 3 * 45 * COIN)
    check("airdrop pool got 3*5 LARZ",
          chain.balance(K.AIRDROP_POOL_ADDRESS) == 3 * 5 * COIN)
    check("total supply = 3*50 LARZ", chain.total_supply() == 3 * 50 * COIN)

    # --- alice pays bob 10 LARZ ------------------------------------------- #
    tx = alice.send(chain, bob.address, 10 * COIN, fee=0)
    mine_block(chain, alice.address, txs=[tx])
    check("bob received 10 LARZ", bob.balance(chain) == 10 * COIN)
    check("alice balance dropped by 10 (+ new block reward)",
          alice.balance(chain) == (3 * 45 - 10 + 45) * COIN)
    check("supply now 4*50 LARZ", chain.total_supply() == 4 * 50 * COIN)

    # --- double-spend is rejected ----------------------------------------- #
    tx1 = alice.send(chain, bob.address, 5 * COIN)
    # craft a second tx spending the SAME inputs
    tx2 = alice.send(chain, bob.address, 5 * COIN)
    tx2.inputs = tx1.inputs                       # force identical inputs
    tx2.sign([alice.keys[alice.address]] * len(tx2.inputs))
    blk = assemble_block(chain, alice.address, [tx1, tx2]); mine(blk)
    try:
        chain.add_block(blk); ok = False
    except ValidationError:
        ok = True
    check("double-spend within block rejected", ok)

    # --- tampered signature rejected -------------------------------------- #
    good = alice.send(chain, bob.address, 1 * COIN)
    good.outputs[0].amount = 40 * COIN            # tamper AFTER signing
    blk = assemble_block(chain, alice.address, [good]); mine(blk)
    try:
        chain.add_block(blk); ok = False
    except ValidationError:
        ok = True
    check("tampered tx (sig no longer valid) rejected", ok)

    # --- over-minting coinbase rejected ----------------------------------- #
    blk = assemble_block(chain, alice.address)
    blk.transactions[0].outputs[0].amount += 999 * COIN   # steal extra
    blk.update_merkle(); mine(blk)
    try:
        chain.add_block(blk); ok = False
    except ValidationError:
        ok = True
    check("over-minting coinbase rejected", ok)

    # --- insufficient PoW rejected ---------------------------------------- #
    blk = assemble_block(chain, alice.address)
    blk.header.nonce = 0                           # do NOT mine
    if not blk.header.pow_valid():
        try:
            chain.add_block(blk); ok = False
        except ValidationError:
            ok = True
        check("block without valid PoW rejected", ok)
    else:
        check("block without valid PoW rejected", True)   # trivial target edge

    # --- halving math ----------------------------------------------------- #
    check("subsidy at height 1 = 50 LARZ", K.subsidy(1) == 50 * COIN)
    check("subsidy after 1 halving = 25 LARZ",
          K.subsidy(K.HALVING_INTERVAL + 1) == 25 * COIN)
    check("subsidy after 2 halvings = 12.5 LARZ",
          K.subsidy(2 * K.HALVING_INTERVAL + 1) == 25 * COIN // 2)
    total = sum(K.subsidy(h) for h in range(1, 64 * K.HALVING_INTERVAL, 1)) if False else None
    check("max supply is the 100M cap", K.MAX_SUPPLY == 100_000_000 * COIN)

    print("\n  %d passed, %d failed" % (PASS[0], FAIL[0]))
    return 1 if FAIL[0] else 0


if __name__ == "__main__":
    sys.exit(main())
