"""CLI over the same service layer as the API."""
import argparse
import json
import sys
import time
from pathlib import Path

from . import jobs, registry, runs
from .contract import load_contract_file, validate_contract
from .schemas import PreprocessingConfig, ScoreBatchRequest, ScoreRequest, TrainConfig
from .snapshot import load_manifest, snapshot_from_csv
from .validate import parse_csv_file, validate_rows


def _out(obj):
    print(json.dumps(obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj, indent=2))


def _contract(path: str):
    res = validate_contract(load_contract_file(path))
    if not res.ok:
        sys.exit("contract invalid:\n  " + "\n  ".join(res.errors))
    return res.contract


def cmd_contract_validate(a):
    res = validate_contract(load_contract_file(a.contract))
    _out(res)
    sys.exit(0 if res.ok else 1)


def cmd_import_validate(a):
    res = validate_rows(_contract(a.contract), parse_csv_file(a.csv))
    _out(res.report)
    sys.exit(0 if res.report.ok else 1)


def cmd_snapshot_create(a):
    res = validate_rows(_contract(a.contract), parse_csv_file(a.csv))
    if not res.report.ok:
        _out(res.report)
        sys.exit(1)
    pre = PreprocessingConfig() if a.preprocessing == "default" else PreprocessingConfig(lowercase=False, collapse_whitespace=False, strip_urls=False, max_chars=1_000_000)
    _out(snapshot_from_csv(a.snapshot_id, a.dataset_id, _contract(a.contract), res.rows, preprocessing=pre, seed=a.seed, keep_splits=a.keep_splits))


def cmd_snapshot_show(a):
    _out(load_manifest(a.snapshot_id))


def cmd_train(a):
    cfg = TrainConfig(snapshot_id=a.snapshot_id, model=a.model, params=json.loads(a.params) if a.params else None,
                      seed=a.seed, device=a.device, experiment=a.experiment)
    if a.sync:
        from .train import run_training
        print(json.dumps({"run_id": run_training(cfg)}))
        return
    rec = jobs.start_job(cfg)
    if not a.wait:
        _out(rec)
        return
    off = 0
    while True:
        logs = jobs.job_logs(rec.job_id, off)
        for line in logs.lines:
            print(line)
        off = logs.next_offset
        if logs.status not in jobs.ACTIVE:
            break
        time.sleep(1)
    _out(jobs.get_job(rec.job_id))


def cmd_jobs(a):
    if a.action == "list":
        _out(jobs.list_jobs())
    elif a.action == "status":
        _out(jobs.get_job(a.job_id))
    elif a.action == "logs":
        print("\n".join(jobs.job_logs(a.job_id, a.offset).lines))
    elif a.action == "cancel":
        _out(jobs.cancel_job(a.job_id))


def cmd_runs(a):
    if a.action == "list":
        _out(runs.list_runs(a.experiment))
    elif a.action == "show":
        _out(runs.summarize(a.run_id, detail=True))
    elif a.action == "compare":
        _out(runs.compare(a.run_id))


def cmd_promote(a):
    _out(registry.promote(a.run_id, initiated_by=a.by, reason=a.reason))


def cmd_rollback(a):
    _out(registry.rollback(initiated_by=a.by, reason=a.reason))


def cmd_production(a):
    from .scoring import scorer
    _out({**scorer.info(), "history": [h.model_dump() for h in registry.history()]})


def cmd_score(a):
    from .scoring import scorer
    if a.text:
        _out(scorer.score(ScoreRequest(text=" ".join(a.text))))
    else:
        items = [ScoreRequest(text=l) for l in sys.stdin.read().splitlines() if l.strip()]
        _out(scorer.score_batch(ScoreBatchRequest(items=items)))


def cmd_serve(a):
    import uvicorn
    uvicorn.run("triagekit.api:app", host=a.host, port=a.port, reload=False)


def cmd_openapi(a):
    from .api import openapi_json
    text = openapi_json()
    if a.out:
        Path(a.out).write_text(text + "\n")
    else:
        print(text)


def cmd_adapt_twcs(a):
    from .adapters.twcs import load_labeled_twcs, original_protocol_splits, split_hashes, write_canonical_csv
    rows = load_labeled_twcs(a.input)
    info = {"rows": len(rows)}
    if a.original_splits:
        assign = original_protocol_splits(rows)
        rows = [r.model_copy(update={"split": assign[r.id]}) for r in rows]
        info |= split_hashes(assign)
    write_canonical_csv(rows, a.output)
    _out({"output": a.output, **info})


def cmd_replicate(a):
    from .replicate import run_replication
    rep = run_replication(a.data, a.seeds, a.device)
    _out({k: rep[k] for k in ("snapshot_id", "per_seed", "mean_test_macro_f1", "reported_mean", "all_seeds_within_tolerance",
                              "three_seed_mean_within_tolerance", "environment_differences_from_original", "report_path")})


def cmd_adapt_bitext(a):
    from .adapters.bitext import load_bitext
    from .adapters.twcs import write_canonical_csv
    rows = load_bitext(a.input, dedupe=not a.keep_duplicates)
    write_canonical_csv(rows, a.output)
    _out({"output": a.output, "rows": len(rows), "positives": sum(r.label == 1 for r in rows)})


