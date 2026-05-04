#!/usr/bin/env bash
# Initialize local dev environment: register group/device and generate device/config.json.
# Group: dev-group / devpass, Device: deadbeef0101
set -euo pipefail

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
BACKEND_URL="${BACKEND_URL:-http://localhost:9001}"
CONFIG="$(dirname "$0")/../device/config.json"

# Skip if already initialized
if [[ -f "$CONFIG" ]]; then
  EXISTING_KEY=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('api_key',''))" 2>/dev/null || true)
  if [[ -n "$EXISTING_KEY" ]]; then
    echo "init-local: already initialized, skipping."
    exit 0
  fi
fi

echo "Initializing local device via $ENDPOINT ..."

# Retry until backend is ready
BACKEND_READY=0
for i in $(seq 1 20); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/healthz" 2>/dev/null || echo "000")
  if [[ "$STATUS" == "200" ]]; then BACKEND_READY=1; break; fi
  echo "  Waiting for backend ($i/20) ..."
  sleep 2
done
if [[ "$BACKEND_READY" -eq 0 ]]; then
  echo "ERROR: Backend at $BACKEND_URL is not responding after 40s."
  echo "  Start the backend first: cd backend && LOCALSTACK_ENDPOINT=http://localhost:4566 uv run uvicorn --app-dir app main:app --port 9001"
  exit 1
fi

curl -sf -X POST "$BACKEND_URL/api/admin/groups" \
  -H "Content-Type: application/json" \
  -d '{"group_id":"dev-group","group_pw":"devpass"}' \
  && echo "Created group: dev-group" \
  || echo "Group already exists (ok)"

DEVICE_RESP=$(curl -s -X POST "$BACKEND_URL/api/admin/groups/dev-group/devices" \
  -H "Content-Type: application/json" \
  -d '{"dev_id":"deadbeef0101"}' 2>/dev/null || echo "{}")
echo "Registered device: $DEVICE_RESP"

API_KEY=$(echo "$DEVICE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])" 2>/dev/null || true)
THING_NAME=$(echo "$DEVICE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['thing_name'])" 2>/dev/null || true)

# Generate device config.json
if [[ -z "$API_KEY" || -z "$THING_NAME" ]]; then
  echo "ERROR: Device registration failed. Backend response: $DEVICE_RESP"
  echo "  Ensure the backend is running with LOCALSTACK_ENDPOINT=http://localhost:4566"
  exit 1
fi
if [[ -n "$API_KEY" && -n "$THING_NAME" ]]; then
  # Determine WebSocket URL from BACKEND_URL
  WS_URL=$(echo "$BACKEND_URL" | sed 's|^http://|ws://|; s|^https://|wss://|')

  cat > "$CONFIG" <<CONF
{
  "thing_name": "${THING_NAME}",
  "api_key": "${API_KEY}",
  "backend_ws_url": "${WS_URL}/ws/device"
}
CONF
  echo "Generated $CONFIG"
fi

echo "Init complete."
echo "  Login:  group_id=dev-group  group_pw=devpass"
echo "  Device: dev_id=deadbeef0101  thing_name=dev-group:deadbeef0101"
