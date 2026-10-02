"""Second-tier resolvers for the uncertainty band. Both are optional; anything unresolved falls back to review."""
import os
import re
import time
from typing import Literal

from pydantic import BaseModel, Field

from .schemas import Label, LabelContract, LlmMeta, Rule, SuggestResponse

PROMPT_VERSION = "1"
DEFAULT_MODEL = "claude-opus-5"


def llm_enabled() -> bool:
    return bool(os.environ.get("TRIAGEKIT_LLM_ENABLED", "").lower() in ("1", "true", "yes"))


def llm_model() -> str:
    return os.environ.get("TRIAGEKIT_LLM_MODEL", DEFAULT_MODEL)


def rule_resolve(rules: list[Rule], text: str) -> tuple[Rule, str] | None:
    """First rule with a matching pattern wins; returns (rule, matched pattern) or None (explicit no-match)."""
    for r in rules:
        for pat in r.patterns:
            if re.search(pat, text, flags=re.IGNORECASE):
                return r, pat
    return None


class _Verdict(BaseModel):
    label: Literal[0, 1]
    category: str | None = None
    reason: str = Field(description="one short sentence grounded in the customer's wording")


def _system(contract: LabelContract) -> str:
    cats = ", ".join(contract.categories.allowed) or "none"
    amb = "\n".join(f"- {a}" for a in contract.ambiguous_cases) or "- none"
    return (
        f"You are a customer-support triage classifier working under label contract '{contract.name}' "
        f"version {contract.contract_version}.\n\n"
        f"label 1 = {contract.positive.name}: {contract.positive.definition.strip()}\n"
        f"Examples: {contract.positive.examples}\n\n"
        f"label 0 = {contract.negative.name}: {contract.negative.definition.strip()}\n"
        f"Examples: {contract.negative.examples}\n\n"
        f"Ambiguous cases:\n{amb}\n\n"
        f"Allowed categories: {cats}. Use null when no category applies.\n"
        "Judge only the message text. Reply with the structured verdict; the reason must be one short sentence."
    )


def llm_resolve(contract: LabelContract, text: str, timeout_s: float = 20.0) -> SuggestResponse:
    """Calls Claude with structured output validated against the contract. Never raises; errors are returned."""
    if not llm_enabled():
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=None, error="llm tier disabled (TRIAGEKIT_LLM_ENABLED)")
    try:
        import anthropic
    except ImportError:
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=None, error="anthropic sdk not installed")
    model = llm_model()
    t0 = time.perf_counter()
    try:
        client = anthropic.Anthropic(timeout=timeout_s, max_retries=1)
        resp = client.messages.parse(
            model=model, max_tokens=512, system=_system(contract),
            messages=[{"role": "user", "content": f"CUSTOMER MESSAGE:\n{text}"}], output_format=_Verdict)
    except anthropic.APITimeoutError:
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=None, error="llm timeout")
    except anthropic.APIStatusError as e:
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=None, error=f"llm api error {e.status_code}")
    except anthropic.APIConnectionError:
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=None, error="llm connection error")
    except Exception as e:  # invalid structured output etc.
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=None, error=f"llm error: {type(e).__name__}")
    meta = LlmMeta(model_id=getattr(resp, "model", model), prompt_version=PROMPT_VERSION,
                   latency_ms=int((time.perf_counter() - t0) * 1000),
                   input_tokens=getattr(resp.usage, "input_tokens", None), output_tokens=getattr(resp.usage, "output_tokens", None),
                   stop_reason=getattr(resp, "stop_reason", None))
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=meta, error=f"llm returned no verdict ({resp.stop_reason})")
    v = resp.parsed_output
    if v.category is not None and contract.categories.allowed and v.category not in contract.categories.allowed:
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=meta, error=f"llm category {v.category!r} not in contract")
    if contract.categories.required and v.category is None:
        return SuggestResponse(ok=False, label=None, category=None, reason=None, llm=meta, error="llm omitted a required category")
    return SuggestResponse(ok=True, label=v.label, category=v.category, reason=v.reason[:300], llm=meta)
