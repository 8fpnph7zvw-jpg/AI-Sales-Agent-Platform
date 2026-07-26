"""Import every model so SQLAlchemy and Alembic receive complete metadata."""

from app.models.ai.ai_agent_run import AiAgentRun
from app.models.ai.prompt import Prompt
from app.models.auth.auth_session import AuthSession
from app.models.auth.permission import Permission
from app.models.auth.role import Role
from app.models.auth.role_permission import RolePermission
from app.models.auth.tenant import Tenant
from app.models.auth.user import User
from app.models.auth.user_role import UserRole
from app.models.connector.connector import Connector
from app.models.connector.connector_config import ConnectorConfig
from app.models.connector.webhook_log import WebhookLog
from app.models.conversation.conversation import Conversation
from app.models.conversation.message import Message
from app.models.customer.customer import Customer
from app.models.customer.customer_session import CustomerSession
from app.models.notification.notification import Notification
from app.models.quotation.product import Product
from app.models.quotation.quotation import Quotation
from app.models.quotation.quotation_item import QuotationItem
from app.models.rag.embedding import Embedding
from app.models.rag.knowledge_chunk import KnowledgeChunk
from app.models.rag.knowledge_collection import KnowledgeCollection
from app.models.rag.knowledge_document import KnowledgeDocument
from app.models.rag.knowledge_file import KnowledgeFile
from app.models.system.audit_log import AuditLog
from app.models.system.outbox_event import OutboxEvent
from app.models.system.system_config import SystemConfig
from app.models.workflow.workflow import Workflow
from app.models.workflow.workflow_node import WorkflowNode

__all__ = [
    "AiAgentRun",
    "AuditLog",
    "AuthSession",
    "Connector",
    "ConnectorConfig",
    "Conversation",
    "Customer",
    "CustomerSession",
    "Embedding",
    "KnowledgeChunk",
    "KnowledgeCollection",
    "KnowledgeDocument",
    "KnowledgeFile",
    "Message",
    "Notification",
    "OutboxEvent",
    "Permission",
    "Product",
    "Prompt",
    "Quotation",
    "QuotationItem",
    "Role",
    "RolePermission",
    "SystemConfig",
    "Tenant",
    "User",
    "UserRole",
    "WebhookLog",
    "Workflow",
    "WorkflowNode",
]
