"""
larzchain.miner — assemble a candidate block and find a proof-of-work nonce.

The coinbase pays the miner (90% of subsidy + all tx fees) and the Estate
Airdrop Pool (10% of subsidy) — the split is a consensus rule enforced by every
validating node, not an honor system.
"""

from . import consensus as K
from .tx import TxOutput, coinbase
from .block import Block, BlockHeader


def build_coinbase(height, miner_address, fees, note=""):
    sub = K.subsidy(height)
    miner_share, pool_share = K.split_subsidy(sub)
    outs = [TxOutput(miner_share + fees, miner_address)]
    if pool_share > 0:
        outs.append(TxOutput(pool_share, K.AIRDROP_POOL_ADDRESS))
    return coinbase(outs, note=note or ("h%d" % height))


def assemble_block(chain, miner_address, mempool_txs=(), timestamp=None, note=""):
    height = chain.height + 1
    fees = sum(_fee(chain, tx) for tx in mempool_txs)
    cb = build_coinbase(height, miner_address, fees, note=note)
    txs = [cb] + list(mempool_txs)
    bits = chain._expected_bits(chain.tip, chain.height)
    header = BlockHeader(version=1, prev_hash=chain.tip.hash, merkle_root="",
                         timestamp=timestamp if timestamp is not None
                         else chain.tip.header.timestamp + K.TARGET_BLOCK_TIME,
                         bits=bits, nonce=0)
    return Block(header, txs).update_merkle()


def _fee(chain, tx):
    in_total = sum(chain.utxos[i.outpoint].amount for i in tx.inputs
                   if i.outpoint in chain.utxos)
    return max(0, in_total - tx.total_out())


def mine(block, max_nonce=None):
    """Grind the nonce until the header meets its PoW target."""
    h = block.header
    while not h.pow_valid():
        h.nonce += 1
        if max_nonce is not None and h.nonce > max_nonce:
            return None
    return block
