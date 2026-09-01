# Changelog

All notable changes to this project are recorded here. Releases are cut by
pushing a `v*.*.*` tag; GitHub Actions then builds and publishes
`ghcr.io/dynamicsecurity-dsi/tunnel-monitor` with `MAJOR.MINOR.PATCH`,
`MAJOR.MINOR`, and `latest` tags.

## [1.0.1] - 2026-09-01

### Changed

- **Health report reformatted** for a cleaner, more formal look: a colored
  attachment bar (green *Operational* / amber *Degraded* / red *Major outage*),
  a header, a Status / Availability / Sites-healthy / Generated field grid, and a
  fixed-width `SITE / ADDRESS / STATUS` table. Emoji removed. State-change alerts
  are unchanged.
- `docker-compose.yml` pinned to `:1.0.1`.

## [1.0.0] - 2026-08-31

First tagged release.

### Image

- `ghcr.io/dynamicsecurity-dsi/tunnel-monitor` — tags `1.0.0`, `1.0`, `latest`,
  and `sha-<commit>`
- Platforms: `linux/amd64`, `linux/arm64`
- Built and published by GitHub Actions on every push to `main` and every
  `v*.*.*` tag

### Features

- **Keepalive + monitoring in one pass** — the same ping that keeps a tunnel's SA
  alive drives UP / DOWN / DEGRADED detection. Alerts fire only on a state change.
- **Optional per-site TCP port checks** (e.g. DICOM 4242, HL7 8201–8203) after a
  successful ping.
- **Periodic Slack health report** (`report_interval`, default 1h).
- **Two config schemas, auto-detected:**
  - flat — `slack_webhook`, `sites[]`
  - nested — `slack.webhook` / `slack.enabled`, `vpn_sites[]`,
    `twingate.connectors[]`
  - `config.json` is reloaded every cycle — edits apply with no restart.
- **Container subcommands** (`ENTRYPOINT`-based; no subcommand runs the monitor):
  - `print-example-config` — write a skeleton config to stdout
  - `check-config [--config PATH]` — validate; exit 1 on problems
  - `add-connector --name --ip [--ports] [--description] [--replace] [--config PATH]`
- **`monitor-manage.sh`** — interactive host-side menu: view / add / edit / remove
  sites, restart, logs.
- **`install.sh`** — one-shot host bootstrap. `REF` selects the git ref (default
  `main`); the image is read from the downloaded `docker-compose.yml`.
- **`docker-compose.yml`** — image-only deploy (host networking, json-file log
  rotation), pinned to `:1.0.0`.

### Deploy

```bash
# latest
curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/main/install.sh | bash

# pinned to this release (host files + image both from v1.0.0)
curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/v1.0.0/install.sh | REF=v1.0.0 bash
```

### Notes

- Requires Docker Engine 20.10+ with the Compose plugin.
- Run it where the host can reach the monitored IPs when the tunnel is up
  (beside the Twingate connector / behind the IPsec tunnel).
- `config.json` holds a live webhook and is git-ignored — never commit it.

[1.0.1]: https://github.com/DynamicSecurity-DSi/Tunnel-Monitor/releases/tag/v1.0.1
[1.0.0]: https://github.com/DynamicSecurity-DSi/Tunnel-Monitor/releases/tag/v1.0.0
