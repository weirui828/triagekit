import numpy as np

from triagekit.resolvers import llm_resolve, rule_resolve
from triagekit.schemas import Rule, TrainConfig


def test_rule_resolver_explicit_match_and_no_match():
    rules = [Rule(name="human", label=1, patterns=[r"\b(human|agent|manager)\b"], category="account"),
             Rule(name="hours", label=0, patterns=["store hours"])]
    hit = rule_resolve(rules, "let me talk to a MANAGER now")
    assert hit and hit[0].name == "human" and hit[0].label == 1
    assert rule_resolve(rules, "what are your store hours")[0].name == "hours"
    assert rule_resolve(rules, "where is my order") is None


def test_llm_disabled_returns_error_not_exception(contract, monkeypatch):
    monkeypatch.delenv("TRIAGEKIT_LLM_ENABLED", raising=False)
    r = llm_resolve(contract, "hello")
    assert not r.ok and "disabled" in r.error and r.label is None


def test_scorer_second_tier(contract, data_dir, tmp_path):
    """In-band scores go to the rule tier when configured, and to review on no match."""
    from triagekit.models import get_model
    from triagekit.pyfunc_model import ARTIFACT_KEY, TriagePyfunc, write_package
    from triagekit.schemas import PolicySelection, PreprocessingConfig
    from triagekit.scoring import Loaded
    import mlflow.pyfunc
    c = contract.model_copy(deep=True)
    c.routing_policy.second_tier = "rule"
    c.routing_policy.rules = [Rule(name="human", label=1, patterns=["human"])]
    m = get_model("tfidf_lr", {}, PreprocessingConfig(), 0, "cpu")
    m.fit(["refund now please", "where is my order", "talk to a human", "store hours"], np.array([1, 0, 1, 0]))
    pol = PolicySelection(classification_threshold=0.5, threshold_objective="max_macro_f1", threshold_feasible=True,
                          routing_low=0.0, routing_high=1.0, routing_objective="max_coverage", routing_feasible=True, notes=[])
    pkg = write_package(tmp_path / "pkg", m, pol, c, {"contract_hash": "x"})
    mlflow.pyfunc.save_model(path=str(tmp_path / "model"), python_model=TriagePyfunc(), artifacts={ARTIFACT_KEY: str(pkg)})
    pf = mlflow.pyfunc.load_model(str(tmp_path / "model"))
    loaded = Loaded(pf, pf.unwrap_python_model().package, "test:1", "test")
    r = loaded.score("I need a human")
    assert r.resolved_by == "rule" and r.final_label == 1 and r.action == "escalate"
    r = loaded.score("something else entirely")
    assert r.resolved_by == "human_pending" and r.action == "review" and r.fallback == "rule:no_match"


def test_bertweet_defaults_checkpoint():
    assert TrainConfig(snapshot_id="s", model="bertweet").params.checkpoint == "vinai/bertweet-base"
