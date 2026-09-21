"""Offline regression test for the legacy theorem-auditing flow."""

import json
from types import SimpleNamespace

from src.verification.auditor_prover import AuditorProver


class _OfflineRetriever:
    def retrieve_for_audit(self, **_kwargs):
        return []

    def close(self):
        pass


class _OfflineCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **_kwargs):
        outcomes = [
            {
                "status": "PASS",
                "confidence": 0.95,
                "lean_code": None,
                "reason": "The supplied derivation is sufficient.",
                "missing_prerequisites": [],
            },
            {
                "status": "FAIL_GAP",
                "confidence": 0.95,
                "lean_code": None,
                "reason": "Integration is unavailable in the supplied context.",
                "missing_prerequisites": ["definite integral"],
            },
        ]
        content = json.dumps(outcomes[self.calls])
        self.calls += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )


def test_auditor_prover():
    """Classify a supported theorem and a missing-prerequisite theorem."""
    prover = AuditorProver.__new__(AuditorProver)
    prover.retriever = _OfflineRetriever()
    prover.openai = SimpleNamespace(
        chat=SimpleNamespace(completions=_OfflineCompletions())
    )
    prover.model = "offline-test"
    prover.lean_compiler = None
    prover.budget_tracker = None

    supported = prover.audit_theorem(
        theorem_text="A constant function has derivative zero.",
        chapter=5,
        skip_lean=True,
    )
    missing = prover.audit_theorem(
        theorem_text="Fundamental Theorem of Calculus.",
        chapter=2,
    )

    assert supported.status == "VERIFIED_LOGIC"
    assert missing.status == "FAIL_GAP"
    assert missing.missing_prerequisites == ["definite integral"]

    prover.close()
