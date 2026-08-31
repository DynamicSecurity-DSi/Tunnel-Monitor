#!/usr/bin/env bash
# install.sh — set up a tunnel-monitor deployment directory on this host.
#
#   curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/main/install.sh | bash
#
# Options (env vars):
#   DIR   deploy directory        (default /opt/tunnel-monitor)
#   REF   git ref to install from — branch, tag, or SHA (default main)
#
#   # pin a reproducible install to a release:
#   curl -fsSL https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/v1.0.0/install.sh | REF=v1.0.0 bash
#
# What it does:
#   - checks for docker + the compose plugin
#   - creates the deploy directory
#   - downloads the host-side files (docker-compose.yml, monitor-manage.sh) at $REF
#   - writes a placeholder config.json (only if one is not already there)
#   - pulls whatever image the downloaded docker-compose.yml pins
# It does NOT start the container — edit config.json first, then `docker compose up -d`.

set -euo pipefail

REF="${REF:-main}"
REPO_RAW="https://raw.githubusercontent.com/DynamicSecurity-DSi/Tunnel-Monitor/${REF}"
DIR="${DIR:-/opt/tunnel-monitor}"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !\033[0m %s\n'  "$*" >&2; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# --- prerequisites -----------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "docker is not installed / not on PATH"
docker compose version >/dev/null 2>&1 || die "the 'docker compose' plugin is required"

DL=""
command -v curl >/dev/null 2>&1 && DL="curl -fsSL -o"
[ -z "$DL" ] && command -v wget >/dev/null 2>&1 && DL="wget -qO"
[ -z "$DL" ] && die "need curl or wget"

fetch() { $DL "$2" "$REPO_RAW/$1" || die "download failed: $1"; }

# --- deploy directory ------------------------------------------------------
SUDO=""
if [ ! -d "$DIR" ]; then
  say "Creating $DIR"
  mkdir -p "$DIR" 2>/dev/null || { SUDO="sudo"; sudo mkdir -p "$DIR"; }
fi
[ -w "$DIR" ] || SUDO="sudo"
if [ -n "$SUDO" ]; then
  warn "$DIR needs elevated writes; using sudo"
  sudo chown "$(id -un)":"$(id -gn)" "$DIR" 2>/dev/null || true
fi
cd "$DIR" || die "cannot cd to $DIR"

# --- files ---------------------------------------------------------------
say "Downloading host-side files into $DIR (ref: $REF)"
fetch docker-compose.yml docker-compose.yml
fetch monitor-manage.sh  monitor-manage.sh
chmod +x monitor-manage.sh

if [ -e config.json ]; then
  warn "config.json already exists — left untouched"
else
  say "Writing placeholder config.json"
  cat > config.json <<'JSON'
{
  "check_interval": 300,
  "report_interval": 3600,
  "slack": {
    "enabled": true,
    "webhook": "https://hooks.slack.com/services/REPLACE/WITH/YOUR-WEBHOOK"
  },
  "vpn_sites": [],
  "twingate": {
    "connectors": []
  }
}
JSON
fi

# --- image -------------------------------------------------------------
# Pull exactly the image the downloaded compose file pins — single source of truth.
IMAGE="$(sed -n 's/^[[:space:]]*image:[[:space:]]*//p' docker-compose.yml | head -1)"
IMAGE="${IMAGE:-ghcr.io/dynamicsecurity-dsi/tunnel-monitor:latest}"
say "Pulling $IMAGE"
docker pull "$IMAGE" || warn "pull failed now (private package or no network?) — 'docker compose up -d' will retry"

cat <<EOF

$(say "Done. $DIR now contains:")
  docker-compose.yml   config.json   monitor-manage.sh

Next steps:
  1. Edit $DIR/config.json  — set slack.webhook and add sites
       cd $DIR && ./monitor-manage.sh      # or edit the file directly
  2. cd $DIR && docker compose up -d
  3. docker compose logs -f                # expect "Monitoring N site(s)" then a Slack health report

Update later:  cd $DIR && docker compose pull && docker compose up -d
EOF
