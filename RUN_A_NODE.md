# Run a LarzChain node

> **Testnet.** LARZ is experimental, not an investment, and may be worth nothing.
> Running a node is participating in a test network. See [`PLAN.md`](PLAN.md).

A LarzChain node stores the chain, relays blocks/transactions, and helps the
network stay in sync. It's pure Python, zero dependencies — Python 3.8+.

## 1. Get it

```bash
git clone https://github.com/larz-scripter/larzchain
cd larzchain
python3 -m larzchain version
```

## 2. Run

**Local / behind NAT** (stays synced, doesn't accept inbound — fine for most):

```bash
python3 -m larzchain node --persist chain.json
```

It auto-connects to the seed nodes, syncs the chain, and starts relaying. That's
it — you're on the network.

**Public node** (others can connect to you — this is what powers the network).
Tell it the URL peers should dial back, and make that URL reachable:

```bash
python3 -m larzchain node \
  --port 9333 \
  --public-url https://your-server.example.com:9333 \
  --persist /var/lib/larzchain/chain.json \
  --log /var/log/larzchain.log
```

Open the port (or put it behind a reverse proxy — see below). New nodes that
find you via the seeds will peer with you and pull your chain.

**Mine** (optional — help secure the chain and earn the block reward):

```bash
python3 -m larzchain node --mine --address L<your-address> --persist chain.json
```

## 3. Check it's healthy

Every node exposes plain HTTP endpoints:

```bash
curl http://127.0.0.1:9333/health     # height, peers, version, uptime, errors
curl http://127.0.0.1:9333/metrics    # Prometheus-format counters
curl http://127.0.0.1:9333/debug      # stats + recent errors + peers
curl http://127.0.0.1:9333/info       # chain tip, work, peers, network id
```

- `/health` — a one-glance status; `update_available` is set when a newer node
  version is published (it **never auto-updates** — you upgrade when you choose).
- `/metrics` — scrape with Prometheus/Grafana or any tool that reads the text
  exposition format.
- `/debug` — the last ~50 errors with timestamps, plus per-peer failure counts.

## 4. Keep it running (systemd)

Copy [`deploy/larzchain-node.service`](deploy/larzchain-node.service), edit the
paths/URL, then:

```bash
sudo cp deploy/larzchain-node.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now larzchain-node
sudo journalctl -u larzchain-node -f
```

## 5. Or with Docker

```bash
docker build -t larzchain .
docker run -d --name larzchain -p 9333:9333 \
  -v larzchain-data:/data \
  larzchain node --port 9333 --persist /data/chain.json \
  --public-url http://YOUR_PUBLIC_IP:9333
```

## Behind a reverse proxy (recommended for public HTTPS)

Terminate TLS at nginx/Apache/Caddy and proxy to the node. Example (Apache):

```apache
ProxyPass        /larzchain/rpc/ http://127.0.0.1:9333/
ProxyPassReverse /larzchain/rpc/ http://127.0.0.1:9333/
```

Then run with `--public-url https://your-domain/larzchain/rpc`.

## Options

| flag | meaning |
|---|---|
| `--port` | listen port (default 9333) |
| `--public-url` | the URL peers dial back (public nodes) |
| `--persist` | file to store the chain **and** learned peers |
| `--seeds` | comma-separated seed URLs (overrides the built-in list) |
| `--peer` | add a specific peer (repeatable) |
| `--no-bootstrap` | don't contact seeds on start |
| `--mine` / `--address` | mine to an address |
| `--report-url` | **opt-in** telemetry: POST health/errors to a collector (off by default) |
| `--log` | also write logs to a file |

## Notes

- **No phone-home.** A node only talks to peers and (optionally) the published
  seed/version files. Telemetry is **off** unless you set `--report-url`.
- **Nodes behind NAT** stay fully synced by pulling from peers; they just can't
  accept inbound connections. Publicly-reachable nodes form the backbone — the
  same shape as Bitcoin.
- Protocol details for building a compatible node: [`docs/NETWORK.md`](docs/NETWORK.md).
