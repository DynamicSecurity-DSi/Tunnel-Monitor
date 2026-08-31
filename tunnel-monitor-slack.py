#!/usr/bin/env python3
"""
tunnel-monitor-slack.py
=======================
Dual-purpose tunnel monitor:
  1. KEEPALIVE  — pings every check_interval seconds to keep IPsec/Twingate tunnels alive
  2. MONITORING — alerts Slack on per-address state changes (UP/DOWN/DEGRADED)
  3. REPORTING  — sends an hourly health summary to Slack

Config: /app/config.json
Accepts either config shape:
  - flat:   {"slack_webhook": "...", "sites": [{"name", "addresses":[ip], "test_ports":[...]}]}
  - nested: {"slack": {"enabled": true, "webhook": "..."},
             "vpn_sites": [{"name", "addresses":[{"ip": "..."}]}],
             "twingate": {"connectors": [{"name", "ip": "...", "test_ports":[...]}]}}
Logs:   /var/log/tunnel-monitor.log
"""

import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/tunnel-monitor.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.json")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _as_ip_list(value) -> list:
    """Coerce an 'addresses'/'ip' value into a flat list of IP strings."""
    out = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                ip = item.get("ip") or item.get("address")
                if ip:
                    out.append(str(ip))
            elif item:
                out.append(str(item))
    elif value:
        out.append(str(value))
    return out


def normalize_sites(config: dict) -> list:
    """
    Flatten the supported config shapes into a common list of:
        {"name": str, "addresses": [ip, ...], "test_ports": [port, ...]}
    """
    sites = []

    for site in config.get("sites", []) or []:
        sites.append({
            "name": site.get("name", "unnamed"),
            "addresses": _as_ip_list(site.get("addresses", [])),
            "test_ports": list(site.get("test_ports", []) or []),
        })

    for site in config.get("vpn_sites", []) or []:
        sites.append({
            "name": site.get("name", "unnamed"),
            "addresses": _as_ip_list(site.get("addresses", [])),
            "test_ports": list(site.get("test_ports", []) or []),
        })

    twingate = config.get("twingate", {}) or {}
    for conn in twingate.get("connectors", []) or []:
        sites.append({
            "name": conn.get("name", "unnamed"),
            "addresses": _as_ip_list(conn.get("ip") or conn.get("addresses", [])),
            "test_ports": list(conn.get("test_ports", []) or []),
        })

    return sites


def resolve_webhook(config: dict) -> tuple:
    """Return (webhook_url, enabled) across the flat and nested config shapes."""
    slack = config.get("slack")
    if isinstance(slack, dict):
        url = slack.get("webhook") or slack.get("webhook_url") or ""
        return url, bool(slack.get("enabled", True))
    return config.get("slack_webhook", "") or "", True


# ---------------------------------------------------------------------------
# Ping / TCP helpers
# ---------------------------------------------------------------------------
def ping(host: str, count: int = 2, timeout: int = 5) -> bool:
    """Return True if host responds to ICMP ping."""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", str(timeout), host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception as e:
        log.warning(f"ping error for {host}: {e}")
        return False


def tcp_check(host: str, port: int, timeout: int = 5) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
def slack_post(webhook_url: str, payload: dict) -> None:
    if not webhook_url:
        log.debug("Slack disabled or no webhook configured; skipping post")
        return
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            log.warning(f"Slack post returned {resp.status_code}: {resp.text}")
    except Exception as e:
        log.warning(f"Slack post failed: {e}")


def send_alert(webhook_url: str, site_name: str, address: str, status: str,
               test_ports: Optional[list] = None, port_results: Optional[dict] = None) -> None:
    """Send a state-change alert to Slack."""
    icons = {"UP": "✅", "DOWN": "🚨", "DEGRADED": "⚠️"}
    colors = {"UP": "#36a64f", "DOWN": "#cc0000", "DEGRADED": "#ffaa00"}
    icon = icons.get(status, "❓")
    color = colors.get(status, "#888888")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fields = [
        {"title": "Address", "value": address, "short": True},
        {"title": "Status", "value": f"{icon} {status}", "short": True},
        {"title": "Time", "value": ts, "short": True},
    ]

    if test_ports and port_results:
        port_lines = []
        for port in test_ports:
            ok = port_results.get(port, False)
            port_lines.append(f"{'✅' if ok else '❌'} TCP {port}")
        fields.append({"title": "Port Checks", "value": "\n".join(port_lines), "short": False})

    payload = {
        "attachments": [{
            "color": color,
            "title": f"{icon} {site_name} — {status}",
            "fields": fields,
            "footer": "tunnel-monitor",
        }]
    }
    slack_post(webhook_url, payload)


