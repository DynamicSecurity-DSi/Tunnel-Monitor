# Monitoring Guide

## Adding a New Site

Edit `config.json` and add a new entry to the `sites` array:

```json
{
  "name": "Northside Radiology",
  "addresses": [
    "192.168.10.5"
  ],
  "test_ports": [4242, 8201]
}
```

No restart needed — config is reloaded every check cycle.

---

## Addresses to Monitor

The `addresses` list should contain IPs that are reachable from the Docker host when the tunnel is healthy:

| Scenario | What to monitor |
|---|---|
| Twingate connector | LAN IP of the on-site connector host |
| IPsec tunnel | Tunnel endpoint or a LAN host behind the tunnel |
| Both | Include both — each generates independent alerts |

---

## Port Checks (`test_ports`)

Optional TCP port checks run after a successful ping. Use these to verify that services are actually listening, not just that the host is reachable.

| Port | Service |
|---|---|
| `4242` | Orthanc DICOM |
| `8042` | Orthanc HTTP/REST |
| `8201` | Mirth HL7 channel (site-specific) |
| `8202` | Mirth HL7 channel (site-specific) |
| `8203` | Mirth HL7 channel (site-specific) |
| `8443` | Mirth Connect Web UI |

Remove `test_ports` entirely if you only want ping-based monitoring.

---

## Tuning Intervals

| Setting | Lab | Production |
|---|---|---|
| `check_interval` | `60` (1 min) | `300` (5 min) |
| `report_interval` | `300` (5 min) | `3600` (1 hour) |

For IPsec keepalive, `check_interval` should be shorter than the tunnel's DPD timeout. For Cisco RV345 with DPD at 600 seconds, 300 seconds gives a comfortable margin.

---

## Viewing Logs

```bash
# Live container stdout
docker logs -f tunnel-monitor

# Log file inside container
docker exec tunnel-monitor tail -f /var/log/tunnel-monitor.log
```

Log entries:
- `INFO` — state changes and health reports
- `DEBUG` — every ping result (verbose, off by default in production)
- `WARNING` — Slack post failures, ping errors (non-fatal)
- `ERROR` / `CRITICAL` — fatal errors that stop the monitor

---

## Restarting After Config Change

Config reloads automatically each cycle. For immediate effect:

```bash
docker restart tunnel-monitor
```

---

## Running Alongside Other Containers

tunnel-monitor uses `network_mode: host` so it can reach tunnel IPs directly. This is compatible with other containers on the same host as long as they don't also use host networking for conflicting ports.

To add tunnel-monitor to an existing `docker-compose.yml`:

```yaml
  tunnel-monitor:
    image: tunnel-monitor:latest
    build:
      context: ./tunnel-monitor
    container_name: tunnel-monitor
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./tunnel-monitor/config.json:/app/config.json:ro
      - tunnel-monitor-logs:/var/log
```

---

## Alerting Behavior

- Alerts fire **only on state change** — a host that stays DOWN does not spam Slack
- When a host recovers, a ✅ UP alert is sent
- DEGRADED fires when some (not all) addresses at a site are down
- Health reports send on the `report_interval` schedule regardless of state
