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

Subcommands (no subcommand = run the monitor):
    print-example-config              write a skeleton config to stdout
    check-config   [--config PATH]    validate a config file
    add-connector  --name N --ip IP [--ports 4242,8443] [--description D] [--replace]
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
    """Send a periodic health summary to Slack as a formatted report."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = []            # (site, address, status)
    total = up_count = 0
    sites_total = sites_ok = 0

    for site in normalize_sites(config):
        name = site["name"]
        addrs = site.get("addresses", [])
        if not addrs:
            continue
        sites_total += 1
        states = [state.get(f"{name}:{a}", "UNKNOWN") for a in addrs]
        for addr, st in zip(addrs, states):
            rows.append((name, addr, st))
            total += 1
            up_count += (st == "UP")
        if states and all(s == "UP" for s in states):
            sites_ok += 1

    pct = int(round(100 * up_count / total)) if total else 0
    if total == 0:
        status_word, color = "No targets configured", "#8d8d8d"
    elif up_count == total:
        status_word, color = "Operational", "#2eb67d"
    elif up_count == 0:
        status_word, color = "Major outage", "#e01e5a"
    else:
        status_word, color = "Degraded", "#ecb22e"

    # fixed-width table so columns line up in Slack
    w_site = max([len("SITE")] + [len(r[0]) for r in rows])
    w_addr = max([len("ADDRESS")] + [len(r[1]) for r in rows])
    table_lines = [f"{'SITE':<{w_site}}  {'ADDRESS':<{w_addr}}  STATUS"]
    table_lines += [f"{s:<{w_site}}  {a:<{w_addr}}  {st}" for s, a, st in rows]
    table = "```\n" + "\n".join(table_lines) + "\n```" if rows else "```\n(no targets configured)\n```"

    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text", "text": "Tunnel Health Report"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Status*\n{status_word}"},
                    {"type": "mrkdwn", "text": f"*Availability*\n{pct}% ({up_count}/{total} addresses)"},
                    {"type": "mrkdwn", "text": f"*Sites healthy*\n{sites_ok}/{sites_total}"},
                    {"type": "mrkdwn", "text": f"*Generated*\n{ts}"},
                ]},
                {"type": "section", "text": {"type": "mrkdwn", "text": table}},
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": "tunnel-monitor"},
                ]},
            ],
        }]
    }
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


# ---------------------------------------------------------------------------
# CLI subcommands (config scaffolding / validation)
# ---------------------------------------------------------------------------
def build_example_config() -> dict:
    """A minimal nested-schema config, ready to fill in."""
    return {
        "check_interval": 300,
        "report_interval": 3600,
        "slack": {
            "enabled": True,
            "webhook": "https://hooks.slack.com/services/REPLACE/WITH/YOUR-WEBHOOK",
        },
        "vpn_sites": [],
        "twingate": {"connectors": []},
    }


def parse_ports(s: str) -> list:
    """'4242, 8443 8201' -> [4242, 8443, 8201]"""
    out = []
    for part in (s or "").replace(" ", ",").split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out


_PLACEHOLDER_MARKERS = ("REPLACE", "YOUR/WEBHOOK", "YOUR-WEBHOOK", "XXXX", "PLACEHOLDER", "T00000000")


def cmd_print_example() -> int:
    print(json.dumps(build_example_config(), indent=2))
    return 0


def cmd_check_config(path: str) -> int:
    if not os.path.exists(path):
        print(f"ERROR  config file not found: {path}")
        return 1
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR  {path} is not valid JSON: {e}")
        return 1
    except OSError as e:
        print(f"ERROR  cannot read {path}: {e}")
        return 1

    problems = 0
    webhook, enabled = resolve_webhook(config)
    if not enabled:
        print("INFO   Slack notifications disabled (slack.enabled = false)")
    elif not webhook:
        print("ERROR  Slack is enabled but no webhook is set (slack.webhook / slack_webhook)")
        problems += 1
    elif any(m in webhook for m in _PLACEHOLDER_MARKERS):
        print(f"WARN   Slack webhook still looks like a placeholder: {webhook}")

    for key in ("check_interval", "report_interval"):
        val = config.get(key, 300 if key == "check_interval" else 3600)
        if not isinstance(val, int) or val <= 0:
            print(f"ERROR  {key} must be a positive integer (got {val!r})")
            problems += 1

    sites = normalize_sites(config)
    if not sites:
        print("WARN   no sites configured (sites / vpn_sites / twingate.connectors are all empty)")
    for s in sites:
        if not s["addresses"]:
            print(f"ERROR  site '{s['name']}' has no addresses / ip")
            problems += 1
        for p in s["test_ports"]:
            if not isinstance(p, int):
                print(f"ERROR  site '{s['name']}' has a non-integer port: {p!r}")
                problems += 1

    if problems:
        print(f"\n{problems} problem(s) found")
        return 1
    ci = config.get("check_interval", 300)
    ri = config.get("report_interval", 3600)
    print(f"OK     {path}: {len(sites)} site(s), check_interval={ci}s, report_interval={ri}s")
    return 0


def cmd_add_connector(path: str, name: str, ip: str, ports: list,
                      description: str, replace: bool) -> int:
    if os.path.exists(path):
        try:
            with open(path) as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR  {path} is not valid JSON: {e}")
            return 1
        except OSError as e:
            print(f"ERROR  cannot read {path}: {e}")
            return 1
    else:
        config = build_example_config()
        print(f"note   {path} did not exist — creating it from the example")

    connectors = config.setdefault("twingate", {}).setdefault("connectors", [])
    existing = next((c for c in connectors if c.get("name") == name), None)
    if existing and not replace:
        print(f"ERROR  connector '{name}' already exists (pass --replace to overwrite)")
        return 1

    entry = {"name": name, "description": description or name, "ip": ip, "test_ports": ports}
    if existing:
        connectors[connectors.index(existing)] = entry
        action = "replaced"
    else:
        connectors.append(entry)
        action = "added"

    try:
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"ERROR  cannot write {path}: {e}")
        print("       for add-connector the config must be mounted read-write, not :ro")
        return 1

    ports_desc = f"ports {','.join(map(str, ports))}" if ports else "ping only"
    print(f"{action} connector '{name}' ({ip}, {ports_desc}) in {path}")
    return 0


def cli(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="tunnel-monitor-slack.py",
        description="Run the tunnel monitor, or manage its config. "
                    "With no subcommand it runs the monitor loop.",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="run the monitor loop (default)")
    sub.add_parser("print-example-config", help="print a skeleton config to stdout")

    p = sub.add_parser("check-config", help="validate a config file")
    p.add_argument("--config", default=CONFIG_PATH, help=f"config path (default: {CONFIG_PATH})")

    p = sub.add_parser("add-connector", help="add or replace a Twingate connector")
    p.add_argument("--config", default=CONFIG_PATH, help=f"config path (default: {CONFIG_PATH})")
    p.add_argument("--name", required=True)
    p.add_argument("--ip", required=True)
    p.add_argument("--ports", default="", help="comma/space separated TCP ports (optional)")
    p.add_argument("--description", default="")
    p.add_argument("--replace", action="store_true",
                   help="overwrite an existing connector of the same name")

    args = parser.parse_args(argv)

    if args.cmd in (None, "run"):
        main()
        return 0
    if args.cmd == "print-example-config":
        return cmd_print_example()
    if args.cmd == "check-config":
        return cmd_check_config(args.config)
    if args.cmd == "add-connector":
        return cmd_add_connector(args.config, args.name, args.ip,
                                 parse_ports(args.ports), args.description, args.replace)
    parser.print_help()
    return 2


if __name__ == "__main__":
    try:
        sys.exit(cli())
    except KeyboardInterrupt:
        log.info("tunnel-monitor stopped by user")
    except Exception as e:
        log.exception(f"Fatal error: {e}")
        sys.exit(1)
