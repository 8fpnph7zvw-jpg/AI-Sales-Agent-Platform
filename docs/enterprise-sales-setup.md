# Enterprise sales setup

## Database

Run the normal Alembic upgrade before starting the upgraded API:

```bash
cd backend
alembic upgrade head
```

Revision `20260802_0008` creates `sales_profiles` and `customer_scores`, adds the
sales score-read permission, creates the `admin` and `sales` system roles for
existing tenants, and soft-deletes stale duplicate WhatsApp connector rows.

## Dify applications

Keep the existing Customer Service application as an **Agent** and keep its App
API key in `DIFY_API_KEY`. Its responsibilities remain chat, recommendations,
knowledge retrieval, and automatic replies.

Create a separate Dify application with type **Workflow** for lead scoring. Its
Start node must accept these string inputs:

- `chat_history`
- `customer_profile`
- `product_requirement`
- `quantity`
- `country`

The End node must expose either the four output fields directly or one JSON
string field named `result`, `output`, `text`, or `json`:

```json
{
  "score": 90,
  "level": "A",
  "need_follow": true,
  "reason": "Customer has clear purchase intention"
}
```

The backend validates the score range and enforces levels A=90-100, B=70-89,
C=40-69, and D=0-39. Configure the Workflow App API key separately:

```dotenv
DIFY_SCORING_API_BASE_URL=https://api.dify.ai/v1
DIFY_SCORING_API_KEY=
DIFY_SCORING_TIMEOUT_SECONDS=30
```

## Feishu

Create an internal Feishu app, enable bot/message permissions, publish it to the
tenant, then configure backend-only credentials:

```dotenv
FEISHU_API_BASE_URL=https://open.feishu.cn
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_TIMEOUT_SECONDS=15
```

Use the admin User Management page to bind each sales account to one
`feishu_open_id`, then assign customers to that sales account. Dify never calls
Feishu directly: the FastAPI scoring workflow calls `FeishuService` only when
`score >= 80` and `need_follow` is true.

Scoring or notification failures are logged after the WhatsApp customer-service
reply succeeds and do not change a successful WhatsApp webhook into a failure.
