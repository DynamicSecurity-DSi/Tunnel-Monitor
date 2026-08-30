#!/usr/bin/env bash
# deploy-lab.sh
# Quick-deploy script for lab/testing environments.
# Builds the image and starts the container with fast check intervals.
# For production, use docker-compose-tunnel-monitor.yml with config.json tuned to your environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Config check ---
if [ ! -f config.json ]; then
  echo "ERROR: config.json not found. Copy config-example-detailed.json to config.json and fill in your values."
  exit 1
fi

WEBHOOK=$(python3 -c "import json; c=json.load(open('config.json')); print(c.get('slack_webhook',''))" 2>/dev/null || true)
if [[ "$WEBHOOK" == *"YOUR/WEBHOOK"* ]] || [[ -z "$WEBHOOK" ]]; then
  echo "ERROR: slack_webhook in config.json is still a placeholder. Update it before deploying."
  exit 1
fi

echo "==> Building tunnel-monitor image..."
docker build -t tunnel-monitor:latest .

echo "==> Stopping any existing container..."
docker rm -f tunnel-monitor 2>/dev/null || true

echo "==> Starting tunnel-monitor (lab mode)..."
docker run -d \
  --name tunnel-monitor \
  --restart unless-stopped \
  --network host \
  -v "$SCRIPT_DIR/config.json":/app/config.json:ro \
  tunnel-monitor:latest

echo ""
echo "==> Done. Container is running."
echo "    Logs:   docker logs -f tunnel-monitor"
echo "    Stop:   docker rm -f tunnel-monitor"
echo "    Status: docker ps | grep tunnel-monitor"
