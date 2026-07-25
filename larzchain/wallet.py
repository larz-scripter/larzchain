"""
larzchain.wallet — key management and transaction building.

Keeps one or more secp256k1 keys, finds spendable UTXOs for its addresses in a
chain, and builds + signs transactions (with change and an optional fee).
"""

from . import crypto
from .tx import Transaction, TxInput, TxOutput, COIN


class Wallet:
    def __init__(self, privkeys=None):
        self.keys = {}                         # address -> privkey
        for pk in (privkeys or []):
            self.add_key(pk)
        if not self.keys:
            self.new_address()

    def add_key(self, privkey):
        pub = crypto.privkey_to_pubkey(privkey)
        addr = crypto.pubkey_to_address(pub)
        self.keys[addr] = privkey
        return addr

    def new_address(self):
        return self.add_key(crypto.gen_privkey())

    @property
    def address(self):
        return next(iter(self.keys))

    @property
    def addresses(self):
        return list(self.keys)

    def balance(self, chain):
        return sum(chain.balance(a) for a in self.keys)

    def _spendable(self, chain):
        out = []
        for a in self.keys:
            out.extend((op, o) for op, o in chain.utxos_for(a))
        return out

    def send(self, chain, to_address, amount, fee=0):
        """Build + sign a tx sending `amount` sparks to `to_address`."""
        amount, fee = int(amount), int(fee)
        need = amount + fee
        selected, gathered = [], 0
        for op, o in sorted(self._spendable(chain), key=lambda x: -x[1].amount):
            selected.append((op, o))
            gathered += o.amount
            if gathered >= need:
                break
        if gathered < need:
            raise ValueError("insufficient funds: have %d, need %d" % (gathered, need))

        inputs = [TxInput(op[0], op[1]) for op, _ in selected]
        outputs = [TxOutput(amount, to_address)]
        change = gathered - need
        if change > 0:
            outputs.append(TxOutput(change, self.address))     # change back to us

        tx = Transaction(inputs, outputs)
        privkeys = [self.keys[o.address] for _, o in selected]
        tx.sign(privkeys)
        return tx