def send_health_report(webhook_url: str, state: dict, config: dict) -> None:
    """Send a periodic health summary to Slack."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"*Tunnel Health Report* — {ts}\n"]

    total = 0
    up_count = 0

    for site in normalize_sites(config):
        name = site["name"]
        addrs = site.get("addresses", [])
        site_states = [state.get(f"{name}:{a}", "UNKNOWN") for a in addrs]
        all_up = all(s == "UP" for s in site_states)
        any_up = any(s == "UP" for s in site_states)

        if all_up:
            site_icon = "✅"
            up_count += len(addrs)
        elif any_up:
            site_icon = "⚠️"
            up_count += sum(1 for s in site_states if s == "UP")
        else:
            site_icon = "🚨"

        total += len(addrs)
        addr_lines = []
        for addr, st in zip(addrs, site_states):
            a_icon = "✅" if st == "UP" else ("⚠️" if st == "DEGRADED" else "❌")
            addr_lines.append(f"  {a_icon} {addr} — {st}")
        lines.append(f"{site_icon} *{name}*\n" + "\n".join(addr_lines))

    pct = int(100 * up_count / total) if total else 0
    health_icon = "✅" if pct == 100 else ("⚠️" if pct >= 50 else "🚨")
    lines.append(f"\n{health_icon} Overall health: *{pct}%* ({up_count}/{total} addresses UP)")

    payload = {"text": "\n\n".join(lines)}
    slack_post(webhook_url, payload)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("tunnel-monitor starting up")
    config = load_config()

    webhook_url, slack_enabled = resolve_webhook(config)
    if not slack_enabled:
        log.info("Slack notifications disabled in config")
    elif not webhook_url:
        log.warning("No Slack webhook configured; alerts/reports will be skipped")

    check_interval: int = config.get("check_interval", 300)
    report_interval: int = config.get("report_interval", 3600)

    # per-address state: key = "site_name:address", value = "UP" | "DOWN" | "UNKNOWN"
    state: dict[str, str] = {}
    last_report: float = 0.0

    log.info(f"Monitoring {len(normalize_sites(config))} site(s), "
             f"check_interval={check_interval}s, report_interval={report_interval}s")

    while True:
        config = load_config()  # reload each cycle so config changes take effect without restart
        webhook_url, slack_enabled = resolve_webhook(config)
        if not slack_enabled:
            webhook_url = ""

        for site in normalize_sites(config):
            site_name: str = site["name"]
            addresses: list = site.get("addresses", [])
            test_ports: list = site.get("test_ports", [])

            up_addrs = []
            down_addrs = []

            for addr in addresses:
                key = f"{site_name}:{addr}"
                is_up = ping(addr)

                port_results = {}
                if is_up and test_ports:
                    for port in test_ports:
                        port_results[port] = tcp_check(addr, port)

                new_status = "UP" if is_up else "DOWN"
                old_status = state.get(key, "UNKNOWN")

                if new_status != old_status:
                    log.info(f"{site_name} / {addr}: {old_status} → {new_status}")
                    state[key] = new_status
                    send_alert(webhook_url, site_name, addr, new_status,
                               test_ports if test_ports else None,
                               port_results if port_results else None)
                else:
                    log.debug(f"{site_name} / {addr}: {new_status} (no change)")

                if is_up:
                    up_addrs.append(addr)
                else:
                    down_addrs.append(addr)

            # Update site-level DEGRADED state
            if up_addrs and down_addrs:
                for addr in up_addrs:
                    key = f"{site_name}:{addr}"
                    if state.get(key) != "DEGRADED":
                        state[key] = "DEGRADED"
                        send_alert(webhook_url, site_name, addr, "DEGRADED")

        # Periodic health report
        now = time.time()
        if now - last_report >= report_interval:
            log.info("Sending health report to Slack")
            send_health_report(webhook_url, state, config)
            last_report = now

        time.sleep(check_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("tunnel-monitor stopped by user")
    except Exception as e:
        log.exception(f"Fatal error: {e}")
        sys.exit(1)
