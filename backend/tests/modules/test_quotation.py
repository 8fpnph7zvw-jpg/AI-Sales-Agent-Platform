from decimal import Decimal

from app.modules.quotation.service import QuotationService


def test_money_rounds_to_mysql_scale() -> None:
    assert QuotationService._money(Decimal("12.34567")) == Decimal("12.3457")
    assert QuotationService._money(Decimal("12.34565")) == Decimal("12.3457")
