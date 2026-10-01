"""Provider boundary for explaining already established impact evidence."""

from abc import ABC, abstractmethod

from openimpact.explanation.models import ExplanationInput, ExplanationResult


class ExplanationProvider(ABC):
    """Implementations only turn ExplanationInput into explanatory text."""

    @abstractmethod
    def explain(self, input: ExplanationInput) -> ExplanationResult:
        """Explain the supplied facts without changing impact findings."""


def create_explanation_provider(mode: str = "rule") -> ExplanationProvider:
    """Select a local provider; future modes can be added without changing Core."""
    if mode == "rule":
        from openimpact.explanation.fallback import RuleBasedProvider

        return RuleBasedProvider()
    raise ValueError(f"不支持的解释模式：{mode}")


def explain_safely(
    input: ExplanationInput, provider: ExplanationProvider | None = None
) -> ExplanationResult:
    """Keep provider failures in the explanation layer, with a rule fallback."""
    from openimpact.explanation.fallback import RuleBasedProvider

    try:
        selected = provider if provider is not None else create_explanation_provider()
        result = selected.explain(input)
        if not isinstance(result, ExplanationResult):
            raise TypeError("Provider 返回值必须是 ExplanationResult。")
        return result
    except Exception:
        try:
            return RuleBasedProvider().explain(input)
        except Exception:
            # This text is safe even when the input itself is malformed.
            return ExplanationResult(
                summary="解释暂不可用。",
                why_affected="解释生成失败，请查看已有静态影响结果和代码证据。",
                risk_level="unknown",
                suggested_check="根据静态报告中的位置和调用路径人工检查。",
                confidence=0.0,
            )
