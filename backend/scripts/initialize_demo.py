from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import password_hasher
from app.db.session import AsyncSessionLocal, dispose_engine
from app.models.auth.permission import Permission
from app.models.auth.role import Role
from app.models.auth.role_permission import RolePermission
from app.models.auth.tenant import Tenant
from app.models.auth.user import User
from app.models.auth.user_role import UserRole
from app.models.connector.connector import Connector
from app.models.customer.customer import Customer
from app.models.quotation.product import Product
from app.models.quotation.quotation import Quotation
from app.models.quotation.quotation_item import QuotationItem
from app.models.rag.embedding import Embedding
from app.models.rag.knowledge_chunk import KnowledgeChunk
from app.models.rag.knowledge_collection import KnowledgeCollection
from app.models.rag.knowledge_document import KnowledgeDocument
from app.models.workflow.workflow import Workflow
from app.models.workflow.workflow_node import WorkflowNode
from app.modules.knowledge.embedding import EmbeddingService

TENANT_NAME = "AI Sales Demo"
TENANT_SLUG = "demo"
ADMIN_EMAIL = "admin@test.com"
DEFAULT_ADMIN_PASSWORD = "Admin@2026"
OWNER_ROLE_CODE = "owner"

CUSTOMERS: tuple[dict[str, Any], ...] = (
    {
        "name": "ABC Electronics",
        "company_name": "ABC Electronics",
        "email": "buyer@abc-electronics.test",
        "country_code": "US",
        "language": "en",
        "intent_score": Decimal("82"),
        "intent_level": "high",
        "tags": ["demo", "electronics", "high-intent"],
    },
    {
        "name": "Amazon Buyer Test",
        "company_name": "Amazon Buyer Test",
        "email": "amazon-buyer@test.com",
        "country_code": "US",
        "language": "en",
        "intent_score": Decimal("68"),
        "intent_level": "medium",
        "tags": ["demo", "amazon"],
    },
    {
        "name": "European Importer",
        "company_name": "European Importer",
        "email": "buyer@european-importer.test",
        "country_code": "DE",
        "language": "en",
        "intent_score": Decimal("45"),
        "intent_level": "medium",
        "tags": ["demo", "europe", "importer"],
    },
)

CONNECTORS: tuple[dict[str, Any], ...] = (
    {
        "provider": "whatsapp",
        "name": "WhatsApp",
        "capabilities": [
            "receive_messages",
            "send_messages",
            "text",
            "media",
            "delivery_receipts",
            "webhooks",
        ],
    },
    {
        "provider": "alibaba",
        "name": "Alibaba",
        "capabilities": ["inquiries", "messages"],
    },
    {
        "provider": "amazon",
        "name": "Amazon",
        "capabilities": ["buyer-messages", "orders"],
    },
    {
        "provider": "feishu",
        "name": "Feishu",
        "capabilities": ["notifications", "messages"],
    },
)

PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "sku": "DEMO-WE-001",
        "name": "Wireless Earphone",
        "description": "Bluetooth 5.3 wireless earphone with charging case.",
        "category": "Consumer Electronics",
        "base_price": Decimal("12.90"),
        "min_order_qty": Decimal("100"),
        "attributes": {"color": ["black", "white"], "warranty_months": 12},
    },
    {
        "sku": "DEMO-SW-001",
        "name": "Smart Watch",
        "description": "Fitness smart watch with heart-rate and sleep monitoring.",
        "category": "Wearables",
        "base_price": Decimal("24.50"),
        "min_order_qty": Decimal("50"),
        "attributes": {"display": "1.9 inch", "warranty_months": 12},
    },
    {
        "sku": "DEMO-UC-001",
        "name": "USB Charger",
        "description": "20W USB-C fast charger with international plug options.",
        "category": "Accessories",
        "base_price": Decimal("5.80"),
        "min_order_qty": Decimal("200"),
        "attributes": {"power_watts": 20, "plug": ["US", "EU", "UK"]},
    },
)

KNOWLEDGE_DOCUMENTS: tuple[tuple[str, str], ...] = (
    (
        "产品介绍.md",
        "产品介绍\n"
        "Wireless Earphone 支持 Bluetooth 5.3 并配充电盒。"
        "Smart Watch 支持心率和睡眠监测。USB Charger 支持 20W USB-C 快充。",
    ),
    (
        "价格规则.md",
        "价格规则\n"
        "产品价格以美元计价。批量订单可申请阶梯折扣：500 件以上 3%，"
        "1000 件以上 5%。最终价格以销售审批后的报价单为准。",
    ),
    (
        "运输方式.md",
        "运输方式\n"
        "样品可使用 DHL、FedEx 或 UPS。批量订单支持空运和海运，"
        "可按 FOB、CIF 或 DDP 条款报价。交期通常为确认订单后 15 至 30 天。",
    ),
    (
        "售后政策.md",
        "售后政策\n"
        "产品提供 12 个月有限质保。质量问题请在收货后 7 天内提供订单号、"
        "批次号、照片或视频，销售团队将在 2 个工作日内响应。",
    ),
)

