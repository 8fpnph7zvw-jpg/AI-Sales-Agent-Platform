from __future__ import annotations

import json
import logging
import re
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer.customer import Customer
from app.models.customer.customer_score import CustomerScore
from app.modules.lead_score.repository import LeadScoreRepository
from app.services.customer_category_service import CustomerCategoryService
from app.services.dify_scoring_service import DifyScoringInput, DifyScoringService
from app.services.feishu_service import FeishuService

logger = logging.getLogger(__name__)

class LeadScoringOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        repository: LeadScoreRepository,
        dify: DifyScoringService,
        feishu: FeishuService,
    ) -> None:
        self.session = session
        self.repository = repository
        self.dify = dify
        self.feishu = feishu
        self.customer_category = CustomerCategoryService()

    async def score_customer(
        self,
        customer: Customer,
        *,
        product_requirement: str | None = None,
        quantity: str | None = None,
    ) -> CustomerScore:
        messages = await self.repository.recent_messages(customer.tenant_id, customer.id)
        chat_history = "\n".join(
            f"{message.sender_type}: {message.content_text or ''}" for message in messages
        )
        customer_history = "\n".join(
            message.content_text or ""
            for message in messages
            if message.sender_type == "customer"
        )
        last_customer_message = next(
            (
                message.content_text or ""
                for message in reversed(messages)
                if message.sender_type == "customer"
            ),
            "",
        )
        product = (product_requirement or last_customer_message).strip()
        result = await self.dify.run(
            DifyScoringInput(
                chat_history=chat_history,
                customer_profile=json.dumps(
                    {
                        "name": customer.name,
                        "company": customer.company_name,
                        "email": customer.email,
                        "phone": customer.phone_e164,
                        "country": customer.country_code,
                        "tags": customer.tags,
                    },
                    ensure_ascii=False,
                ),
                product_requirement=product,
                quantity=(quantity or self._infer_quantity(last_customer_message)).strip(),
                country=customer.country_code or "",
                user=customer.public_id,
            )
        )
        score = CustomerScore(
            tenant_id=customer.tenant_id,
            customer_id=customer.id,
            score=result.score,
            level=result.level,
            need_follow=result.need_follow,
            reason=result.reason,
        )
        self.repository.add_score(score)
        customer.intent_score = Decimal(result.score)
        customer.intent_level = result.level
        customer.score_explanation = {
            "source": "dify_workflow",
            "need_follow": result.need_follow,
            "reason": result.reason,
        }
        self.customer_category.update_customer_category(
            customer,
            source="scoring",
            conversation_history=customer_history,
        )
        if last_customer_message:
            self.customer_category.update_customer_category(
                customer,
                source="repeat_inquiry",
                has_won_history=await self.repository.has_won_quotation(
                    customer.tenant_id,
                    customer.id,
                ),
            )
        await self.session.commit()
        await self.session.refresh(score)

        if result.score >= 80 and result.need_follow and customer.owner_user_id:
            profile = await self.repository.sales_profile(
                customer.tenant_id, customer.owner_user_id
            )
            if profile and profile.feishu_open_id:
                try:
                    await self.feishu.send_message(
                        profile.feishu_open_id,
                        self._notification_text(
                            customer,
                            product,
                            quantity or self._infer_quantity(last_customer_message),
                            score,
                        ),
                    )
                except Exception:
                    logger.exception(
                        "feishu_high_intent_notification_failed tenant_id=%s customer_id=%s",
                        customer.tenant_id,
                        customer.public_id,
                    )
        return score

    @staticmethod
    def _infer_quantity(message: str) -> str:
        match = re.search(
            r"\b(\d[\d,]*(?:\.\d+)?)\s*(pcs?|pieces?|units?|sets?|个|件|套)\b",
            message,
            flags=re.IGNORECASE,
        )
        return match.group(0) if match else ""

    @staticmethod
    def _notification_text(
        customer: Customer,
        product: str,
        quantity: str,
        score: CustomerScore,
    ) -> str:
        return (
            "🔥 高意向客户提醒\n\n"
            f"客户：{customer.name}\n"
            f"产品：{product or '未识别'}\n"
            f"数量：{quantity or '未识别'}\n"
            f"国家：{customer.country_code or '未填写'}\n"
            f"评分：{score.score}\n"
            f"等级：{score.level}\n"
            f"原因：{score.reason}\n\n"
            "请及时跟进。"
        )
