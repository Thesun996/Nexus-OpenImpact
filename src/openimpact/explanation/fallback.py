"""Local explanation provider that uses the established rule template."""

from openimpact.explanation.models import (
    ExplanationInput,
    ExplanationResult,
    fallback_explanation,
)
from openimpact.explanation.provider import ExplanationProvider


class RuleBasedProvider(ExplanationProvider):
    def explain(self, input: ExplanationInput) -> ExplanationResult:
        return fallback_explanation(input)
