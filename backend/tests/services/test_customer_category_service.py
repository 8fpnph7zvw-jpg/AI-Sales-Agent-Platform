from __future__ import annotations

import logging

import pytest

from app.models.customer.customer import Customer
from app.services.customer_category_service import CustomerCategoryService


def make_customer(category: str = "potential") -> Customer:
    return Customer(
        id=42,
        public_id="01J00000000000000000000000",
        tenant_id=1,
        name="Test Customer",
        lifecycle_stage="new",
        country_code=None,
        tags=["whatsapp", f"customer-category:{category}"],
    )


def test_price_only_inquiry_remains_potential(caplog: pytest.LogCaptureFixture) -> None:
    customer = make_customer()
    caplog.set_level(logging.INFO)

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="scoring",
        conversation_history="How much this hat?",
    )

    assert category == "potential"
    assert customer.tags == ["whatsapp", "customer-category:potential"]
    assert "category_update_started" in caplog.text
    assert "category_updated" in caplog.text
    assert "reason=incomplete_purchase_context" in caplog.text


@pytest.mark.parametrize("destination", ["Ship to USA", "Shipping USA", "USA address"])
def test_destination_without_shipping_method_remains_potential(destination: str) -> None:
    customer = make_customer()

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="scoring",
        conversation_history=f"Need 1000 hats. {destination}. Please quote.",
    )

    assert category == "potential"
    assert customer.tags == ["whatsapp", "customer-category:potential"]


def test_complete_purchase_context_becomes_follow_up() -> None:
    customer = make_customer()

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="scoring",
        conversation_history=(
            "Need 1000 hats. Ship to USA. By sea. Please quote."
        ),
    )

    assert category == "follow_up"
    assert customer.tags == ["whatsapp", "customer-category:follow_up"]


def test_repeat_inquiry_after_historical_win_becomes_vip() -> None:
    customer = make_customer("customer")

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="repeat_inquiry",
        has_won_history=True,
    )

    assert category == "vip"
    assert customer.tags == ["whatsapp", "customer-category:vip"]


@pytest.mark.parametrize(
    ("protected_category", "reason"),
    [
        ("quoted", "already_quoted"),
        ("customer", "already_customer"),
        ("vip", "already_vip"),
    ],
)
def test_scoring_does_not_overwrite_protected_category(
    protected_category: str,
    reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    customer = make_customer(protected_category)
    caplog.set_level(logging.INFO)

    category = CustomerCategoryService().update_customer_category(
        customer,
        source="scoring",
        conversation_history=(
            "Need 1000 hats. Ship to USA. By sea. Please quote."
        ),
    )

    assert category == protected_category
    assert customer.tags == ["whatsapp", f"customer-category:{protected_category}"]
    assert "category_update_skipped" in caplog.text
    assert f"reason={reason}" in caplog.text
