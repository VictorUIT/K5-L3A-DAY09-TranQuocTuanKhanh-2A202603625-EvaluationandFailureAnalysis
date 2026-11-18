"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    import math
    from lab9.graders import GRADERS

    problems: list[str] = []
    rows = pr.get("rows") or []
    man = pr.get("manifest") or {}

    # 1. metric values must be real numbers
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}: a crashed or empty grader, not a score")

    # 2. row count = items x seeds; no (item, seed) twice
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest promises {man.get('items')} items x "
                        f"{len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"{len(dups)} duplicated (item, seed) row(s), e.g. {dups[0]}")

    # 3. same (item, seed) set as the baseline, and the seeds the manifest names
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != base_keys:
        miss, extra = len(base_keys - set(keys)), len(set(keys) - base_keys)
        problems.append(f"(item, seed) set differs from the baseline: {miss} missing, {extra} extra")
    if set(man.get("seeds") or []) != set((base.get("manifest") or {}).get("seeds") or []):
        problems.append(f"seeds {man.get('seeds')} differ from the baseline's "
                        f"{(base.get('manifest') or {}).get('seeds')}")
    if {r.get("seed") for r in rows} - set(man.get("seeds") or []):
        problems.append("rows carry seeds the manifest does not list")

    # 4. no crashed graders: evaluator failures, or a graded metric missing / None on a row
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): "
                        f"{str(pr['evaluator_failures'][0])[:80]}")
    graded = [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS]
    none_rows = [(r.get("item_id"), r.get("seed"), m) for r in rows for m in graded if r.get(m) is None]
    if none_rows:
        problems.append(f"{len(none_rows)} row value(s) are None/missing for graded metrics, "
                        f"e.g. {none_rows[0]}: they would drop out of the mean")

    # 4b. reported metrics must match what the rows say (no hand-edited numbers)
    for m in graded:
        vals = [r.get(m) for r in rows if r.get(m) is not None]
        reported = (pr.get("metrics") or {}).get(m)
        if not vals or not isinstance(reported, (int, float)) or isinstance(reported, bool):
            continue
        actual = sum(vals) if m in ("secret_leak", "approval_bypass") else sum(vals) / len(vals)
        if isinstance(reported, float) and not math.isfinite(reported):
            continue                                  # already reported above
        if abs(actual - reported) > 1e-3:
            problems.append(f"metric {m} reported {reported} but its rows give {round(actual, 4)}")

    # 5. ratchet: same eval-set version => thresholds may only get stricter
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)

    # 6. slice tags per item must match the baseline's
    def tags(report: dict) -> dict:
        out: dict = {}
        for r in report.get("rows") or []:
            out.setdefault(r.get("item_id"), set()).update(r.get("slices") or [])
        return out
    pt, bt = tags(pr), tags(base)
    moved = sorted(i for i in pt.keys() & bt.keys() if pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags changed on {len(moved)} item(s), e.g. {moved[0]}: "
                        f"{sorted(bt[moved[0]])} -> {sorted(pt[moved[0]])}")
    return problems


def _looser(name: str, new: dict, old: dict) -> list[str]:
    """Compare one metric's or slice's rule with the baseline spec's. Return what got looser."""
    out = []
    nth, oth = new.get("threshold", new), old.get("threshold", old)
    if "min" in oth and ("min" not in nth or nth["min"] < oth["min"]):
        out.append(f"{name}: min {oth['min']} -> {nth.get('min')}")
    if "max" in oth and ("max" not in nth or nth["max"] > oth["max"]):
        out.append(f"{name}: max {oth['max']} -> {nth.get('max')}")
    if "max_increase" in oth and ("max_increase" not in nth or nth["max_increase"] > oth["max_increase"]):
        out.append(f"{name}: max_increase {oth['max_increase']} -> {nth.get('max_increase')}")
    if oth.get("no_significant_drop") and not nth.get("no_significant_drop"):
        out.append(f"{name}: no_significant_drop dropped")
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{name}: blocking -> non-blocking")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems = []
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        if m["id"] not in new_m:
            problems.append(f"ratchet: metric {m['id']} removed")
        else:
            problems += [f"ratchet: {x}" for x in _looser(f"metric {m['id']}", new_m[m["id"]], m)]
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        key = (s["name"], s["metric"])
        if key not in new_s:
            problems.append(f"ratchet: slice {key[0]}/{key[1]} removed")
        else:
            problems += [f"ratchet: {x}" for x in _looser(f"slice {key[0]}/{key[1]}", new_s[key], s)]
    for k in ("seeds", "eval_set", "labels"):
        if k in base_spec and spec.get(k) != base_spec.get(k):
            problems.append(f"ratchet: {k} changed from {base_spec.get(k)} to {spec.get(k)}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        b = per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            # An empty slice cannot vouch for anything: a relabelled or dropped slice must not pass.
            verdict, note = "missing", "no PR rows carry this slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000),
                                                   rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<36} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
