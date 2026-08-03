# Feishu Open Platform integration

The backend integrates with Feishu through `app.integrations.feishu`. Credentials stay on the
server and must never be exposed through frontend environment variables.

## 1. Create a Feishu application

1. Sign in to the [Feishu Open Platform](https://open.feishu.cn/).
2. Create an enterprise self-built application.
3. Enable the bot capability for the application.
4. Publish a version and make the application available to the intended tenant/users.
5. Copy the App ID and App Secret from **Credentials & Basic Info**.

## 2. Required permission

Grant the application the following permission and publish a new application version:

- `im:message:send_as_bot`

The receiving user must be within the application's availability scope. The test endpoint uses a
Feishu `open_id` and sends a direct text message as the application bot.

## 3. Configure environment variables

Copy `.env.example` to `.env` and set:

```dotenv
FEISHU_ENABLED=true
FEISHU_APP_ID=your_feishu_app_id
FEISHU_APP_SECRET=your_feishu_app_secret
```

`FEISHU_ENABLED` defaults to `false`. Do not commit a populated `.env` file. Restart/rebuild the
backend after changing its environment.

## 4. Test the connector

Call the administrator-only endpoint with a token that has `connector.manage` or
`connector.secret_manage`:

```bash
curl -X POST "https://your-host/api/v1/connectors/feishu/test" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"open_id":"ou_xxxxx","message":"测试消息"}'
```

Successful response:

```json
{"success": true}
```

The client caches `tenant_access_token` in memory, refreshes it before expiry, and retries once when
Feishu reports an invalid token.

## Future sales-account binding design

No database change or migration is included in this integration. A future implementation can add
`user_feishu_accounts` with:

| Field | Suggested type | Notes |
| --- | --- | --- |
| `id` | BIGINT UNSIGNED | Internal primary key |
| `user_id` | BIGINT UNSIGNED | Unique foreign key to `users.id` |
| `feishu_open_id` | VARCHAR(128) | Tenant-scoped message receiver ID |
| `union_id` | VARCHAR(128) NULL | Cross-application identity when available |
| `created_at` | DATETIME(6) | Creation timestamp |
| `updated_at` | DATETIME(6) | Update timestamp |

Recommended constraints are a unique key on `user_id`, a tenant-appropriate uniqueness policy for
`feishu_open_id`, and `ON DELETE CASCADE` or an explicit account-unbind workflow. Secrets do not
belong in this table.

## Lead scoring notification integration

`NotificationService.notify_sales()` is the channel abstraction. Feishu is its first adapter; Email
and SMS adapters can be added without changing lead scoring. Automatic Feishu delivery remains
disabled while `FEISHU_ENABLED=false`.
