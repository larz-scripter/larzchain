"""
larzchain.larzscript_settlement — settle Larzscript payments on-chain.

Larzscript (the Larz stack's money-native language) runs every ``pay`` and
``subscribe`` through a pluggable *settlement backend*. This module IS that
backend, wired to a real LarzChain node: a ``pay`` inside a ``.lz`` program is

  1. **authorized** against the payer's real, confirmed on-chain LARZ balance
     (an over-spend is declined *before* any money moves — no partial settle), and
  2. **recorded** by building, signing and broadcasting a real LARZ transaction.

So the same money-native program you can run in-memory now settles for real:

    from larzscript import run
    from larzchain.node import Node
    from larzchain.wallet import Wallet
    from larzchain.larzscript_settlement import LarzChainSettlement

    treasury = Wallet()
    node = Node(port=9333, miner_address=treasury.address, faucet_wallet=treasury)

    settle = LarzChainSettlement(node)
    settle.mine_reward(4)            # mine some LARZ to the treasury (dev)
    settle.fund("customer", 50)      # 50 LARZ -> the program's "customer" wallet

    run(open("store.lz").read(), settlement=settle)   # every pay is now on-chain
    print(settle.broadcast)          # the real on-chain txids that settled

Unit convention (matching :mod:`larzchain.larzpay`): **1 Larzscript price-unit
($1.00) == 1 LARZ**. That is an ecosystem-native pricing unit, not a USD peg.

This is the only place the chain depends on the language: importing this module
requires ``larzscript`` installed, but importing ``larzchain`` itself does not.
"""

from larzscript.runtime import Settlement, Transaction
from larzscript.errors import SettlementError

from .wallet import Wallet
from .tx import COIN


def cents_to_sparks(cents):
    """A Larzscript Money amount (integer cents) in LarzChain sparks.

    $1.00 == 100 cents == 1 LARZ == COIN sparks, so sparks = cents * COIN / 100.
    """
    return int(cents) * COIN // 100


class LarzChainSettlement(Settlement):
    """A Larzscript settlement backend backed by a LarzChain node.

    Each Larzscript wallet name is mapped to a LarzChain identity. Names that
    send money need a signing key (a :class:`larzchain.wallet.Wallet`); names
    that only receive can be registered as a bare address. Unmapped names are
    auto-provisioned a fresh key when ``auto_provision`` is true (the default),
    which is convenient for demos and tests.

    ``auto_mine`` (default true) confirms each settled payment into its own
    block, so a payer's change output is spendable before its next payment —
    the simple, always-correct mode. Set it false for throughput and call
    :meth:`mine` yourself, keeping in mind that several unconfirmed payments
    from the *same* wallet contend for the same UTXOs.
    """

    def __init__(self, node, accounts=None, auto_provision=True, auto_mine=True):
        self.node = node
        self.auto_provision = auto_provision
        self.auto_mine = auto_mine
        self.accounts = {}          # name -> Wallet (has a signing key)
        self.addresses = {}         # name -> address (send- or receive-only)
        self.broadcast = []         # on-chain txids this backend has submitted
        for name, holder in (accounts or {}).items():
            self.register(name, holder)

    # -- identity mapping -------------------------------------------------- #
    def register(self, name, holder):
        """Map a Larzscript wallet ``name`` to a LarzChain Wallet or address."""
        if isinstance(holder, Wallet):
            self.accounts[name] = holder
            self.addresses[name] = holder.address
        else:                                        # a bare 'L...' address
            self.addresses[name] = holder
        return self.addresses[name]

    def _wallet(self, name):
        """The signing Wallet for ``name`` (auto-provisioned if allowed)."""
        w = self.accounts.get(name)
        if w is None:
            if not self.auto_provision:
                raise SettlementError(
                    "no on-chain signing key for wallet '%s'" % name)
            w = Wallet()
            self.register(name, w)
        return w

    def address_of(self, name):
        if name in self.addresses:
            return self.addresses[name]
        return self._wallet(name).address

    # -- chain helpers ----------------------------------------------------- #
    @property
    def chain(self):
        return self.node.chain

    def onchain_balance(self, name):
        """Confirmed on-chain balance of ``name``, in sparks."""
        return self.chain.balance(self.address_of(name))

    def balances(self):
        """A {name: LARZ} snapshot of every mapped account (whole + fraction)."""
        return {name: self.chain.balance(addr) / COIN
                for name, addr in self.addresses.items()}

    def mine(self, note="larzscript"):
        """Mine one block (confirming pending broadcasts). Returns the block.

        The note is made unique per block (by appending the height) so the
        coinbase transaction never collides with an earlier identical one - two
        coinbases with the same outputs *and* the same note would share a txid
        and the second would silently overwrite the first in the UTXO set.
        """
        return self.node.mine_one(note="%s-h%d" % (note, self.chain.height + 1))

    def mine_reward(self, n=1):
        """Dev helper: mine ``n`` blocks so the node's miner accrues LARZ."""
        last = None
        for _ in range(int(n)):
            last = self.mine(note="reward")
        return last

    def fund(self, name, larz, fee=0):
        """Dev helper: send ``larz`` LARZ from the node faucet wallet to
        ``name`` and confirm it. Requires ``node.faucet_wallet`` to hold funds
        (see :meth:`mine_reward`)."""
        if not self.node.faucet_wallet:
            raise SettlementError("node has no faucet_wallet to fund from")
        sparks = int(larz) * COIN
        tx = self.node.faucet_wallet.send(self.chain, self.address_of(name),
                                          sparks, fee=fee)
        self.node.submit_tx(tx, gossip=False)
        self.mine(note="fund-" + name)
        return tx.txid

    # -- the settlement path (called by Larzscript's pay/subscribe) -------- #
    #
    # We override transfer() rather than the authorize()/record() hooks because
    # on-chain settlement must key on each wallet's *identity* (its declared
    # name, e.g. "customer"), not the label used at the pay site (e.g. the
    # parameter name "buyer" inside `fn buy(buyer) { pay ... from buyer ... }`).
    # transfer() receives the actual Wallet objects, so their .name is the
    # stable identity we funded and sign with; the labels are kept only for the
    # returned ledger Transaction, so the in-program ledger still reads the way
    # the source code did.
    def transfer(self, src, dst, amount, src_label=None, dst_label=None,
                 kind="pay", memo=None):
        need = cents_to_sparks(amount.cents)
        if self.onchain_balance(src.name) < need:
            raise SettlementError(
                "settlement declined: '%s' has %.8f LARZ, needs %s"
                % (src.name, self.onchain_balance(src.name) / COIN, amount))
        # keep the in-program wallet balances correct (mirrors the chain)
        src.debit(amount)
        dst.credit(amount)
        # settle on-chain, by wallet identity
        self._settle_onchain(src.name, dst.name, need, memo or kind)
        return Transaction(src_label if src_label is not None else src.name,
                           dst_label if dst_label is not None else dst.name,
                           amount)

    def _settle_onchain(self, payer_name, payee_name, sparks, note):
        payer = self._wallet(payer_name)              # needs a signing key
        to_addr = self.address_of(payee_name)
        onchain = payer.send(self.chain, to_addr, sparks)
        if not self.node.submit_tx(onchain, gossip=False):
            raise SettlementError(
                "on-chain tx %s->%s was not accepted (unconfirmed inputs?)"
                % (payer_name, payee_name))
        self.broadcast.append(onchain.txid)
        if self.auto_mine:
            self.mine(note=note)
        return onchain.txid
