"""
larzchain.chain — the blockchain: UTXO set, full validation, and consensus.

Enforces every rule that makes LarzCoin sound money:
  * proof-of-work meets the block's difficulty, and difficulty follows the
    retarget schedule
  * every non-coinbase input spends a real, unspent output and is validly signed
  * no double-spends; outputs never exceed inputs (the difference is the fee)
  * the coinbase mints at most subsidy(height) + fees, and pays the 10% airdrop
    pool its exact share (the 90/10 split is consensus, not convention)
  * the money supply never exceeds MAX_SUPPLY
  * the best chain is the one with the most cumulative work; longer valid chains
    trigger a reorg
"""

from . import consensus as K
from .block import Block, bits_to_target
from .tx import verify_input_signature


class ValidationError(Exception):
    pass


class Blockchain:
    def __init__(self):
        self.blocks = []            # active chain, index = height
        self.index = {}             # block hash -> Block (all seen, incl. side)
        self.heights = {}           # block hash -> height on its branch
        self.work = {}              # block hash -> cumulative work
        self.utxos = {}             # (txid, index) -> TxOutput  (active chain)
        self._add_genesis()

    # --------------------------------------------------------------------- #
    def _add_genesis(self):
        g = K.make_genesis()
        self.blocks = [g]
        self.index[g.hash] = g
        self.heights[g.hash] = 0
        self.work[g.hash] = g.work
        # genesis coinbase is unspendable (0 value) -> not added to UTXO set

    @property
    def height(self):
        return len(self.blocks) - 1

    @property
    def tip(self):
        return self.blocks[-1]

    def total_supply(self):
        return sum(o.amount for o in self.utxos.values())

    def balance(self, address):
        return sum(o.amount for o in self.utxos.values() if o.address == address)

    def utxos_for(self, address):
        return [(op, o) for op, o in self.utxos.items() if o.address == address]

    # --------------------------------------------------------------------- #
    #  Difficulty expected for the block at `height` extending `prev`
    # --------------------------------------------------------------------- #
    def _expected_bits(self, prev_block, prev_height):
        height = prev_height + 1
        if height % K.RETARGET_INTERVAL != 0:
            return prev_block.header.bits
        first = self.blocks[prev_height + 1 - K.RETARGET_INTERVAL]
        timespan = prev_block.header.timestamp - first.header.timestamp
        return K.next_bits(prev_block.header.bits, timespan)

    # --------------------------------------------------------------------- #
    #  Validate a single transaction against a UTXO view
    # --------------------------------------------------------------------- #
    def _validate_tx(self, tx, utxo_view, spent_in_block):
        if tx.is_coinbase:
            raise ValidationError("coinbase only allowed as first tx")
        in_total = 0
        seen = set()
        for inp in tx.inputs:
            op = inp.outpoint
            if op in seen or op in spent_in_block:
                raise ValidationError("double-spend within block/tx")
            seen.add(op)
            funding = utxo_view.get(op)
            if funding is None:
                raise ValidationError("input spends unknown/spent output %s" % (op,))
            if not verify_input_signature(tx, inp, funding):
                raise ValidationError("bad signature on input %s" % (op,))
            in_total += funding.amount
        out_total = tx.total_out()
        if out_total > in_total:
            raise ValidationError("outputs exceed inputs")
        if any(o.amount < 0 for o in tx.outputs):
            raise ValidationError("negative output")
        return in_total - out_total            # fee

    # --------------------------------------------------------------------- #
    #  Full block validation (against a given prev tip state)
    # --------------------------------------------------------------------- #
    def _validate_block(self, block, prev_block, prev_height, utxo_view):
        h = block.header
        if h.prev_hash != prev_block.hash:
            raise ValidationError("prev_hash mismatch")
        if not block.valid_merkle():
            raise ValidationError("bad merkle root")
        if not h.pow_valid():
            raise ValidationError("insufficient proof-of-work")
        if h.bits != self._expected_bits(prev_block, prev_height):
            raise ValidationError("wrong difficulty bits")
        if not block.transactions or not block.transactions[0].is_coinbase:
            raise ValidationError("first tx must be coinbase")
        if any(t.is_coinbase for t in block.transactions[1:]):
            raise ValidationError("multiple coinbase txs")

        height = prev_height + 1
        fees = 0
        spent = set()
        for tx in block.transactions[1:]:
            fees += self._validate_tx(tx, utxo_view, spent)
            spent.update(inp.outpoint for inp in tx.inputs)

        # coinbase economics: subsidy + fees, with the 10% pool split enforced
        cb = block.transactions[0]
        allowed = K.subsidy(height) + fees
        if cb.total_out() > allowed:
            raise ValidationError("coinbase over-mints (%d > %d)"
                                  % (cb.total_out(), allowed))
        self._check_airdrop_split(cb, height, fees)

        # supply cap
        minted = K.subsidy(height)
        if self.total_supply() + minted > K.MAX_SUPPLY:
            raise ValidationError("exceeds max supply")
        return True

    def _check_airdrop_split(self, cb, height, fees):
        sub = K.subsidy(height)
        if sub == 0:
            return
        _, pool_share = K.split_subsidy(sub)
        paid = sum(o.amount for o in cb.outputs
                   if o.address == K.AIRDROP_POOL_ADDRESS)
        if paid < pool_share:
            raise ValidationError("airdrop pool underpaid (%d < %d)"
                                  % (paid, pool_share))

    # --------------------------------------------------------------------- #
    #  Apply / connect a block to the active chain (updates UTXO set)
    # --------------------------------------------------------------------- #
    def _apply(self, block):
        for tx in block.transactions:
            if not tx.is_coinbase:
                for inp in tx.inputs:
                    self.utxos.pop(inp.outpoint, None)
            for i, out in enumerate(tx.outputs):
                if out.amount > 0:
                    self.utxos[(tx.txid, i)] = out

    def _rebuild_utxos(self, chain):
        self.utxos = {}
        saved = self.blocks
        self.blocks = []
        for b in chain:
            self.blocks.append(b)
            self._apply(b)

    # --------------------------------------------------------------------- #
    #  Public: accept a block (extend tip, or consider a reorg)
    # --------------------------------------------------------------------- #
    def add_block(self, block):
        h = block.hash
        if h in self.index:
            return False                       # already have it
        prev = self.index.get(block.header.prev_hash)
        if prev is None:
            raise ValidationError("orphan: unknown prev_hash")
        prev_height = self.heights[block.header.prev_hash]

        # build the UTXO view as of `prev` (fast path: prev is current tip)
        if block.header.prev_hash == self.tip.hash:
            self._validate_block(block, prev, prev_height, self.utxos)
            self._connect_to_tip(block)
            return True

        # side branch: validate against a reconstructed view, maybe reorg
        branch = self._branch_to(prev)
        view = self._utxo_view_for(branch)
        self._validate_block(block, prev, prev_height, view)
        self.index[h] = block
        self.heights[h] = prev_height + 1
        self.work[h] = self.work[block.header.prev_hash] + block.work
        if self.work[h] > self.work[self.tip.hash]:
            self._reorg_to(block)
            return True
        return False                            # kept as a side branch

    def _connect_to_tip(self, block):
        self.blocks.append(block)
        self.index[block.hash] = block
        self.heights[block.hash] = self.height
        self.work[block.hash] = self.work[block.header.prev_hash] + block.work
        self._apply(block)

    def _branch_to(self, block):
        """Return the list of blocks from genesis..block along its branch."""
        chain = []
        cur = block
        while cur is not None:
            chain.append(cur)
            cur = self.index.get(cur.header.prev_hash)
        return list(reversed(chain))

    def _utxo_view_for(self, chain):
        view = {}
        for b in chain:
            for tx in b.transactions:
                if not tx.is_coinbase:
                    for inp in tx.inputs:
                        view.pop(inp.outpoint, None)
                for i, out in enumerate(tx.outputs):
                    if out.amount > 0:
                        view[(tx.txid, i)] = out
        return view

    def _reorg_to(self, new_tip):
        chain = self._branch_to(new_tip)
        self.blocks = chain
        self.utxos = self._utxo_view_for(chain)

    def get_block(self, h):
        return self.index.get(h)

    def serialize_chain(self):
        return [b.to_dict() for b in self.blocks]
