# Dual Purpose: Keepalive + Monitoring

tunnel-monitor was designed to solve two problems at once.

---

## Problem 1: IPsec Tunnels Need Keepalives

IPsec tunnels (and some Twingate edge nodes) drop their SA (Security Association) when idle. Most firewalls have a DPD (Dead Peer Detection) timeout — if no traffic flows for that period, the tunnel tears down and must renegotiate on the next packet, causing a delay or failed connection.

**Solution:** tunnel-monitor pings each site address every `check_interval` seconds. Even if no application traffic is flowing, the pings keep the tunnel alive and prevent SA expiry.

For a Cisco RV345 with DPD at 600 seconds, setting `check_interval: 300` pings every 5 minutes — well within the DPD window.

---

## Problem 2: Tunnel Failures Need to Be Detected

A dropped tunnel is silent — no application sends an alert, the modality just times out, and nobody knows until a clinician calls. Traditional monitoring polls a central server; tunnel monitoring needs to work from the inside out.

**Solution:** tunnel-monitor tracks per-address state independently. When ping fails, it immediately fires a Slack alert. When it recovers, it sends a recovery alert. State is tracked in memory so repeated failures don't spam Slack — only transitions trigger alerts.

---

## How They Work Together

```
Every check_interval seconds:
  for each site:
    for each address:
      ping(address)
        → success: keepalive achieved; if was DOWN, send ✅ UP alert
        → failure: if was UP, send 🚨 DOWN alert
      if test_ports configured and ping succeeded:
        tcp_check(address, port) for each port

Every report_interval seconds:
  send full health summary to Slack
```

The ping that serves as a keepalive is the same ping that drives monitoring. One process, two outcomes.

---

## Why Not Just Use a Monitoring Tool?

Tools like Zabbix, Prometheus, or Uptime Kuma are great but:

- They require a server outside the tunnel to monitor the tunnel endpoint
- They don't serve as keepalives
- They add infrastructure complexity

tunnel-monitor is a single container, a JSON config file, and a Slack webhook. It runs on the same host as the Twingate connector or alongside the Preventi AI stack on pv-docker-01, with no external dependencies.