WORKFLOW_NAME = "客户询盘 AI 跟进"
WORKFLOW_NODES: tuple[dict[str, Any], ...] = (
    {
        "node_key": "customer_inquiry",
        "node_type": "trigger",
        "name": "客户询盘",
        "config": {"event": "inquiry.received"},
        "position": {"x": 80, "y": 160},
    },
    {
        "node_key": "ai_auto_reply",
        "node_type": "ai_agent",
        "name": "AI自动回复",
        "config": {"action": "agent.reply", "knowledge_collection": "产品FAQ"},
        "position": {"x": 320, "y": 160},
    },
    {
        "node_key": "intent_scoring",
        "node_type": "lead_score",
        "name": "意向评分",
        "config": {"action": "lead_score.calculate"},
        "position": {"x": 560, "y": 160},
    },
    {
        "node_key": "notify_sales",
        "node_type": "condition_notification",
        "name": "高意向通知销售",
        "config": {"condition": "intent_score >= 80", "channel": "feishu"},
        "position": {"x": 800, "y": 160},
    },
)


async def _upsert_tenant(session: AsyncSession) -> Tenant:
    tenant = await session.scalar(
        select(Tenant).where(Tenant.slug == TENANT_SLUG).with_for_update()
    )
    if tenant is None:
        tenant = Tenant(
            name=TENANT_NAME,
            slug=TENANT_SLUG,
            status="active",
            timezone="Asia/Shanghai",
            default_currency="USD",
        )
        session.add(tenant)
        await session.flush()
    else:
        tenant.name = TENANT_NAME
        tenant.status = "active"
        tenant.deleted_at = None
    return tenant


async def _upsert_admin(session: AsyncSession, tenant: Tenant) -> User:
    role = await session.scalar(
        select(Role)
        .where(Role.tenant_id == tenant.id, Role.code == OWNER_ROLE_CODE)
        .with_for_update()
    )
    if role is None:
        role = Role(
            tenant_id=tenant.id,
            code=OWNER_ROLE_CODE,
            name="Owner",
            description="Tenant owner with full access.",
            is_system=True,
        )
        session.add(role)
        await session.flush()

    permission_ids = set((await session.scalars(select(Permission.id))).all())
    if not permission_ids:
        raise RuntimeError("Permission catalog is empty; run database migrations first.")
    assigned_ids = set(
        (
            await session.scalars(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            )
        ).all()
    )
    session.add_all(
        RolePermission(role_id=role.id, permission_id=permission_id)
        for permission_id in permission_ids - assigned_ids
    )

    user = await session.scalar(
        select(User)
        .where(User.tenant_id == tenant.id, User.email == ADMIN_EMAIL)
        .with_for_update()
    )
    if user is None:
        password = os.getenv("DEMO_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
        user = User(
            tenant_id=tenant.id,
            email=ADMIN_EMAIL,
            password_hash=password_hasher.hash(password),
            display_name="Administrator",
            status="active",
            locale="zh-CN",
            timezone="Asia/Shanghai",
        )
        session.add(user)
        await session.flush()
    else:
        user.status = "active"
        user.deleted_at = None

    link = await session.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    if link is None:
        session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    return user


async def _upsert_customers(
    session: AsyncSession, tenant: Tenant, admin: User
) -> dict[str, Customer]:
    result: dict[str, Customer] = {}
    for values in CUSTOMERS:
        customer = await session.scalar(
            select(Customer).where(
                Customer.tenant_id == tenant.id,
                Customer.source_type == "demo_seed",
                Customer.source_ref == values["name"],
            )
        )
        if customer is None:
            customer = await session.scalar(
                select(Customer).where(
                    Customer.tenant_id == tenant.id,
                    Customer.name == values["name"],
                )
            )
        if customer is None:
            customer = Customer(tenant_id=tenant.id, name=values["name"])
            session.add(customer)
        for key, value in values.items():
            setattr(customer, key, value)
        customer.lifecycle_stage = "qualified"
        customer.source_type = "demo_seed"
        customer.source_ref = values["name"]
        customer.owner_user_id = admin.id
        customer.created_by = admin.id
        customer.consent_status = "granted"
        customer.notes = "Enterprise demo customer generated by initialize_demo.py."
        customer.deleted_at = None
        result[values["name"]] = customer
    await session.flush()
    return result


async def _upsert_connectors(
    session: AsyncSession, tenant: Tenant, admin: User
) -> dict[str, Connector]:
    result: dict[str, Connector] = {}
    for values in CONNECTORS:
        connector = await session.scalar(
            select(Connector).where(
                Connector.tenant_id == tenant.id,
                Connector.provider == values["provider"],
                Connector.external_account_id == "demo-template",
            )
        )
        if connector is None:
            connector = Connector(
                tenant_id=tenant.id,
                provider=values["provider"],
                external_account_id="demo-template",
            )
            session.add(connector)
        connector.name = values["name"]
        connector.status = "disabled"
        connector.capabilities = values["capabilities"]
        connector.health_status = None
        connector.health_detail = {
            "template": True,
            "message": "Demo template only; no external API is connected.",
        }
        connector.created_by = admin.id
        connector.deleted_at = None
        result[values["provider"]] = connector
    await session.flush()
    return result


async def _upsert_workflow(session: AsyncSession, tenant: Tenant, admin: User) -> None:
    workflow = await session.scalar(
        select(Workflow).where(
            Workflow.tenant_id == tenant.id,
            Workflow.name == WORKFLOW_NAME,
            Workflow.version == 1,
        )
    )
    edges = [
        {"source": WORKFLOW_NODES[index]["node_key"], "target": node["node_key"]}
        for index, node in enumerate(WORKFLOW_NODES[1:])
    ]
    if workflow is None:
        workflow = Workflow(
            tenant_id=tenant.id,
            name=WORKFLOW_NAME,
            trigger_type="customer_inquiry",
            version=1,
        )
        session.add(workflow)
        await session.flush()
    workflow.trigger_type = "customer_inquiry"
    workflow.status = "draft"
    workflow.definition = {
        "description": "客户询盘后由 AI 回复、评分，并在高意向时通知销售。",
        "nodes": [node["node_key"] for node in WORKFLOW_NODES],
        "edges": edges,
        "demo_template": True,
    }
    workflow.created_by = admin.id
    workflow.updated_by = admin.id
    workflow.deleted_at = None

    existing = {
        node.node_key: node
        for node in (
            await session.scalars(
                select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id)
            )
        ).all()
    }
    for order, values in enumerate(WORKFLOW_NODES):
        node = existing.get(values["node_key"])
        if node is None:
            node = WorkflowNode(
                tenant_id=tenant.id,
                workflow_id=workflow.id,
                node_key=values["node_key"],
            )
            session.add(node)
        node.node_type = values["node_type"]
        node.name = values["name"]
        node.config = values["config"]
        node.position = values["position"]
        node.sort_order = order


