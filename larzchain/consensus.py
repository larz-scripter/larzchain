"""
larzchain.consensus — LarzCoin's economic + difficulty rules, in one place.

Everything here is a consensus rule: change it and you're on a different chain.
Values match PLAN.md. Fair launch: no premine, genesis coinbase unspendable.
"""

import hashlib
from . import crypto
from .tx import COIN, TxOutput, coinbase
from .block import BlockHeader, Block, bits_to_target, target_to_bits

# --- monetary policy ------------------------------------------------------ #
MAX_SUPPLY        = 100_000_000 * COIN      # hard cap, in sparks
INITIAL_SUBSIDY   = 50 * COIN               # block 1 reward
HALVING_INTERVAL  = 1_000_000               # blocks (~3.8 yr at 120s)

# --- the disclosed distribution split (consensus-enforced) ---------------- #
AIRDROP_BASIS_POINTS = 1000                 # 10.00% of each coinbase subsidy


def _pool_privkey():
    """DEMO/testnet pool key — deterministic so genesis is reproducible and the
    claim service can spend accrued pool funds. MAINNET uses a securely-generated
    key whose ADDRESS is published (the key is custodied, the address is public
    and every inflow/outflow is on-chain — see PLAN.md §3.1)."""
    d = hashlib.sha256(b"larzcoin-estate-airdrop-pool-v1").digest()
    return int.from_bytes(d, "big") % (crypto.N - 1) + 1


def pool_address():
    return crypto.pubkey_to_address(crypto.privkey_to_pubkey(_pool_privkey()))


# A well-known, hard-coded pool address. Inflows (10% of every subsidy) and
# outflows (community airdrop claims) are fully visible on-chain. NOT a premine
# and NOT a hidden founder wallet — see PLAN.md §3.
AIRDROP_POOL_ADDRESS = pool_address()

AIRDROP_WELCOME_GRANT = 100 * COIN          # one-time grant per verified account

# --- timing / difficulty -------------------------------------------------- #
TARGET_BLOCK_TIME = 120                     # seconds
RETARGET_INTERVAL = 1440                    # blocks (~2 days)
# Genesis difficulty: easy enough to CPU-mine in the demo. Real mainnet would
# start harder. bits 0x1f00ffff -> a very large target (low difficulty).
GENESIS_BITS = 0x1f00ffff
MAX_TARGET   = bits_to_target(GENESIS_BITS)


def subsidy(height):
    """Total newly-minted sparks at a given block height (before the cap)."""
    if height == 0:
        return 0                            # genesis mints nothing (fair launch)
    halvings = (height - 1) // HALVING_INTERVAL
    if halvings >= 64:
        return 0
    return INITIAL_SUBSIDY >> halvings


def split_subsidy(total):
    """Split a subsidy into (miner_share, airdrop_pool_share)."""
    pool = total * AIRDROP_BASIS_POINTS // 10000
    return total - pool, pool


def next_bits(prev_bits, actual_timespan):
    """Retarget: adjust difficulty to hold TARGET_BLOCK_TIME, clamped 4x."""
    expected = TARGET_BLOCK_TIME * RETARGET_INTERVAL
    actual = max(expected // 4, min(actual_timespan, expected * 4))
    new_target = bits_to_target(prev_bits) * actual // expected
    new_target = min(new_target, MAX_TARGET)
    return target_to_bits(new_target)


# --- genesis -------------------------------------------------------------- #
GENESIS_NOTE = ("LarzCoin genesis 2026 - fair launch, no premine, "
                "earned not sold. https://larzos.com/larz")
GENESIS_TIMESTAMP = 1785000000              # fixed, pre-announced launch time


def make_genesis():
    """Deterministic genesis block. Coinbase output is unspendable (0 value)."""
    cb = coinbase([TxOutput(0, AIRDROP_POOL_ADDRESS)], note=GENESIS_NOTE)
    header = BlockHeader(version=1, prev_hash="00" * 32,
                         merkle_root="", timestamp=GENESIS_TIMESTAMP,
                         bits=GENESIS_BITS, nonce=0)
    block = Block(header, [cb]).update_merkle()
    # mine the genesis to satisfy PoW (cheap at GENESIS_BITS)
    while not block.header.pow_valid():
        block.header.nonce += 1
    return block


# --- P2P network identity + bootstrap (testnet) --------------------------- #
# A node only peers with others on the same NETWORK_ID *and* genesis hash, so
# testnet and any future mainnet never cross-connect. Bump NETWORK_ID for a new
# network. Seeds are estate-run bootstrap nodes; the list can grow at runtime via
# the published SEEDS_URL without a client release.
NETWORK_ID = "larz-testnet-1"
PROTOCOL_VERSION = 1
DEFAULT_PORT = 9333
SEED_NODES = [
    "https://larzos.com/larzchain/rpc",     # estate seed (Apache -> :9333)
]
SEEDS_URL = "https://larzos.com/larzchain/seeds.txt"
VERSION_URL = "https://larzos.com/larzchain/version.txt"
