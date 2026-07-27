#!/bin/sh
set -eu

umask 077

OPENWA_BASE_URL="${OPENWA_BASE_URL:-http://openwa:2785/api}"
OPENWA_KEY_FILE="${OPENWA_KEY_FILE:-/openwa-data/.api-key}"
OPENWA_RUNTIME_DIR="${OPENWA_RUNTIME_DIR:-/runtime}"
PROJECT_ENV_FILE="${PROJECT_ENV_FILE:-/workspace/.env}"
OPENWA_SESSION_NAME="${OPENWA_SESSION_NAME:-ai-sales-agent}"
OPENWA_SESSION_REQUESTED="${OPENWA_SESSION:-}"
OPENWA_WEBHOOK_URL="${OPENWA_WEBHOOK_URL:-http://backend:8000/api/v1/webhooks/whatsapp}"
OPENWA_INIT_TIMEOUT_SECONDS="${OPENWA_INIT_TIMEOUT_SECONDS:-180}"
BACKEND_UID="${BACKEND_UID:-10001}"
BACKEND_GID="${BACKEND_GID:-10001}"
configured_api_key="${OPENWA_API_KEY:-}"

log() {
  printf '%s\n' "[openwa-init] $*"
}

fail() {
  printf '%s\n' "[openwa-init] ERROR: $*" >&2
  exit 1
}

case "$OPENWA_SESSION_NAME" in
  *[!A-Za-z0-9-]*|"")
    fail "OPENWA_SESSION_NAME must contain only letters, numbers, and hyphens"
    ;;
esac

name_length="${#OPENWA_SESSION_NAME}"
if [ "$name_length" -lt 3 ] || [ "$name_length" -gt 50 ]; then
  fail "OPENWA_SESSION_NAME must be between 3 and 50 characters"
fi

mkdir -p "$OPENWA_RUNTIME_DIR"

if [ -s "$OPENWA_KEY_FILE" ]; then
  openwa_api_key="$(tr -d '\r\n' < "$OPENWA_KEY_FILE")"
elif [ -n "$configured_api_key" ]; then
  openwa_api_key="$configured_api_key"
else
  elapsed=0
  while [ ! -s "$OPENWA_KEY_FILE" ]; do
    if [ "$elapsed" -ge "$OPENWA_INIT_TIMEOUT_SECONDS" ]; then
      fail "OpenWA did not create $OPENWA_KEY_FILE within ${OPENWA_INIT_TIMEOUT_SECONDS}s"
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  openwa_api_key="$(tr -d '\r\n' < "$OPENWA_KEY_FILE")"
fi
if [ "${#openwa_api_key}" -lt 24 ]; then
  fail "OpenWA generated API key is unexpectedly short"
fi

curl --fail --silent --show-error \
  --request POST \
  --header "X-API-Key: $openwa_api_key" \
  --output /dev/null \
  "$OPENWA_BASE_URL/auth/validate"

sessions_file="$(mktemp)"
create_file="$(mktemp)"
webhooks_file="$(mktemp)"
payload_file="$(mktemp)"
env_file_tmp="$(mktemp)"
trap 'rm -f "$sessions_file" "$create_file" "$webhooks_file" "$payload_file" "$env_file_tmp"' EXIT

curl --fail --silent --show-error \
  --header "X-API-Key: $openwa_api_key" \
  --output "$sessions_file" \
  "$OPENWA_BASE_URL/sessions"

openwa_session_id="$(
  node -e '
    const fs = require("fs");
    const [file, requested, name] = process.argv.slice(1);
    const sessions = JSON.parse(fs.readFileSync(file, "utf8"));
    const match = sessions.find((item) => item.id === requested)
      || sessions.find((item) => item.name === requested)
      || sessions.find((item) => item.name === name);
    if (match?.id) process.stdout.write(String(match.id));
  ' "$sessions_file" "$OPENWA_SESSION_REQUESTED" "$OPENWA_SESSION_NAME"
)"

if [ -z "$openwa_session_id" ]; then
  printf '{"name":"%s"}' "$OPENWA_SESSION_NAME" > "$payload_file"
  curl --fail --silent --show-error \
    --request POST \
    --header "X-API-Key: $openwa_api_key" \
    --header "Content-Type: application/json" \
    --data-binary "@$payload_file" \
    --output "$create_file" \
    "$OPENWA_BASE_URL/sessions"
  openwa_session_id="$(
    node -e '
      const fs = require("fs");
      const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
      if (value?.id) process.stdout.write(String(value.id));
    ' "$create_file"
  )"
  [ -n "$openwa_session_id" ] || fail "OpenWA session creation returned no session ID"
  log "created OpenWA session $OPENWA_SESSION_NAME"
else
  log "using existing OpenWA session $OPENWA_SESSION_NAME"
fi