async def _upsert_knowledge(session: AsyncSession, tenant: Tenant, admin: User) -> None:
    collection = await session.scalar(
        select(KnowledgeCollection).where(
            KnowledgeCollection.tenant_id == tenant.id,
            KnowledgeCollection.name == "产品FAQ",
        )
    )
    embedder = EmbeddingService(get_settings().rag_embedding_dimensions)
    if collection is None:
        collection = KnowledgeCollection(
            tenant_id=tenant.id,
            name="产品FAQ",
        )
        session.add(collection)
        await session.flush()
    collection.description = "企业 Demo 产品、价格、运输和售后知识。"
    collection.embedding_provider = embedder.model
    collection.status = "active"
    collection.created_by = admin.id
    collection.deleted_at = None

    now = datetime.now(UTC)
    for filename, content in KNOWLEDGE_DOCUMENTS:
        encoded = content.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        document = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant.id,
                KnowledgeDocument.collection_id == collection.id,
                KnowledgeDocument.filename == filename,
            )
        )
        if document is None:
            document = KnowledgeDocument(
                tenant_id=tenant.id,
                collection_id=collection.id,
                filename=filename,
                mime_type="text/markdown",
                size_bytes=len(encoded),
                sha256=digest,
                uploaded_by=admin.id,
            )
            session.add(document)
            await session.flush()
        document.mime_type = "text/markdown"
        document.size_bytes = len(encoded)
        document.sha256 = digest
        document.status = "ready"
        document.chunk_count = 1
        document.error_message = None
        document.processed_at = now

        chunk = await session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.chunk_index == 0,
            )
        )
        if chunk is None:
            chunk = KnowledgeChunk(
                tenant_id=tenant.id,
                document_id=document.id,
                chunk_index=0,
                content_text=content,
                content_hash=digest,
            )
            session.add(chunk)
            await session.flush()
        chunk.content_text = content
        chunk.content_hash = digest
        chunk.token_count = len(content.split())
        chunk.metadata_json = {"filename": filename, "demo_seed": True}
        chunk.sync_status = "ready"

        vector = embedder.embed(content)
        embedding = await session.scalar(select(Embedding).where(Embedding.chunk_id == chunk.id))
        if embedding is None:
            embedding = Embedding(
                tenant_id=tenant.id,
                chunk_id=chunk.id,
                model=embedder.model,
                dimensions=len(vector),
                vector=vector,
            )
            session.add(embedding)
        embedding.model = embedder.model
        embedding.dimensions = len(vector)
        embedding.vector = vector
        embedding.vector_metadata = {
            "document_id": document.public_id,
            "demo_seed": True,
        }


