# WhatsApp Connector

Node.js gateway between `whatsapp-web.js` and the FastAPI application. It keeps
browser authentication in `sessions/` through `LocalAuth`; session contents must
never be committed.

Each ID is isolated as `sessions/session-{sessionId}`. On startup the gateway
logs every stored profile, its Chromium lock files, whether it is the historical
default session, and whether it will be restored. Stored non-default sessions
are restored by default. `customer001` is not restored unless explicitly
enabled, so a historical test profile cannot start alongside a formal session.

Relevant lifecycle settings:

- `WHATSAPP_AUTO_RESTORE_SESSIONS=true` restores stored formal sessions.
- `WHATSAPP_AUTO_RESTORE_DEFAULT_SESSION=false` keeps the default/test session stopped.
- `WHATSAPP_READY_TIMEOUT_MS=120000` bounds the authenticated-to-ready phase.
- `WHATSAPP_READY_RETRY_LIMIT=1` restarts the Client once with the same LocalAuth profile.
- `WHATSAPP_BROWSER_SHUTDOWN_TIMEOUT_MS=10000` bounds graceful Chromium shutdown.
- `WHATSAPP_PROFILE_UNLOCK_TIMEOUT_MS=5000` prevents reconnect from opening a still-locked profile.

No profile is deleted during discovery or recovery. If `ready` is not emitted,
the gateway logs WhatsApp socket state, WWebJS injection state, page state,
Chromium PID/version, and profile locks before performing the bounded retry.
The WhatsApp Web version cache is stored at
`sessions/.wwebjs_cache` (`WHATSAPP_WEB_VERSION_CACHE_PATH`) because the gateway
runs as an unprivileged user and the package default `./.wwebjs_cache` is outside
the writable session directory. Cache persistence happens between
`authenticated` and `ready`, so an unwritable default path can stop that exact
lifecycle transition.

## Local development

1. Copy `.env.example` to `.env` and set matching `BACKEND_API_TOKEN` / FastAPI
   `WHATSAPP_GATEWAY_TOKEN` values. FastAPI resolves the connector from the
   forwarded `session_id`; the gateway does not own a fixed connector ID.
2. Use the provided dependency installer so the upstream development-only Husky
   hook is skipped without changing the submodule, then start:

   - PowerShell: `npm.cmd run install:dependencies; npm.cmd start`
   - Bash: `npm run install:dependencies && npm start`
3. Use the authenticated FastAPI `/connectors/whatsapp/{id}/web-session/*`
   endpoints. Node gateway routes are internal service-to-service APIs.

The FastAPI URL must include its API prefix, for example
`http://localhost:8000/api/v1`.

## LID-aware replies

For each inbound one-to-one message, the gateway remembers the actual
`message.from` / `chat.id` returned by WhatsApp. Automatic replies use that ID
directly, including `@lid` IDs, instead of constructing `{phone}@c.us`. If an
outbound request has no in-memory inbound mapping, the gateway resolves the
number with whatsapp-web.js and then requests its LID/phone identity pair before
sending. The `/api/whatsapp/send` request contract remains unchanged.