curl --fail --silent --show-error \
  --header "X-API-Key: $openwa_api_key" \
  --output "$webhooks_file" \
  "$OPENWA_BASE_URL/sessions/$openwa_session_id/webhooks"

openwa_webhook_id="$(
  node -e '
    const fs = require("fs");
    const [file, url] = process.argv.slice(1);
    const hooks = JSON.parse(fs.readFileSync(file, "utf8"));
    const match = hooks.find((item) => item.url === url);
    if (match?.id) process.stdout.write(String(match.id));
  ' "$webhooks_file" "$OPENWA_WEBHOOK_URL"
)"

OPENWA_INIT_API_KEY="$openwa_api_key" \
OPENWA_INIT_WEBHOOK_URL="$OPENWA_WEBHOOK_URL" \
node -e '
  const fs = require("fs");
  const payload = {
    url: process.env.OPENWA_INIT_WEBHOOK_URL,
    events: ["message.received"],
    secret: process.env.OPENWA_INIT_API_KEY,
    retryCount: 3,
  };
  fs.writeFileSync(process.argv[1], JSON.stringify(payload), { mode: 0o600 });
' "$payload_file"

if [ -n "$openwa_webhook_id" ]; then
  node -e '
    const fs = require("fs");
    const [source, destination] = process.argv.slice(1);
    const payload = JSON.parse(fs.readFileSync(source, "utf8"));
    payload.active = true;
    fs.writeFileSync(destination, JSON.stringify(payload), { mode: 0o600 });
  ' "$payload_file" "$create_file"
  curl --fail --silent --show-error \
    --request PUT \
    --header "X-API-Key: $openwa_api_key" \
    --header "Content-Type: application/json" \
    --data-binary "@$create_file" \
    --output /dev/null \
    "$OPENWA_BASE_URL/sessions/$openwa_session_id/webhooks/$openwa_webhook_id"
  log "updated OpenWA webhook"
else
  curl --fail --silent --show-error \
    --request POST \
    --header "X-API-Key: $openwa_api_key" \
    --header "Content-Type: application/json" \
    --data-binary "@$payload_file" \
    --output /dev/null \
    "$OPENWA_BASE_URL/sessions/$openwa_session_id/webhooks"
  log "registered OpenWA webhook"
fi

write_runtime_value() {
  destination="$1"
  value="$2"
  temporary="$(mktemp "$OPENWA_RUNTIME_DIR/.openwa-runtime.XXXXXX")"
  printf '%s' "$value" > "$temporary"
  chown "$BACKEND_UID:$BACKEND_GID" "$temporary"
  chmod 0400 "$temporary"
  mv -f "$temporary" "$destination"
}

write_runtime_value "$OPENWA_RUNTIME_DIR/openwa_api_key" "$openwa_api_key"
write_runtime_value "$OPENWA_RUNTIME_DIR/openwa_session" "$openwa_session_id"

env_existed=false
if [ -f "$PROJECT_ENV_FILE" ]; then
  env_existed=true
  awk \
    -v api_key="$openwa_api_key" \
    -v session_id="$openwa_session_id" \
    -v session_name="$OPENWA_SESSION_NAME" '
      BEGIN { key_written = 0; session_written = 0; name_written = 0 }
      /^OPENWA_API_KEY=/ {
        if (!key_written) print "OPENWA_API_KEY=" api_key
        key_written = 1
        next
      }
      /^OPENWA_SESSION=/ {
        if (!session_written) print "OPENWA_SESSION=" session_id
        session_written = 1
        next
      }
      /^OPENWA_SESSION_NAME=/ {
        if (!name_written) print "OPENWA_SESSION_NAME=" session_name
        name_written = 1
        next
      }
      { print }
      END {
        if (!key_written) print "OPENWA_API_KEY=" api_key
        if (!session_written) print "OPENWA_SESSION=" session_id
        if (!name_written) print "OPENWA_SESSION_NAME=" session_name
      }
    ' "$PROJECT_ENV_FILE" > "$env_file_tmp"
else
  printf 'OPENWA_API_KEY=%s\nOPENWA_SESSION=%s\nOPENWA_SESSION_NAME=%s\n' \
    "$openwa_api_key" \
    "$openwa_session_id" \
    "$OPENWA_SESSION_NAME" > "$env_file_tmp"
fi

cat "$env_file_tmp" > "$PROJECT_ENV_FILE"
chmod 0600 "$PROJECT_ENV_FILE"

if [ "$env_existed" = false ]; then
  workspace_owner="$(stat -c '%u:%g' /workspace 2>/dev/null || true)"
  if [ -n "$workspace_owner" ]; then
    chown "$workspace_owner" "$PROJECT_ENV_FILE" 2>/dev/null || true
  fi
fi

key_prefix="$(printf '%.12s' "$openwa_api_key")"
log "API key ${key_prefix}... synchronized to runtime secret and project .env"
log "OpenWA initialization completed"
