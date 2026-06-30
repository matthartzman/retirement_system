from __future__ import annotations
"""Single source of truth for product/version labels."""

PRODUCT_NAME = 'Retirement System'
VERSION = '9'
RELEASE_LABEL = f"{PRODUCT_NAME} v{VERSION}"
API_NAMESPACE = ""  # API routes use /api/ prefix without version suffix.
CACHE_SCHEMA_VERSION = VERSION
USER_AGENT = f"RetirementPlanSystem/{VERSION} (+local-advisor-tool)"

def release_label(prefix: str = "") -> str:
    return f"{prefix}{RELEASE_LABEL}" if prefix else RELEASE_LABEL
