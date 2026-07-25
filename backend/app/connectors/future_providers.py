"""Catalog metadata only; these are not platform API implementations."""

from typing import Any

FUTURE_PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "key": "whatsapp",
        "name": "WhatsApp Business",
        "category": "messaging",
        "description": "面向客户会话、模板消息与媒体消息的未来适配器。",
        "availability": "planned",
        "capabilities": [
            "receive_messages",
            "send_messages",
            "text",
            "media",
            "delivery_receipts",
            "webhooks",
        ],
        "config_schema": {
            "fields": [
                {"key": "business_account_id", "label": "Business Account ID", "type": "text"},
                {"key": "phone_number_id", "label": "Phone Number ID", "type": "text"},
            ]
        },
    },
    {
        "key": "amazon",
        "name": "Amazon",
        "category": "marketplace",
        "description": "面向订单、买家消息和履约事件的未来适配器。",
        "availability": "planned",
        "capabilities": ["orders", "events", "webhooks"],
        "config_schema": {
            "fields": [
                {"key": "seller_id", "label": "Seller ID", "type": "text"},
                {"key": "marketplace_id", "label": "Marketplace ID", "type": "text"},
                {"key": "region", "label": "Region", "type": "text"},
            ]
        },
    },
    {
        "key": "alibaba",
        "name": "Alibaba",
        "category": "marketplace",
        "description": "面向询盘、订单和贸易事件的未来适配器。",
        "availability": "planned",
        "capabilities": ["receive_messages", "orders", "events", "webhooks"],
        "config_schema": {
            "fields": [
                {"key": "merchant_id", "label": "Merchant ID", "type": "text"},
                {"key": "site", "label": "Site", "type": "text"},
            ]
        },
    },
]
