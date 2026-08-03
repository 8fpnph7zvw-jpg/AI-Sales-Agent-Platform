from __future__ import annotations

import pytest

from app.models.customer.customer import Customer
from app.services.customer_category_service import CustomerCategoryService


def make_customer(category: str = "lead") -> Customer:
    return Customer(
        id=42,
        public_id="01J00000000000000000000000",
        tenant_id=1,
        name="Test Customer",
        lifecycle_stage="new",
        country_code=None,
        tags=["whatsapp", f"customer-category:{category}"],
    )


def test_price_only_inquiry_remains_lead() -> None:
    customer = make_customer()

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="scoring",
        conversation_history="customer: How much this hat?",
    )

    assert category == "lead"
    assert customer.tags == ["whatsapp", "customer-category:lead"]


def test_complete_purchase_context_becomes_follow_up() -> None:
    customer = make_customer()

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="scoring",
        conversation_history=(
            "customer: Need 1000 pcs hats. Ship to USA. Need quotation."
        ),
    )

    assert category == "follow_up"
    assert customer.tags == ["whatsapp", "customer-category:follow_up"]


def test_repeat_inquiry_after_historical_win_becomes_vip() -> None:
    customer = make_customer("won")

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="repeat_inquiry",
        has_won_history=True,
    )

    assert category == "vip"
    assert customer.tags == ["whatsapp", "customer-category:vip"]


@pytest.mark.parametrize("protected_category", ["quoted", "won", "vip"])
def test_scoring_does_not_overwrite_protected_category(
    protected_category: str,
) -> None:
    customer = make_customer(protected_category)

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="scoring",
        conversation_history=(
            "customer: Need 1000 pcs hats. Ship to USA. Need quotation."
        ),
    )

    assert category == protected_category
    assert customer.tags == ["whatsapp", f"customer-category:{protected_category}"]
