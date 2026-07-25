"""
larzchain.block — block structure, merkle root, proof-of-work hashing, and the
Bitcoin-style compact difficulty encoding (`bits`).
"""

import json
from . import crypto
from .tx import Transaction


# --- compact difficulty (nBits), like Bitcoin ----------------------------- #
def bits_to_target(bits):
    exponent = bits >> 24
    coefficient = bits & 0x007FFFFF
    if exponent <= 3:
        return coefficient >> (8 * (3 - exponent))
    return coefficient << (8 * (exponent - 3))


def target_to_bits(target):
    if target <= 0:
        return 0
    size = (target.bit_length() + 7) // 8
    if size <= 3:
        coefficient = target << (8 * (3 - size))
    else:
        coefficient = target >> (8 * (size - 3))
    if coefficient & 0x00800000:                     # keep it positive
        coefficient >>= 8
        size += 1
    return (size << 24) | (coefficient & 0x007FFFFF)


def merkle_root(txids):
    if not txids:
        return "00" * 32
    layer = [bytes.fromhex(t) for t in txids]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])                   # duplicate the last
        layer = [crypto.sha256d(layer[i] + layer[i + 1])
                 for i in range(0, len(layer), 2)]
    return layer[0].hex()


class BlockHeader:
    __slots__ = ("version", "prev_hash", "merkle_root", "timestamp", "bits", "nonce")

    def __init__(self, version, prev_hash, merkle_root, timestamp, bits, nonce=0):
        self.version = version
        self.prev_hash = prev_hash
        self.merkle_root = merkle_root
        self.timestamp = timestamp
        self.bits = bits
        self.nonce = nonce

    def serialize(self):
        return json.dumps({
            "version": self.version, "prev_hash": self.prev_hash,
            "merkle_root": self.merkle_root, "timestamp": self.timestamp,
            "bits": self.bits, "nonce": self.nonce},
            sort_keys=True, separators=(",", ":")).encode()

    @property
    def hash(self):
        return crypto.sha256d(self.serialize()).hex()

    def pow_valid(self):
        return int(self.hash, 16) <= bits_to_target(self.bits)

    def to_dict(self):
        return {"version": self.version, "prev_hash": self.prev_hash,
                "merkle_root": self.merkle_root, "timestamp": self.timestamp,
                "bits": self.bits, "nonce": self.nonce}

    @staticmethod
    def from_dict(d):
        return BlockHeader(d["version"], d["prev_hash"], d["merkle_root"],
                           d["timestamp"], d["bits"], d["nonce"])


class Block:
    def __init__(self, header, transactions):
        self.header = header
        self.transactions = transactions            # [Transaction]

    @property
    def hash(self):
        return self.header.hash

    @property
    def txids(self):
        return [t.txid for t in self.transactions]

    def update_merkle(self):
        self.header.merkle_root = merkle_root(self.txids)
        return self

    def valid_merkle(self):
        return self.header.merkle_root == merkle_root(self.txids)

    @property
    def work(self):
        """Approx work = 2^256 / (target+1); summed across a chain for consensus."""
        target = bits_to_target(self.header.bits)
        return (1 << 256) // (target + 1)

    def to_dict(self):
        return {"header": self.header.to_dict(),
                "transactions": [t.to_dict() for t in self.transactions]}

    @staticmethod
    def from_dict(d):
        return Block(BlockHeader.from_dict(d["header"]),
                     [Transaction.from_dict(t) for t in d["transactions"]])
