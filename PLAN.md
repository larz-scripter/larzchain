# LarzCoin (LARZ) — Chain & Distribution Plan

**A fair-launch, proof-of-work cryptocurrency for the Larz ecosystem.
Earned, never sold. No premine. Open source.**

> ⚠️ **Honesty first.** LarzCoin is an experimental cryptocurrency. It is **not
> an investment**, carries **no promise of value**, and **may be worth nothing**.
> There is **no sale and no fundraising** — you cannot buy LARZ from us. Coins
> come into existence only by mining, and are distributed only by mining rewards
> and disclosed community airdrops. Everything below is public and verifiable.

---

## 1. Decisions locked (2026-07-25)

| Decision | Choice |
|---|---|
| **Intent** | Real ecosystem coin — earned via mining + estate activity, spendable across LarzOS. **Not sold.** |
| **Consensus** | Proof-of-Work, SHA-256d (Bitcoin-like), with difficulty retargeting |
| **Distribution** | **Fair-launch mining + disclosed estate airdrop** — no premine, no ICO |

---

## 2. Coin parameters (proposed)

| Parameter | Value | Notes |
|---|---|---|
| Ticker | **LARZ** | |
| Smallest unit | **spark** | 1 LARZ = 100,000,000 sparks (8 decimals, like satoshis) |
| Max supply | **100,000,000 LARZ** | hard cap, enforced by consensus |
| Block time | **120 s** (2 min) | snappier than BTC for in-app use |
| Initial block reward | **50 LARZ** | |
| Halving | every **1,000,000 blocks** (~3.8 yr) | geometric, sums to the 100M cap |
| Difficulty retarget | every **1,440 blocks** (~2 days) | targets 120 s/block |
| Genesis coinbase | **unspendable** | Bitcoin homage; embeds a launch headline |
| Address format | secp256k1 pubkey → hash → base58check | |

**Issuance math:** `initial_reward × halving_interval × 2 = 50 × 1,000,000 × 2 =
100,000,000 LARZ`. First halving ~3.8 years in; last sparks mined decades out.

---

## 3. Distribution — how coins actually reach people

Because it's a **true fair launch, there is no premine** — not one coin exists
before block 0. So the airdrop can't come from a founder stash; it comes from
**newly mined coins, transparently split at the protocol level.**

### 3.1 Block-reward split (consensus rule, on-chain, public)

Every block's coinbase is split:

* **90% → the miner** (45 LARZ initially) — pays for the work securing the chain
* **10% → the Estate Airdrop Pool** (5 LARZ initially) — a well-known, hard-coded
  address whose spending rules are public and auditable

This is **not** a hidden dev cut: the pool address is published, its inflows are
every 10% coinbase, and its outflows are community airdrop claims — all visible
on-chain in the block explorer. Anyone can verify no coins leak to insiders.

### 3.2 Estate airdrop — bootstrapping real holders

Funded entirely by the pool as it fills:

* **One-time welcome grant** — any verified LarzOS / EarnifyHub / CryptoLarz
  account can claim a fixed grant (proposed **100 LARZ**) once. First-come as the
  pool accrues; queued if the pool is temporarily empty.
* **Earn-by-activity** — small LARZ rewards for real ecosystem contribution,
  reusing existing gamification: finishing an Academy course, playing/winning
  games, publishing marketplace content, referring a user. Ties LARZ to genuine
  utility, not speculation.
* **Sybil resistance** — grants require an existing verified estate account +
  rate limits; not "one wallet = one claim" (trivially gamed).

### 3.3 Why this is defensible

* No sale → no "investment contract" being marketed → far less securities risk.
* No premine → no insider head-start; we mine block 0 at the same public moment
  as everyone else.
* Airdrop pool is on-chain and disclosed → no hidden enrichment.
* Utility-first (spend on Larz Pro / marketplace / tips) → value comes from
  *use* inside the ecosystem, not from convincing someone it'll "go up."

