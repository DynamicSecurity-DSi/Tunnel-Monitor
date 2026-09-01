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

Deploys the prebuilt image from GHCR. Runs on any host with Docker + the Compose
plugin that can reach your target IPs when the tunnel is up.

### 1. Bootstrap

```bash
curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/v1.0.1/install.sh | REF=v1.0.1 bash
```

Creates `/opt/tunnel-monitor/` with `docker-compose.yml`, `monitor-manage.sh`, and
a placeholder `config.json`, and pulls the image. It does **not** start the
container. (Drop `REF` and use the `main` URL to track the latest build instead.)

### 2. Configure

```bash
cd /opt/tunnel-monitor
nano config.json
```

Set **`slack.webhook`** and add **at least one site** — a webhook alone monitors
nothing. Either config shape works (see [Configuration](#configuration)):

```jsonc
{
  "check_interval": 300,
  "report_interval": 3600,
  "slack": { "enabled": true, "webhook": "https://hooks.slack.com/services/…" },
  "vpn_sites": [],
  "twingate": {
    "connectors": [
      { "name": "Site A", "ip": "192.168.10.5", "test_ports": [4242, 8201] }
    ]
  }
}
```

`./monitor-manage.sh` gives a menu for adding/editing sites (it does not set the
webhook — edit that in the file). See [SLACK_SETUP.md](SLACK_SETUP.md) to create
the webhook.

### 3. Start

```bash
docker compose up -d
docker compose logs -f      # expect "Monitoring N site(s)" then "Sending health report to Slack"
```

Upgrade later: bump the image tag in `docker-compose.yml`, then
`docker compose pull && docker compose up -d`.

### Build from source instead

```bash
git clone https://github.com/DynamicSecurity-DSi/Tunnel-Monitor.git
cd Tunnel-Monitor
cp config-example-detailed.json config.json   # then edit it
docker compose -f docker-compose-tunnel-monitor.yml up -d --build
```

---

## Deploy from the published image

More detail on the above — `docker run`, the container subcommands, pinning, and
what lives on the host vs. in the image.

No checkout or build needed — pull `ghcr.io/dynamicsecurity-dsi/tunnel-monitor`
the same way you would any other container image. `docker pull` / `docker compose`
fetch **only the image**; the compose file, the config, and the management script
are host-side files you download once (below).

**What goes where:** a host needs only `docker-compose.yml`, `config.json`, and
(optionally) `monitor-manage.sh`, together in one directory — `/opt/tunnel-monitor`
in the examples below. `tunnel-monitor-slack.py`, `Dockerfile`, and
`requirements.txt` are baked into the image; never copy them to a host.

### Quick install

```bash
# latest (tracks main)
curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/main/install.sh | bash

# pinned to a release (reproducible: host files + image all from the tag)
curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/v1.0.1/install.sh | REF=v1.0.1 bash

# custom location
curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/main/install.sh | DIR=/srv/tunnel-monitor bash
```

`install.sh` checks for Docker, creates `/opt/tunnel-monitor`, downloads
`docker-compose.yml` + `monitor-manage.sh` at `REF` (default `main`), writes a
placeholder `config.json` (never overwriting an existing one), and pulls whatever
image the downloaded `docker-compose.yml` pins. It does **not** start the
container — edit `config.json`, then `docker compose up -d`. The manual
equivalent is steps 1–3 below.

### Prerequisites

- Docker Engine 20.10+ with the Compose plugin (`docker compose version`)
- The host can reach the IPs you want to monitor when the tunnel is up
  (run it on the same box as the Twingate connector / behind the IPsec tunnel)
- A Slack **incoming webhook** URL — see [SLACK_SETUP.md](SLACK_SETUP.md)
- If the GHCR package is private, authenticate first:
  `echo <TOKEN> | docker login ghcr.io -u <github-user> --password-stdin`
  (token needs `read:packages`). Public packages need no login.

### 1. Get the host-side files

Three files live on the host next to each other — none of them are in the image:

| File | Purpose | Source |
|---|---|---|
| `docker-compose.yml` | how the container runs | repo |
| `config.json` | your webhook + sites (bind-mounted read-only into the container) | copy of `config-example-detailed.json`, or the skeleton `install.sh` writes |
| `monitor-manage.sh` | optional host-side menu to edit `config.json` / restart | repo |

```bash
sudo mkdir -p /opt/tunnel-monitor && cd /opt/tunnel-monitor
base=https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/main
curl -O  $base/docker-compose.yml
curl -O  $base/monitor-manage.sh   && chmod +x monitor-manage.sh
curl -o config.json $base/config-example-detailed.json
```

### 2. Configure

Open `config.json` **on the host** (`nano config.json`, or `./monitor-manage.sh`
for a menu) — set the Slack webhook and add the addresses to monitor. Either
config shape works (see [Configuration](#configuration) and
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
| Pin a version | set `image: ghcr.io/dynamicsecurity-dsi/tunnel-monitor:1.0.1` in `docker-compose.yml` |
| Stop / remove | `docker compose down` |

### Container subcommands

The image can also scaffold and validate its own config — no host script needed.
With no subcommand it runs the monitor (the default).

```bash
img=ghcr.io/dynamicsecurity-dsi/tunnel-monitor:latest

# write a skeleton config
docker run --rm $img print-example-config > config.json

# validate a config (exit 0 = ok, 1 = problems); reads /app/config.json by default
docker run --rm -v "$PWD/config.json:/app/config.json:ro" $img check-config

# add / replace a Twingate connector (mount read-write — no :ro)
docker run --rm -v "$PWD/config.json:/app/config.json" $img \
  add-connector --name DSi-DICOM --ip 10.0.0.9 --ports 4242,8443
docker run --rm -v "$PWD/config.json:/app/config.json" $img \
  add-connector --name DSi-EdgeNode --ip 192.168.24.21          # ping-only
```

`--config PATH` overrides the target on `check-config` / `add-connector`;
`add-connector` takes `--description` and `--replace`, and creates the file from
the skeleton if it doesn't exist.

### Reference

| | |
|---|---|
| **Image** | `ghcr.io/dynamicsecurity-dsi/tunnel-monitor` — tags: `latest`, `sha-<short>`, and `MAJOR.MINOR` / `MAJOR.MINOR.PATCH` on releases |
| **Config** | bind-mount your config file to `/app/config.json` (read-only). Override the in-container path with `CONFIG_PATH`. |
| **Networking** | `--network host` / `network_mode: host` is required so the monitor can ping tunnel & connector IPs directly. There are no ports to publish. |
| **Logs** | `docker logs -f tunnel-monitor`, or mount a volume at `/var/log` and set `LOG_FILE` |
| **Platforms** | `linux/amd64`, `linux/arm64` |
| **`monitor-manage.sh`** | host-side helper — not in the image. Keep it beside `docker-compose.yml` / `config.json`. Override targets with `CONFIG_FILE` / `COMPOSE_FILE` / `CONTAINER` env vars. |
| **`install.sh`** | one-shot bootstrap: `curl -fsSL <raw>/install.sh \| bash`. Fetches the host-side files at `REF` (default `main`) + the image the compose file pins, into `DIR` (default `/opt/tunnel-monitor`). Does not start the container. |

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

- [CHANGELOG.md](CHANGELOG.md) — Release notes
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
