"""Loads the production model, routes scores into actions. In-flight requests keep their resolved version."""
import hashlib
import json
import threading
from pathlib import Path

import mlflow.pyfunc

from . import registry
from .resolvers import llm_resolve, rule_resolve
from .schemas import (LabelContract, PolicySelection, ScoreBatchItem, ScoreBatchRequest, ScoreBatchResponse,
                      ScoreRequest, ScoreResult)
from .settings import bundled_model_dir


class Loaded:
    def __init__(self, model, package: dict, version: str, source: str):
        self.model, self.package, self.version, self.source = model, package, version, source
        self.policy = PolicySelection(**package["policy"])
        self.contract = LabelContract(**package["contract"])
        ph = hashlib.sha256(json.dumps({"policy": package["policy"], "contract_hash": package.get("contract_hash")},
                                       sort_keys=True).encode()).hexdigest()[:8]
        self.policy_version = f"{package['contract']['contract_version']}:{ph}"

    def score(self, text: str) -> ScoreResult:
        p = float(self.model.predict([text])[0]["probability"])
        pol = self.policy
        predicted = 1 if p >= pol.classification_threshold else 0
        if p < pol.routing_low:
            final, by, action, reason = 0, "model", "auto_handle", "score below routing low bound"
        elif p >= pol.routing_high:
            final, by, action, reason = 1, "model", "escalate", "score at or above routing high bound"
        else:
            return self._second_tier(text, p, predicted)
        return ScoreResult(probability=p, predicted_label=predicted, final_label=final, resolved_by=by, action=action,
                           model_version=self.version, policy_version=self.policy_version,
                           classification_threshold=pol.classification_threshold, routing_low=pol.routing_low,
                           routing_high=pol.routing_high, reason=reason)

    def _second_tier(self, text: str, p: float, predicted: int) -> ScoreResult:
        """In-band decisions: rule or LLM tier if configured; anything unresolved is human review."""
        pol, rp = self.policy, self.contract.routing_policy
        base = dict(probability=p, predicted_label=predicted, model_version=self.version, policy_version=self.policy_version,
                    classification_threshold=pol.classification_threshold, routing_low=pol.routing_low, routing_high=pol.routing_high)
        review = lambda reason, fallback=None, **kw: ScoreResult(final_label=None, resolved_by="human_pending", action="review",
                                                                 reason=reason, fallback=fallback, **base, **kw)
        if rp.second_tier == "rule":
            hit = rule_resolve(rp.rules, text)
            if hit is None:
                return review("score inside uncertainty band; no rule matched", fallback="rule:no_match")
            rule, pat = hit
            return ScoreResult(final_label=rule.label, resolved_by="rule", action="escalate" if rule.label == 1 else "auto_handle",
                               category=rule.category, reason=f"rule '{rule.name}' matched /{pat}/", **base)
        if rp.second_tier == "llm":
            v = llm_resolve(self.contract, text)
            if not v.ok:
                return review(f"score inside uncertainty band; llm unavailable: {v.error}", fallback=f"llm:{v.error}", llm=v.llm)
            return ScoreResult(final_label=v.label, resolved_by="llm", action="escalate" if v.label == 1 else "auto_handle",
                               category=v.category, reason=v.reason, llm=v.llm, **base)
        return review("score inside uncertainty band")


class Scorer:
    def __init__(self):
        self._lock = threading.Lock()
        self._loaded: Loaded | None = None

    def _load(self, uri: str, version: str, source: str) -> Loaded:
        m = mlflow.pyfunc.load_model(uri)
        return Loaded(m, m.unwrap_python_model().package, version, source)

    def ensure(self) -> Loaded | None:
        """Reload only after a replacement loads successfully; failures keep the current model."""
        version, run_id = registry.current_version()
        with self._lock:
            if version is not None:
                v = f"{registry.REGISTERED_MODEL_NAME}:{version}"
                if self._loaded is None or self._loaded.version != v:
                    self._loaded = self._load(registry.model_uri(), v, "registry")
                return self._loaded
            b = bundled_model_dir()
            if (b / "MLmodel").exists():
                h = hashlib.sha256((b / "MLmodel").read_bytes()).hexdigest()[:12]
                v = f"bundled:{h}"
                if self._loaded is None or self._loaded.version != v:
                    self._loaded = self._load(str(b), v, "bundled")
                return self._loaded
            return self._loaded

    def score(self, req: ScoreRequest) -> ScoreResult:
        m = self.ensure()
        if m is None:
            raise RuntimeError("no production model and no bundled model available")
        return m.score(req.text)

    def score_batch(self, req: ScoreBatchRequest) -> ScoreBatchResponse:
        m = self.ensure()
        if m is None:
            raise RuntimeError("no production model and no bundled model available")
        items = []
        for i, it in enumerate(req.items):
            try:
                items.append(ScoreBatchItem(index=i, request_id=it.request_id, result=m.score(it.text), error=None))
            except Exception as e:
                items.append(ScoreBatchItem(index=i, request_id=it.request_id, result=None, error=str(e)[:500]))
        return ScoreBatchResponse(items=items, model_version=m.version)

    def info(self):
        v, rid = registry.current_version()
        loaded = self._loaded
        return {"version": v, "run_id": rid, "loaded_version": loaded.version if loaded else None,
                "source": "registry" if v else (loaded.source if loaded else "none")}


scorer = Scorer()
