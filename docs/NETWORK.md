# LarzChain wire protocol (v1)

The node network speaks HTTP/JSON. This document is complete enough to build a
compatible node in any language. Transport may gain a raw-TCP option later; this
HTTP protocol is `PROTOCOL_VERSION = 1`.

## Identity

Two nodes peer only if they agree on:

- **`network_id`** — a string, e.g. `"larz-testnet-1"`.
- **`genesis`** — the hash of the genesis block (hex).

Any message that carries a mismatched `network_id`/`genesis` is rejected with
`409 Conflict`, and the peer is not added. This keeps testnet and any future
mainnet cleanly separated, and stops incompatible chains from cross-talking.

## Envelope

Gossip messages (`POST /block`, `POST /tx`) are wrapped:

```json
{ "network_id": "larz-testnet-1", "genesis": "<hash>", "version": 1, "data": { ... } }
```

Read-only endpoints (`/info`, `/blocks`, …) return plain JSON but include
`network_id`/`genesis` in `/info` so callers can verify before syncing.

## Handshake — `POST /hello`

A joining node introduces itself. Request:

```json
{ "network_id": "...", "genesis": "...", "version": 1,
  "public_url": "https://me.example.com:9333", "height": 1234 }
```

- On a network/genesis mismatch → `409`.
- Otherwise the receiver **adds the caller's `public_url` to its peer set**
  (this is how discovery becomes two-way) and replies:

```json
{ "network_id": "...", "genesis": "...", "version": 1, "protocol": 1,
  "height": 1235, "url": "https://receiver...", "peers": ["<url>", "..."] }
```

`peers` is a random bounded sample (≤16) of the receiver's known peers, so
callers learn the wider network (peer-exchange / gossip of addresses).

## Bootstrap

A fresh node discovers the network by, in order:

1. Loading persisted peers (from `<persist>.peers`).
2. Fetching a published `seeds.txt` (one URL per line, `#` comments allowed).
3. Falling back to a built-in seed list.
4. Sending `POST /hello` to each candidate, then adding the peers each returns.

If a node's peer set ever drops to empty, it re-bootstraps.

## Sync

- **`GET /info`** → `{ height, tip, work, supply, mempool, peers, url,
  network_id, genesis, version, update_available }`.
- A node adopts a peer's chain only if the peer's cumulative **`work`** exceeds
  its own (Nakamoto most-work rule; reorgs handled).
- **`GET /blocks?from=N`** → `{ "blocks": [ ... ] }` (blocks at index ≥ N).
  Sync pulls `from = max(0, my_height - 25)` so it fetches only the recent window
  (plus reorg buffer), not the whole chain each cycle.
- **`GET /headers?from=N`** → `{ "headers": [{height,hash,prev,time}, ...] }` for
  a future headers-first sync.

## Gossip

- **`POST /block`** — relay a new block (enveloped). Accepted blocks are
  re-gossiped to peers.
- **`POST /tx`** — relay a new transaction (enveloped).

## Introspection & operations

| Method & path | Returns |
|---|---|
| `GET /health` | `{ok, version, network_id, height, peers, mempool, uptime_s, errors, update_available}` |
| `GET /metrics` | Prometheus text exposition (`larzchain_*`) |
| `GET /debug` | `{stats, peers, peer_fails, peer_versions, banned, recent_errors}` |
| `GET /peers` | known peer URLs |
| `GET /balance/<addr>` | `{address, balance}` |
| `GET /utxos/<addr>` | `{address, utxos, balance}` |
| `GET /history/<addr>` | recent receive history |
| `GET /block/<hash>` | one block |
| `GET /mempool` | pending transactions |
| `GET /faucet/<addr>` | testnet coins (rate-limited 1/hour) |

## Abuse limits

- **Body cap**: POST bodies over 4 MB are dropped early (`413` / connection close).
- **Rate limit**: writes are limited to ~240 requests / 60 s per source IP
  (`429` when exceeded).
- **Peer eviction**: a peer that fails repeatedly (~8 times) is dropped.
- **Validation is authoritative**: a peer can never make you accept an invalid
  block or transaction — bad data is rejected by consensus validation, and the
  limits above bound the bandwidth it can waste.

## Updates

Nodes periodically read a published `version.txt` (a version string). If it's
newer than the running version, `/health.update_available` and `/info` surface it
and the node logs a warning. Nodes **never auto-update** — upgrading is a manual,
operator-controlled action (auto-updating node software is a supply-chain risk).

## Constants (testnet)

| name | value |
|---|---|
| `NETWORK_ID` | `larz-testnet-1` |
| `PROTOCOL_VERSION` | `1` |
| default port | `9333` |
| block time | 120 s |
| genesis timestamp | 1785000000 (pre-announced) |
