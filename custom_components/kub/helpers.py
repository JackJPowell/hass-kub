"""Helpers for KUB account data."""

from typing import Any


def get_service_utility(account: dict[str, Any], service_key: str) -> str:
    """Return the utility name from either supported account data format."""
    service = account[service_key]
    if isinstance(service, dict):
        return service["utility"]
    return service_key.rsplit("_", 1)[0]


def get_service_id(account: dict[str, Any], service_key: str) -> str:
    """Return the service-point ID from either supported account data format."""
    service = account[service_key]
    if isinstance(service, dict):
        return service["id"]
    return service