def cmd_prune(a):
    from .prune import prune
    _out(prune(dry_run=not a.apply, experiment=a.experiment))


def cmd_suggest(a):
    from .resolvers import llm_resolve
    _out(llm_resolve(_contract(a.contract), " ".join(a.text)))


def cmd_bundle(a):
    from .bundle import build_bundled_model
    prov = build_bundled_model(Path(a.out))
    _out({"out": a.out, "policy": prov["policy"], "test_macro_f1": prov["metrics"]["test"]["macro_f1"]})


def build_parser():
    p = argparse.ArgumentParser(prog="triagekit")
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("contract-validate"); x.add_argument("contract"); x.set_defaults(f=cmd_contract_validate)
    x = s.add_parser("import-validate"); x.add_argument("csv"); x.add_argument("--contract", required=True); x.set_defaults(f=cmd_import_validate)
    x = s.add_parser("snapshot-create"); x.add_argument("csv"); x.add_argument("--contract", required=True)
    x.add_argument("--snapshot-id", required=True); x.add_argument("--dataset-id", default="cli"); x.add_argument("--seed", type=int, default=42)
    x.add_argument("--preprocessing", choices=["default", "none"], default="default")
    x.add_argument("--keep-splits", action="store_true", help="use the CSV's split column as-is (all rows must be assigned)")
    x.set_defaults(f=cmd_snapshot_create)
    x = s.add_parser("snapshot-show"); x.add_argument("snapshot_id"); x.set_defaults(f=cmd_snapshot_show)
    x = s.add_parser("train"); x.add_argument("snapshot_id"); x.add_argument("--model", default="tfidf_lr")
    x.add_argument("--seed", type=int, default=42); x.add_argument("--device", default="auto"); x.add_argument("--experiment", default="triagekit")
    x.add_argument("--params", help="JSON object of model hyperparameters")
    x.add_argument("--wait", action="store_true"); x.add_argument("--sync", action="store_true", help="run in-process instead of as a job")
    x.set_defaults(f=cmd_train)
    x = s.add_parser("jobs"); x.add_argument("action", choices=["list", "status", "logs", "cancel"]); x.add_argument("job_id", nargs="?")
    x.add_argument("--offset", type=int, default=0); x.set_defaults(f=cmd_jobs)
    x = s.add_parser("runs"); x.add_argument("action", choices=["list", "show", "compare"]); x.add_argument("run_id", nargs="*")
    x.add_argument("--experiment", default="triagekit"); x.set_defaults(f=cmd_runs)
    for name, fn in (("promote", cmd_promote), ("rollback", cmd_rollback)):
        x = s.add_parser(name)
        if name == "promote":
            x.add_argument("run_id")
        x.add_argument("--by", default="cli"); x.add_argument("--reason"); x.set_defaults(f=fn)
    x = s.add_parser("production"); x.set_defaults(f=cmd_production)
    x = s.add_parser("score"); x.add_argument("text", nargs="*", help="text to score; omit to read lines from stdin"); x.set_defaults(f=cmd_score)
    x = s.add_parser("serve"); x.add_argument("--host", default="127.0.0.1"); x.add_argument("--port", type=int, default=8000); x.set_defaults(f=cmd_serve)
    x = s.add_parser("openapi"); x.add_argument("--out"); x.set_defaults(f=cmd_openapi)
    x = s.add_parser("adapt-twcs", help="convert human-loop llm_labeled_5k.csv to canonical CSV"); x.add_argument("input"); x.add_argument("output")
    x.add_argument("--original-splits", action="store_true", help="assign the human-loop notebook-04 splits"); x.set_defaults(f=cmd_adapt_twcs)
    x = s.add_parser("replicate", help="replicate the human-loop TWCS DistilBERT run"); x.add_argument("--data", required=True)
    x.add_argument("--seeds", type=int, nargs="+", default=[42]); x.add_argument("--device", default="auto"); x.set_defaults(f=cmd_replicate)
    x = s.add_parser("adapt-bitext", help="convert the Bitext intent CSV to canonical CSV"); x.add_argument("input"); x.add_argument("output")
    x.add_argument("--keep-duplicates", action="store_true"); x.set_defaults(f=cmd_adapt_bitext)
    x = s.add_parser("prune", help="delete unpromoted, unreferenced run weights (dry run unless --apply)"); x.add_argument("--apply", action="store_true")
    x.add_argument("--experiment"); x.set_defaults(f=cmd_prune)
    x = s.add_parser("suggest", help="ask the LLM tier for a label suggestion"); x.add_argument("text", nargs="+"); x.add_argument("--contract", required=True)
    x.set_defaults(f=cmd_suggest)
    x = s.add_parser("bundle"); x.add_argument("--out", default="bundled_model"); x.set_defaults(f=cmd_bundle)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "runs" and a.action == "show":
        a.run_id = a.run_id[0]
    if a.cmd == "runs" and a.action == "compare" and len(a.run_id) < 2:
        sys.exit("compare needs at least two run ids")
    a.f(a)


if __name__ == "__main__":
    main()
