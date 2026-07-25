from collections.abc import Callable
from typing import TypeVar

from app.connectors.base import BaseConnector

ConnectorType = TypeVar("ConnectorType", bound=type[BaseConnector])


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, type[BaseConnector]] = {}

    def register(self, provider: str) -> Callable[[ConnectorType], ConnectorType]:
        def decorator(connector: ConnectorType) -> ConnectorType:
            normalized = provider.strip().lower()
            if normalized in self._connectors:
                raise ValueError(f"connector provider already registered: {normalized}")
            self._connectors[normalized] = connector
            return connector

        return decorator

    def get(self, provider: str) -> type[BaseConnector] | None:
        return self._connectors.get(provider.strip().lower())

    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._connectors))


connector_registry = ConnectorRegistry()
