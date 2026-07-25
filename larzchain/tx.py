"""
larzchain.tx — UTXO transactions for LarzCoin.

Bitcoin-style: a transaction spends previous outputs (inputs) and creates new
ones (outputs). Amounts are in *sparks* (1 LARZ = 100_000_000 sparks). Each
input is signed over a sighash that commits to the whole transaction, so nothing
can be altered after signing.
"""

import json
from . import crypto

COIN = 100_000_000            # sparks per LARZ


class TxOutput:
    __slots__ = ("amount", "address")

    def __init__(self, amount, address):
        self.amount = int(amount)          # sparks
        self.address = address             # base58check 'L...' address

    def to_dict(self):
        return {"amount": self.amount, "address": self.address}

    @staticmethod
    def from_dict(d):
        return TxOutput(d["amount"], d["address"])


class TxInput:
    __slots__ = ("txid", "index", "pubkey", "signature")

    def __init__(self, txid, index, pubkey=None, signature=None):
        self.txid = txid                   # hex id of the funding tx
        self.index = int(index)            # which output of it
        self.pubkey = pubkey               # hex compressed pubkey (spender)
        self.signature = signature         # hex 64-byte sig

    @property
    def outpoint(self):
        return (self.txid, self.index)

    def to_dict(self, include_sig=True):
        d = {"txid": self.txid, "index": self.index}
        if include_sig:
            d["pubkey"] = self.pubkey
            d["signature"] = self.signature
        return d

    @staticmethod
    def from_dict(d):
        return TxInput(d["txid"], d["index"], d.get("pubkey"), d.get("signature"))


class Transaction:
    def __init__(self, inputs, outputs, is_coinbase=False, note=""):
        self.inputs = inputs               # [TxInput]
        self.outputs = outputs             # [TxOutput]
        self.is_coinbase = is_coinbase
        self.note = note                   # coinbase memo / arbitrary tag

    # -- serialization / id ------------------------------------------------ #
    def _core(self, include_sig):
        return {
            "inputs": [i.to_dict(include_sig) for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "is_coinbase": self.is_coinbase,
            "note": self.note,
        }

    def serialize(self, include_sig=True):
        return json.dumps(self._core(include_sig), sort_keys=True,
                          separators=(",", ":")).encode()

    @property
    def txid(self):
        return crypto.sha256d(self.serialize(include_sig=True)).hex()

    def sighash(self):
        """Hash signed by every input — commits to the whole tx minus sigs."""
        return crypto.sha256d(self.serialize(include_sig=False))

    # -- signing ----------------------------------------------------------- #
    def sign(self, privkeys):
        """privkeys: list aligned with inputs (skip for coinbase)."""
        h = self.sighash()
        for inp, priv in zip(self.inputs, privkeys):
            pub = crypto.privkey_to_pubkey(priv)
            inp.pubkey = crypto.compress_pubkey(pub).hex()
            inp.signature = crypto.sign(h, priv).hex()
        return self

    # -- value ------------------------------------------------------------- #
    def total_out(self):
        return sum(o.amount for o in self.outputs)

    def to_dict(self):
        d = self._core(include_sig=True)
        d["txid"] = self.txid
        return d

    @staticmethod
    def from_dict(d):
        return Transaction(
            [TxInput.from_dict(i) for i in d["inputs"]],
            [TxOutput.from_dict(o) for o in d["outputs"]],
            is_coinbase=d.get("is_coinbase", False),
            note=d.get("note", ""))


def coinbase(outputs, note=""):
    """A coinbase tx has no real inputs; it mints the block subsidy + fees."""
    return Transaction([], outputs, is_coinbase=True, note=note)


def verify_input_signature(tx, inp, funding_output):
    """Check that `inp` is validly signed by the owner of `funding_output`."""
    if not inp.pubkey or not inp.signature:
        return False
    pub_bytes = bytes.fromhex(inp.pubkey)
    # the spender's pubkey must hash to the funded address
    if crypto.b58check_encode(crypto.ADDRESS_VERSION,
                              crypto.hash160(pub_bytes)) != funding_output.address:
        return False
    point = crypto.decompress_pubkey(pub_bytes)
    return crypto.verify(tx.sighash(), bytes.fromhex(inp.signature), point)
