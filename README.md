# tunnel-monitor

A lightweight Docker container that monitors IPsec VPN tunnels and Twingate connectors via ping and optional TCP port checks. Sends Slack alerts on state changes and periodic health reports.

Built by [DSi](https://dsits.tech).

---

## What It Does

| Function | Description |
|---|---|
| **Keepalive** | Pings each address every `check_interval` seconds (default: 5 min) to keep IPsec tunnels alive |
| **Alerting** | Sends a Slack alert only when a site's status *changes* — no spam |
| **Port checks** | Optionally verifies TCP ports (DICOM 4242, HL7 8201–8203) after a successful ping |
| **Health reports** | Sends a full summary to Slack every `report_interval` seconds (default: 1 hour) |

### Alert Types

- ✅ **UP** — address is reachable (restored after being down)
- 🚨 **DOWN** — address is not responding to ping
- ⚠️ **DEGRADED** — some addresses at a site are up, some are down

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/adamcheech-319/tunnel-monitor.git
cd tunnel-monitor
```

### 2. Configure

```bash
cp config-example-detailed.json config.json
nano config.json
```

Set your Slack webhook URL and add your sites. See [SLACK_SETUP.md](SLACK_SETUP.md) for webhook instructions.

### 3. Deploy (lab)

```bash
chmod +x deploy-lab.sh
./deploy-lab.sh
```

### 4. Deploy (production via docker-compose)

```bash
docker compose -f docker-compose-tunnel-monitor.yml up -d --build
```

---

## Deploy from the published image

No checkout or build needed — pull `ghcr.io/dynamicsecurity-dsi/tunnel-monitor`
the same way you would any other container image. `docker pull` / `docker compose`
fetch **only the image**; the compose file, the config, and the management script
are host-side files you download once (below).

### Prerequisites

- Docker Engine 20.10+ with the Compose plugin (`docker compose version`)
- The host can reach the IPs you want to monitor when the tunnel is up
  (run it on the same box as the Twingate connector / behind the IPsec tunnel)
- A Slack **incoming webhook** URL — see [SLACK_SETUP.md](SLACK_SETUP.md)
- If the GHCR package is private, authenticate first:
  `echo <TOKEN> | docker login ghcr.io -u <github-user> --password-stdin`
  (token needs `read:packages`). Public packages need no login.

### 1. Get the host-side files

```bash
sudo mkdir -p /opt/tunnel-monitor && cd /opt/tunnel-monitor
base=https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/main
curl -O  $base/docker-compose.yml
curl -O  $base/monitor-manage.sh   && chmod +x monitor-manage.sh
curl -o config.json $base/config-example-detailed.json
```

### 2. Configure

Edit `config.json` — set the Slack webhook and add the addresses to monitor.
Either config shape works (see [Configuration](#configuration) and
[MONITORING_GUIDE.md](MONITORING_GUIDE.md)):

```jsonc
// flat
{ "slack_webhook": "https://hooks.slack.com/services/…",
  "check_interval": 300, "report_interval": 3600,
  "sites": [ { "name": "Site A", "addresses": ["10.0.0.5"], "test_ports": [4242] } ] }

// nested (what monitor-manage.sh reads/writes)
{ "check_interval": 300, "report_interval": 3600,
  "slack": { "enabled": true, "webhook": "https://hooks.slack.com/services/…" },
  "vpn_sites": [], "twingate": { "connectors": [] } }
```

`config.json` holds a live webhook — keep it off any public repo (this project's
`.gitignore` already excludes it).

### 3. Start

```bash
docker compose up -d
docker compose logs -f          # expect: "Monitoring N site(s)" then "Sending health report to Slack"
```

or without compose:

```bash
docker run -d --name tunnel-monitor --restart unless-stopped \
  --network host \
  -v /opt/tunnel-monitor/config.json:/app/config.json:ro \
  ghcr.io/dynamicsecurity-dsi/tunnel-monitor:latest
```

### 4. Verify

```bash
docker ps --filter name=tunnel-monitor
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"tunnel-monitor deploy test"}' '<your-webhook-url>'   # expect: ok
```
A health report posts to Slack on startup and then every `report_interval`.

### Day-to-day

| Task | Command |
|---|---|
| Add / edit / remove a site | `./monitor-manage.sh` (interactive menu) |
| Follow logs | `docker compose logs -f` or `docker logs -f tunnel-monitor` |
| Apply a config edit now | not required — config reloads every cycle; `docker compose restart` for immediate effect |
| Update to the latest image | `docker compose pull && docker compose up -d` |
| Pin a version | set `image: ghcr.io/dynamicsecurity-dsi/tunnel-monitor:1.0.0` in `docker-compose.yml` |
| Stop / remove | `docker compose down` |

### Reference

| | |
|---|---|
| **Image** | `ghcr.io/dynamicsecurity-dsi/tunnel-monitor` — tags: `latest`, `sha-<short>`, and `MAJOR.MINOR` / `MAJOR.MINOR.PATCH` on releases |
| **Config** | bind-mount your config file to `/app/config.json` (read-only). Override the in-container path with `CONFIG_PATH`. |
| **Networking** | `--network host` / `network_mode: host` is required so the monitor can ping tunnel & connector IPs directly. There are no ports to publish. |
| **Logs** | `docker logs -f tunnel-monitor`, or mount a volume at `/var/log` and set `LOG_FILE` |
| **Platforms** | `linux/amd64`, `linux/arm64` |
| **`monitor-manage.sh`** | host-side helper — not in the image. Keep it beside `docker-compose.yml` / `config.json`. Override targets with `CONFIG_FILE` / `COMPOSE_FILE` / `CONTAINER` env vars. |

The image is built and published by GitHub Actions
(`.github/workflows/docker-publish.yml`) on every push to `main` and on `v*.*.*`
tags. Cut a release by tagging:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

---

## Configuration

`config.json` schema:

```json
{
  "slack_webhook": "https://hooks.slack.com/services/...",
  "check_interval": 300,
  "report_interval": 3600,
  "sites": [
    {
      "name": "Site Display Name",
      "addresses": ["192.168.X.X"],
      "test_ports": [4242, 8201]
    }
  ]
}
```

| Key | Default | Description |
|---|---|---|
| `slack_webhook` | required | Incoming webhook URL from Slack |
| `check_interval` | `300` | Seconds between ping cycles |
| `report_interval` | `3600` | Seconds between full health reports |
| `sites[].name` | required | Display name for Slack messages |
| `sites[].addresses` | required | List of IPs to monitor at this site |
| `sites[].test_ports` | optional | TCP ports to verify after a successful ping |

Config is reloaded on every check cycle — no restart needed after editing `config.json`.

---

## Logs

```bash
# Follow live logs
docker logs -f tunnel-monitor

# View log file (if using volume mount)
docker exec tunnel-monitor tail -f /var/log/tunnel-monitor.log
```

---

## Docs

- [SLACK_SETUP.md](SLACK_SETUP.md) — How to create a Slack incoming webhook
- [MONITORING_GUIDE.md](MONITORING_GUIDE.md) — Adding sites, tuning intervals, production tips
- [DUAL_PURPOSE.md](DUAL_PURPOSE.md) — Keepalive + monitoring architecture explained

---

## Requirements

- Docker 20.10+
- Network access from the container host to the monitored IPs
- A Slack workspace with an incoming webhook configured

---

## License

MIT
