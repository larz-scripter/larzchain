# ⚡ LarzChain — LarzCoin (LARZ)

**A fair-launch, proof-of-work cryptocurrency. Earned, never sold. No premine.
Pure Python, zero dependencies.**

> ⚠️ **Experimental.** LARZ is **not an investment**, carries **no promise of
> value**, and **may be worth nothing**. There is **no sale** — coins come into
> existence only by mining, and are distributed only by mining rewards and a
> transparent, on-chain community airdrop. See [`PLAN.md`](PLAN.md).

LarzChain is a real, working blockchain built from first principles — the same
zero-dependency ethos as the [Larz framework](https://github.com/larz-scripter/larz),
which powers its block explorer and airdrop service.

## What's real here

* **secp256k1** ECDSA (RFC-6979 deterministic), compressed keys, base58check
  `L…` addresses — all pure Python (`crypto.py`)
* **UTXO transactions** with per-input signing over a commit-to-everything
  sighash (`tx.py`)
* **Proof-of-work blocks** — SHA-256d, merkle roots, Bitcoin-style compact
  difficulty (`block.py`)
* **Full consensus** (`chain.py` + `consensus.py`): block subsidy, halving,
  the **disclosed 10% airdrop split**, supply cap, difficulty retarget,
  signature + double-spend + over-mint checks, most-work chain selection, reorgs
* **P2P node** — HTTP/JSON gossip + pull-sync, mempool (`node.py`)
* **Wallet + CLI** (`wallet.py`, `cli.py`)
* **Block explorer + web wallet + airdrop claim** — Larz-framework apps
  (`explorer.py`, `airdrop.py`)

## Coin parameters

| | |
|---|---|
| Ticker / unit | **LARZ**, divisible to 100,000,000 sparks (8 decimals) |
| Max supply | **100,000,000 LARZ** (hard cap) |
| Block time | 120 s · PoW SHA-256d |
| Reward | 50 LARZ/block, halving every 1,000,000 blocks (~3.8 yr) |
| Coinbase split | **90% miner / 10% Estate Airdrop Pool** (consensus rule, on-chain) |
| Address prefix | `L…` |

## Distribution — earned, not sold

True fair launch: **no premine**, not one coin exists before block 0. The
airdrop is funded by a **protocol-level 90/10 split of every block reward** into
a public, on-chain pool address — every inflow (10% of each subsidy) and outflow
(community grants) is visible in the explorer. Verified estate accounts claim a
one-time welcome grant; there is nothing to buy. Full rationale in
[`PLAN.md`](PLAN.md).

## Quickstart

```bash
# run the whole thing: 2 P2P nodes, explorer, airdrop service
python3 examples/demo_testnet.py
#   node A (mining)   http://127.0.0.1:9333/info
#   block explorer    http://127.0.0.1:9500/
#   airdrop claim     http://127.0.0.1:9600/

# or the CLI
python3 -m larzchain wallet-new
python3 -m larzchain node --port 9333 --mine
python3 -m larzchain balance --node http://127.0.0.1:9333 --address L...
```

## Tests

```bash
python3 tests/test_chain.py     # 20 consensus checks (mining, halving, double-spend, reorg…)
python3 tests/test_p2p.py       # 7 checks: 3 real nodes sync + gossip + reorg  (integration)
python3 tests/test_airdrop.py   # 10 checks: pool funding, claim flow, explorer  (needs `pip install larz`)
```

37 checks, no pytest. CI runs the deterministic consensus suite (`test_chain.py`);
the socket-based P2P and framework-backed airdrop tests run locally as integration
tests (real sockets are too timing-flaky for shared CI runners).

## Status

Working testnet-grade implementation of every core mechanism. **Not** audited or
mainnet-ready: pure-Python secp256k1 is slow, the P2P layer is minimal (HTTP
gossip, no DoS hardening), and mainnet needs a security review + a crypto lawyer
for the airdrop mechanics. Roadmap in `PLAN.md` (Phase 6 = fair-launch mainnet).

## License

MIT. LarzCoin is experimental and earned, not sold — nothing here is a
solicitation to buy anything.
