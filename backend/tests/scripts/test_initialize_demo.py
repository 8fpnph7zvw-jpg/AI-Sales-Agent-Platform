from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.workflow.workflow import Workflow

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_ROOT / "scripts" / "initialize_demo.py"
COMPOSE_PATH = BACKEND_ROOT.parent / "docker-compose.yml"


def _load_script():
    spec = importlib.util.spec_from_file_location("initialize_demo", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_catalog_matches_enterprise_demo_requirements() -> None:
    demo = _load_script()

    assert demo.TENANT_NAME == "AI Sales Demo"
    assert demo.ADMIN_EMAIL == "admin@test.com"
    assert {item["name"] for item in demo.CUSTOMERS} == {
        "ABC Electronics",
        "Amazon Buyer Test",
        "European Importer",
    }
    assert {item["provider"] for item in demo.CONNECTORS} == {
        "whatsapp",
        "alibaba",
        "amazon",
        "feishu",
    }
    assert {item["name"] for item in demo.PRODUCTS} == {
        "Wireless Earphone",
        "Smart Watch",
        "USB Charger",
    }
    assert {item[0] for item in demo.KNOWLEDGE_DOCUMENTS} == {
        "产品介绍.md",
        "价格规则.md",
        "运输方式.md",
        "售后政策.md",
    }
    assert [item["name"] for item in demo.WORKFLOW_NODES] == [
        "客户询盘",
        "AI自动回复",
        "意向评分",
        "高意向通知销售",
    ]


def test_demo_initializer_uses_orm_and_is_wired_into_docker_migration() -> None:
    demo = _load_script()
    source = inspect.getsource(demo)
    compose = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "select(" in source
    assert "session.add(" in source
    assert "op.execute" not in source
    assert "sqlalchemy.text" not in source
    assert "python scripts/initialize_demo.py" in compose


@pytest.mark.asyncio
async def test_new_workflow_has_trigger_type_before_first_flush() -> None:
    demo = _load_script()

    class ScalarResult:
        @staticmethod
        def all() -> list[object]:
            return []

    class Session:
        def __init__(self) -> None:
            self.added: list[object] = []

        async def scalar(self, _statement: object) -> None:
            return None

        def add(self, model: object) -> None:
            self.added.append(model)

        async def flush(self) -> None:
            workflow = next(item for item in self.added if isinstance(item, Workflow))
            assert workflow.trigger_type == "customer_inquiry"

        async def scalars(self, _statement: object) -> ScalarResult:
            return ScalarResult()

    session = Session()
    await demo._upsert_workflow(
        session,
        SimpleNamespace(id=1),
        SimpleNamespace(id=2),
    )
