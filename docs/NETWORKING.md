# LarzChain networking — plan & protocol

> Status: **design + build plan** for turning LarzChain from a manual-peer
> testnet into a self-forming, open peer-to-peer network that anyone can join by
> running a node. **Testnet only.** LARZ is experimental, not an investment, and
> may be worth nothing; mainnet remains a legal/genesis gate (see
> [`../PLAN.md`](../PLAN.md)).

## Goal

Run one command on any reachable server and your node **auto-discovers the
network, syncs the most-work chain, and gossips** — an open mesh of independent
nodes, like Bitcoin, but over simple HTTP/JSON and with zero dependencies.

Two decisions are locked:

- **Transport = HTTP/JSON.** Proxy/Cloudflare-friendly, firewall-tolerant, already
  built and tested. (A raw-TCP transport may be added later as an optional v2 — the
  protocol below is designed so it can be, without a breaking change.)
- **Bootstrap = estate seed nodes + a published seed list.** A small built-in seed
  list, plus a `seeds.txt` hosted at a well-known larzos.com URL, so a fresh node
  finds the network with no manual peering.

## What already works (today)

- HTTP JSON node (`larzchain node --port 9333`): `/info`, `/blocks`, `/block`,
  `/tx`, `/balance`, `/utxos`, `/history`, `/peers`, `/faucet`.
- **Gossip** new blocks/txs to peers; **pull-sync** from peers every 2s; **peer
  exchange** (learn peers from a peer's `/info`).
- **Most-work-chain consensus** with reorgs. Chain persists across restarts.
- You can already connect two servers manually: `--peer <host:port>`.

What's missing is everything that makes it *self-forming and safe to expose*.

## The upgrade (phased)

### Phase 1 — Identity & handshake
- **`network_id`** (e.g. `"larz-testnet-1"`) + **genesis hash** attached to every
  message. Nodes reject peers on a different network or genesis, so testnet and a
  future mainnet never cross-connect and only compatible chains peer.
- **Public address advertising** — `--public-url https://node.example.com` (or
  `host:port`). A node advertises the URL peers should dial back, not `127.0.0.1`.
- **`POST /hello`** handshake — a joining node sends `{network_id, genesis,
  version, height, public_url}`. The receiver validates, **adds the caller to its
  peer set** (two-way discovery — this is the missing piece today), and replies
  with its own info + a sample of its peers.

### Phase 2 — Bootstrap & peer management
- **Built-in seed list** (`consensus.py`): a few estate-run node URLs.
- **`seeds.txt`** fetched from a well-known URL (e.g.
  `https://larzos.com/larzchain/seeds.txt`) so the seed set can grow without a
  client release. On startup a node: loads persisted peers → contacts seeds →
  `/hello` → peer-exchange → connected.
- **Peer persistence** — save/restore the peer set (JSON, next to the chain).
- **Peer management** — `max_peers`, evict unreachable peers, prefer address
  diversity, periodic re-seed if peer count drops to zero.

### Phase 3 — Efficient sync
- **Incremental blocks** — `GET /blocks?from=<my_height>` instead of `from=0`
  every cycle. Optional **headers-first**: `GET /headers?from=N` to pick the
  best chain cheaply, then fetch bodies.
- Back off sync frequency when fully synced; sync eagerly on a new-block gossip.

### Phase 4 — Hardening (before public exposure)
- Per-IP **rate limits** on write endpoints (`/tx`, `/block`, `/hello`).
- **Max message size** + strict schema validation of peer-supplied data.
- **Ban/greylist** peers that send invalid blocks/txs or spam.
- Cap mempool size; drop low-value/duplicate txs.
- Keep all block/tx validation authoritative (a peer can never make you accept an
  invalid block — worst case it wastes bandwidth, which the limits bound).

### Phase 5 — Operator experience & docs
- **`RUN_A_NODE.md`** — install, open the port (or run behind a reverse proxy),
  seeds, a **systemd unit**, and a **Dockerfile**. One command to a running node.
- **`NETWORK.md`** — this protocol, frozen enough that someone could write a
  compatible node in another language. That's what "open" means for a chain.
- **Published testnet params** — `network_id`, genesis timestamp + hash, seed
  list, default port.
- **Multi-node integration tests** — bootstrap → handshake → converge → reorg,
  and abuse cases (bad network id, oversized message, invalid block).

### Phase 6 — Launch the testnet mesh
- Estate runs **2–3 always-on seed/backbone nodes** (systemd, publicly reachable
  via HTTPS reverse proxy), publishes `seeds.txt` and the join guide.
- Anyone runs `larzchain node --public-url …` and joins. Backbone = publicly
  reachable nodes; NAT'd nodes stay synced (outbound pull) but don't accept
  inbound — same shape as Bitcoin.

## Protocol sketch (HTTP/JSON)

Every request/response carries a small envelope:

```json
{ "network_id": "larz-testnet-1", "genesis": "<hash>", "version": 1, "data": { ... } }
```

| Method & path            | Purpose                                             |
|--------------------------|-----------------------------------------------------|
| `POST /hello`            | handshake; caller announces `public_url`, gets peers|
| `GET  /info`             | height, tip, work, supply, mempool, peers, url      |
| `GET  /headers?from=N`   | block headers from height N (headers-first sync)    |
| `GET  /blocks?from=N`    | full blocks from height N                            |
| `POST /block`            | gossip a new block                                  |
| `POST /tx`               | gossip a new transaction                            |
| `GET  /peers`            | known peer URLs (bounded sample)                    |

Mismatched `network_id`/`genesis` → `409 Conflict`, connection dropped.

## Honest constraints

- **HTTP/JSON**, not Bitcoin's raw TCP — simpler and proxy-friendly, but higher
  overhead and less hardened. Acceptable for testnet; revisit for scale.
- **Pure-Python secp256k1 is slow.** Fine for testnet block rates; a `coincurve`
  fast-path is a later, optional add.
- **NAT.** Home nodes stay synced but can't accept inbound; public nodes are the
  backbone.
- **Mainnet is a gate, not code.** Pre-announced genesis, a crypto-lawyer review of
  the airdrop/disclosures, a security review, and harder starting difficulty come
  before any real launch. This plan is testnet only.

## Milestones

- [ ] P1 identity + `/hello` handshake + public-url advertising
- [ ] P2 seed bootstrap + `seeds.txt` + peer persistence/management
- [ ] P3 incremental (headers-first) sync
- [ ] P4 rate limits / size caps / ban list
- [ ] P5 `RUN_A_NODE.md` + Dockerfile + systemd + `NETWORK.md` + integration tests
- [ ] P6 estate seed nodes live + published join guide (testnet launch)
