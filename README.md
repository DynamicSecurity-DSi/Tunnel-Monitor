# tunnel-monitor

A lightweight Docker container that monitors IPsec VPN tunnels and Twingate connectors via ping and optional TCP port checks. Sends Slack alerts on state changes and periodic health reports.

Built for the [Preventi AI](https://preventiAI.com) infrastructure by [DSi](https://dsits.tech).

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
