"""Validated model judgments. These are predictions, not proof or human labels."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuditVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["PASS", "FAIL_GAP", "FAIL_LOGIC", "ABSTAIN"]
    reason: str = Field(min_length=1)
    missing_prerequisites: list[str]
    confidence: float = Field(default=0.5, ge=0, le=1)
    lean_code: str | None = None


def parse_verdict(content: str) -> AuditVerdict:
    """Accept a JSON object or one fenced JSON object; never infer from keywords."""
    content = content.strip()
    if content.startswith("```json\n") and content.endswith("```"):
        content = content[8:-3].strip()
    elif content.startswith("```\n") and content.endswith("```"):
        content = content[4:-3].strip()
    return AuditVerdict.model_validate(json.loads(content))
