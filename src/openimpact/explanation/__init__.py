"""Evidence-bound explanation contracts and deterministic fallback."""

from openimpact.explanation.models import (
    ExplanationInput,
    ExplanationResult,
    fallback_explanation,
)
from openimpact.explanation.fallback import RuleBasedProvider
from openimpact.explanation.provider import (
    ExplanationProvider,
    create_explanation_provider,
    explain_safely,
)

__all__ = [
    "ExplanationInput", "ExplanationResult", "fallback_explanation",
    "ExplanationProvider", "RuleBasedProvider", "create_explanation_provider",
    "explain_safely",
]
