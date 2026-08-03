from __future__ import annotations

import re
from typing import Literal

from app.models.customer.customer import Customer

CustomerCategory = Literal["lead", "follow_up", "quoted", "won", "vip"]
CategoryUpdateSource = Literal[
    "scoring",
    "repeat_inquiry",
    "quotation_created",
    "quotation_won",
]

CUSTOMER_CATEGORY_PREFIX = "customer-category:"
PROTECTED_SCORING_CATEGORIES = frozenset({"quoted", "won", "vip"})
LEGACY_CATEGORY_ALIASES: dict[str, CustomerCategory] = {
    "潜在客户": "lead",
    "高意向客户": "follow_up",
    "重点跟进": "follow_up",
    "待跟进客户": "follow_up",
    "已报价客户": "quoted",
    "已成交客户": "won",
    "VIP客户": "vip",
    "VIP 客户": "vip",
}


class CustomerCategoryService:
    def update_customer_category(
        self,
        customer: Customer,
        *,
        source: CategoryUpdateSource,
        conversation_history: str = "",
        has_won_history: bool = False,
    ) -> CustomerCategory:
        current = self.get_customer_category(customer)
        if source == "scoring":
            if current in PROTECTED_SCORING_CATEGORIES:
                self._set_customer_category(customer, current)
                return current
            target: CustomerCategory = (
                "follow_up"
                if self._is_follow_up_ready(
                    conversation_history,
                    country_code=customer.country_code,
                )
                else "lead"
            )
        elif source == "repeat_inquiry":
            target = "vip" if current == "vip" or has_won_history else current
        elif source == "quotation_created":
            target = "vip" if current in {"won", "vip"} or has_won_history else "quoted"
        else:
            target = "vip" if current == "vip" or has_won_history else "won"
        self._set_customer_category(customer, target)
        return target

    @staticmethod
    def get_customer_category(customer: Customer) -> CustomerCategory:
        for tag in customer.tags or []:
            if not tag.startswith(CUSTOMER_CATEGORY_PREFIX):
                continue
            value = tag.removeprefix(CUSTOMER_CATEGORY_PREFIX).strip()
            if value in {"lead", "follow_up", "quoted", "won", "vip"}:
                return value  # type: ignore[return-value]
            if value in LEGACY_CATEGORY_ALIASES:
                return LEGACY_CATEGORY_ALIASES[value]
        lifecycle_aliases: dict[str, CustomerCategory] = {
            "new": "lead",
            "qualified": "quoted",
            "customer": "won",
        }
        return lifecycle_aliases.get(customer.lifecycle_stage, "lead")

    @staticmethod
    def _set_customer_category(customer: Customer, category: CustomerCategory) -> None:
        customer.tags = [
            tag
            for tag in (customer.tags or [])
            if not tag.startswith(CUSTOMER_CATEGORY_PREFIX)
        ]
        customer.tags.append(f"{CUSTOMER_CATEGORY_PREFIX}{category}")

    @classmethod
    def _is_follow_up_ready(cls, history: str, *, country_code: str | None) -> bool:
        text = " ".join(history.lower().split())
        return all(
            (
                cls._has_product(text),
                cls._has_quantity(text),
                cls._has_country(text, country_code),
                cls._has_shipping(text),
                cls._has_quotation_request(text),
            )
        )

    @staticmethod
    def _has_product(text: str) -> bool:
        common_products = (
            r"\b(?:hat|hats|cap|caps|jacket|jackets|coat|coats|shirt|shirts|"
            r"shoe|shoes|bag|bags|dress|dresses|product|products|item|items)\b"
        )
        quantity_with_product = (
            r"\b\d[\d,]*(?:\.\d+)?\s*"
            r"(?:pcs?|pieces?|units?|sets?|boxes?|cartons?)\s+"
            r"(?:of\s+)?[a-z][a-z0-9-]*\b"
        )
        return bool(
            re.search(common_products, text)
            or re.search(quantity_with_product, text)
            or re.search(r"产品|帽子|外套|夹克|衬衫|鞋|包|裙|商品|货物", text)
        )

    @staticmethod
    def _has_quantity(text: str) -> bool:
        return bool(
            re.search(
                r"\b\d[\d,]*(?:\.\d+)?\s*"
                r"(?:pcs?|pieces?|units?|sets?|boxes?|cartons?|kg|kgs|tons?)\b",
                text,
            )
            or re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:件|个|套|箱|公斤|千克|吨)", text)
        )

    @staticmethod
    def _has_country(text: str, country_code: str | None) -> bool:
        if country_code and country_code.strip():
            return True
        return bool(
            re.search(r"\bship(?:ping)?\s+to\s+[a-z][a-z .-]{1,40}\b", text)
            or re.search(
                r"\b(?:usa|u\.s\.|united states|uk|united kingdom|france|germany|"
                r"canada|australia|japan|korea|singapore|uae|india|china)\b",
                text,
            )
            or re.search(
                r"美国|英国|法国|德国|加拿大|澳大利亚|日本|韩国|"
                r"新加坡|阿联酋|印度|中国",
                text,
            )
        )

    @staticmethod
    def _has_shipping(text: str) -> bool:
        return bool(
            re.search(
                r"\b(?:ship(?:ping)?\s+to|air freight|sea freight|by air|by sea|"
                r"express|dhl|fedex|ups|fob|cif|ddp|exw|freight)\b",
                text,
            )
            or re.search(r"运输|发货|寄到|空运|海运|快递|物流|到岸|离岸", text)
        )

    @staticmethod
    def _has_quotation_request(text: str) -> bool:
        return bool(
            re.search(
                r"\b(?:need|want|send|provide|request|give|prepare|please)\b"
                r".{0,30}\b(?:quotation|quote)\b",
                text,
            )
            or re.search(r"\b(?:quotation|quote)\s+(?:please|required|needed)\b", text)
            or re.search(r"报价|报个价|正式报价|报价单", text)
        )
