from fastapi import APIRouter

from app.modules.ai_agent.router import router as ai_agent_router
from app.modules.auth.router import router as auth_router
from app.modules.connector.router import router as connector_router
from app.modules.conversation.router import management_router as conversation_management_router
from app.modules.conversation.router import router as conversation_router
from app.modules.customer.router import router as customer_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.lead_score.router import router as lead_score_router
from app.modules.notification.router import router as notification_router
from app.modules.quotation.router import router as quotation_router
from app.modules.workflow.router import router as workflow_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(customer_router)
api_router.include_router(conversation_router)
api_router.include_router(conversation_management_router)
api_router.include_router(ai_agent_router)
api_router.include_router(lead_score_router)
api_router.include_router(quotation_router)
api_router.include_router(connector_router)
api_router.include_router(notification_router)
api_router.include_router(knowledge_router)
api_router.include_router(workflow_router)
