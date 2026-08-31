#!/usr/bin/env bash
# monitor-manage.sh
# Management wrapper for the tunnel monitor (production).
# Thin convenience layer over `docker compose` + `docker logs` — see README.md and
# MONITORING_GUIDE.md for the underlying commands and configuration details.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-monitor-prod.yml}"
CONFIG_FILE="${CONFIG_FILE:-config-prod.json}"
CONTAINER="tunnel-monitor"

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

usage() {
  cat <<EOF
Usage: ./monitor-manage.sh <command>

Commands:
  up | deploy     Build the image and start the monitor (compose up -d --build)
  down            Stop and remove the monitor container
  restart         Restart the running container (config also reloads automatically each cycle)
  rebuild         Rebuild the image and force-recreate the container
  status          Show container status
  logs            Follow container logs (Ctrl-C to stop)
  config-check    Check that ${CONFIG_FILE} exists, is valid JSON, and has a real webhook
  test-slack      Post a test message to the webhook in ${CONFIG_FILE}
  help            Show this help

Environment overrides: COMPOSE_FILE, CONFIG_FILE
EOF
}

get_webhook() {
  python3 -c "import json,sys; print(json.load(open('${CONFIG_FILE}')).get('slack_webhook',''))"
}

config_check() {
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: ${CONFIG_FILE} not found."
    exit 1
  fi
  if ! python3 -c "import json; json.load(open('${CONFIG_FILE}'))" 2>/dev/null; then
    echo "ERROR: ${CONFIG_FILE} is not valid JSON."
    exit 1
  fi
  local webhook
  webhook="$(get_webhook)"
  if [ -z "$webhook" ] || [[ "$webhook" == *PLACEHOLDER* ]] || [[ "$webhook" == *"YOUR/WEBHOOK"* ]]; then
    echo "WARNING: slack_webhook in ${CONFIG_FILE} is empty or still a placeholder."
    return 1
  fi
  echo "OK: ${CONFIG_FILE} is valid and has a webhook configured."
}

test_slack() {
  local webhook
  webhook="$(get_webhook)"
  if [ -z "$webhook" ] || [[ "$webhook" == *PLACEHOLDER* ]]; then
    echo "ERROR: no real slack_webhook in ${CONFIG_FILE}."
    exit 1
  fi
  curl -fsS -X POST -H 'Content-type: application/json' \
    --data '{"text":"tunnel-monitor: test message from monitor-manage.sh"}' \
    "$webhook" && echo " -> sent"
}

cmd="${1:-help}"
case "$cmd" in
  up|deploy)      config_check || echo "(continuing despite config warning)"; compose up -d --build ;;
  down)          compose down ;;
  restart)       docker restart "$CONTAINER" ;;
  rebuild)       compose up -d --build --force-recreate ;;
  status)        docker ps --filter "name=${CONTAINER}" ;;
  logs)          docker logs -f "$CONTAINER" ;;
  config-check)  config_check ;;
  test-slack)    test_slack ;;
  help|-h|--help) usage ;;
  *)             echo "Unknown command: ${cmd}"; echo; usage; exit 1 ;;
esac