> **Legal note (not legal advice):** even a free airdrop can, in some structures
> and jurisdictions, be treated as a security or trigger tax events for
> recipients. Before mainnet, get a real crypto lawyer to review the airdrop
> mechanics and disclosures. I'll keep the design transparent and non-deceptive;
> I will not build hype, lock-ups, or buy-back/"number-go-up" mechanics.

---

## 4. Fair-launch integrity rules (non-negotiable)

To mean anything, "fair launch" has to be enforced:

1. **Pre-announce the genesis timestamp publicly** — a fixed date/time so nobody,
   us included, can mine ahead of the crowd.
2. **Open-source the full node before launch** — everyone starts equal.
3. **Zero premine** — genesis coinbase is unspendable; block 1 is the first
   spendable reward, mined in the open.
4. **Publish every parameter** (this document) — no surprise consensus changes.
5. **We mine in public** — no private head-start hashing.

---

## 5. Technical architecture (the node)

Same zero-dependency, pure-Python ethos as the Larz framework. Package layout:

```
larzchain/
  crypto.py      secp256k1 ECDSA (pure Python), base58check, address derivation
  tx.py          UTXO transactions: inputs/outputs, signing, verification
  block.py       block header + body, merkle root, block hashing (SHA-256d)
  chain.py       validation, longest-chain consensus, supply/halving, retarget
  mempool.py     pending-tx pool, fee ordering
  miner.py       PoW search + coinbase (with the 90/10 split rule)
  p2p.py         gossip node: peer discovery, block/tx propagation, sync
  wallet.py      keygen, balances, build/sign/send transactions
  node.py        HTTP/JSON-RPC API (submit tx, query chain, get block)
  cli.py         `larzchain` — node / wallet / mine / send
  explorer/      block explorer — a Larz-framework web app (dogfood!)
  airdrop/       pool claim service — Larz app, verifies estate accounts
tests/           consensus, double-spend, reorg, halving, retarget, signatures
```

**Crypto choice:** pure-Python secp256k1 keeps the zero-dep ethos and is fine at
our scale, but signing/verify is slow. Option to accept one vetted C-backed lib
(`coincurve`) for miners/nodes that want speed — decision at build time.

**Ecosystem interop:**
* Block explorer + web wallet built on the **Larz framework** (nice dogfood).
* **Pay-with-LARZ** as a Larz `PaymentProvider` → `@app.paid` can accept LARZ,
  so estate apps (Larz Pro, EarnifyHub marketplace) take the coin natively.
* Airdrop claim service reuses estate account verification.

---

## 6. Build roadmap

| Phase | Deliverable | Gate |
|---|---|---|
| **0** | Core primitives: crypto, tx (UTXO), block, chain validation + tests | double-spend & signature tests pass |
| **1** | Single-node mining: PoW, difficulty retarget, halving, wallet, CLI | can mine a chain, spend, verify supply cap |
| **2** | P2P networking: gossip, propagation, multi-node longest-chain consensus | 3 nodes converge, survive a reorg |
| **3** | Airdrop pool + claim service (estate account integration) | verified user claims a grant on testnet |
| **4** | Block explorer + web wallet (Larz-framework apps) | browse blocks/txs, send from browser |
| **5** | Public **testnet** run → community review → security pass | stable testnet, no consensus bugs |
| **6** | **Mainnet fair launch** — pre-announced genesis, open-source, we mine in public | lawyer-reviewed airdrop + disclosures |

---

## 7. Open decisions to confirm before/while building

* Max supply 100M and block time 120 s — good, or different feel?
* Airdrop split 90/10 — or lighter pool (95/5)?
* Welcome grant size (100 LARZ) and earn-by-activity rates.
* UTXO model (Bitcoin-like, recommended) vs account model (simpler, Ethereum-like).
* Pure-Python secp256k1 vs allow `coincurve` for speed.
* Ticker/branding: LARZ / LarzCoin — final?

---

*This is a living plan. Nothing here is a solicitation to buy anything, because
there is nothing to buy: LarzCoin can only be earned.*