async def _upsert_products(
    session: AsyncSession, tenant: Tenant
) -> dict[str, Product]:
    result: dict[str, Product] = {}
    for values in PRODUCTS:
        product = await session.scalar(
            select(Product).where(
                Product.tenant_id == tenant.id,
                Product.sku == values["sku"],
            )
        )
        if product is None:
            product = Product(tenant_id=tenant.id, sku=values["sku"])
            session.add(product)
        for key, value in values.items():
            setattr(product, key, value)
        product.unit = "pcs"
        product.currency = "USD"
        product.status = "active"
        product.deleted_at = None
        result[values["sku"]] = product
    await session.flush()
    return result


async def _upsert_quotation_template(
    session: AsyncSession,
    tenant: Tenant,
    admin: User,
    customers: dict[str, Customer],
    products: dict[str, Product],
) -> None:
    quotation = await session.scalar(
        select(Quotation).where(
            Quotation.tenant_id == tenant.id,
            Quotation.quotation_no == "DEMO-TEMPLATE-001",
        )
    )
    if quotation is None:
        quotation = Quotation(
            tenant_id=tenant.id,
            quotation_no="DEMO-TEMPLATE-001",
            customer_id=customers["ABC Electronics"].id,
            currency="USD",
        )
        session.add(quotation)
        await session.flush()
    quotation.customer_id = customers["ABC Electronics"].id
    quotation.status = "draft"
    quotation.currency = "USD"
    quotation.valid_until = None
    quotation.incoterm = "FOB"
    quotation.payment_terms = "30% deposit, 70% before shipment"
    quotation.notes = "Enterprise demo quotation template. Copy and adjust before sending."
    quotation.created_by = admin.id
    quotation.shipping_amount = Decimal("150.0000")

    quantities = {
        "DEMO-WE-001": Decimal("100"),
        "DEMO-SW-001": Decimal("50"),
        "DEMO-UC-001": Decimal("200"),
    }
    existing_items = {
        item.sku_snapshot: item
        for item in (
            await session.scalars(
                select(QuotationItem).where(QuotationItem.quotation_id == quotation.id)
            )
        ).all()
    }
    subtotal = Decimal("0")
    for order, values in enumerate(PRODUCTS):
        product = products[values["sku"]]
        quantity = quantities[product.sku]
        line_total = quantity * product.base_price
        item = existing_items.get(product.sku)
        if item is None:
            item = QuotationItem(
                quotation_id=quotation.id,
                sku_snapshot=product.sku,
                name_snapshot=product.name,
                quantity=quantity,
                unit=product.unit,
                unit_price=product.base_price,
                line_total=line_total,
            )
            session.add(item)
        item.product_id = product.id
        item.sku_snapshot = product.sku
        item.name_snapshot = product.name
        item.description = product.description
        item.quantity = quantity
        item.unit = product.unit
        item.unit_price = product.base_price
        item.discount_rate = Decimal("0")
        item.tax_rate = Decimal("0")
        item.line_total = line_total
        item.sort_order = order
        subtotal += line_total
    quotation.subtotal = subtotal
    quotation.discount_amount = Decimal("0")
    quotation.tax_amount = Decimal("0")
    quotation.total_amount = subtotal + quotation.shipping_amount


async def initialize_demo() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await _upsert_tenant(session)
            admin = await _upsert_admin(session, tenant)
            customers = await _upsert_customers(session, tenant, admin)
            await _upsert_connectors(session, tenant, admin)
            await _upsert_workflow(session, tenant, admin)
            await _upsert_knowledge(session, tenant, admin)
            products = await _upsert_products(session, tenant)
            await _upsert_quotation_template(
                session,
                tenant,
                admin,
                customers,
                products,
            )

    print(
        "Enterprise demo initialized: "
        f"tenant={TENANT_SLUG}, admin={ADMIN_EMAIL}, "
        f"customers={len(CUSTOMERS)}, connectors={len(CONNECTORS)}, "
        f"products={len(PRODUCTS)}, knowledge_documents={len(KNOWLEDGE_DOCUMENTS)}"
    )


async def main() -> None:
    try:
        await initialize_demo()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
