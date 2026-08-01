# WhatsApp Connector

Node.js gateway between `whatsapp-web.js` and the FastAPI application. It keeps
browser authentication in `sessions/` through `LocalAuth`; session contents must
never be committed.

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
