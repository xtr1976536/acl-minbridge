"""Both label policies; full denominators and paired family-cluster bootstrap."""
import argparse
import random
from collections import defaultdict

from prepare import read_json, write_new
from prompts import METHODS
from run import FAMILIES, MODES

POLICIES = ("numeric_provenance_exclusive", "independent_overlapping")


def flags(row, policy):
    item, status = row["annotation"], row["status"]
    lab = item["labels"]
    completed = status == "completed" and item["response_type"] != "unfinished"
    wrong = completed and lab["wrong_answer"]
    if policy == "numeric_provenance_exclusive":
        numeric = wrong and lab["outside_document_input_number"]
        relation = wrong and not lab["outside_document_input_number"]
    else:
        numeric = wrong and lab["numeric_hallucination"]
        relation = wrong and lab["relational_hallucination"]
    return {"wrong": int(wrong), "numeric": int(numeric), "relation": int(relation),
            "unfinished": int(not completed),
            "correct_refusal": int(completed and lab["correct_refusal"])}


def metrics(rows, policy):
    values = [flags(r, policy) for r in rows]
    n = len(values)
    counts = {k: sum(v[k] for v in values) for k in values[0]} if values else {}
    return {"n_all_unanswerable": n, **counts,
            "numeric_rate": counts["numeric"] / n if n else None,
            "relation_rate": counts["relation"] / n if n else None,
            "unfinished_rate": counts["unfinished"] / n if n else None,
            "correct_refusal_rate": counts["correct_refusal"] / n if n else None,
            "h1_relation_share_among_wrong_answers": counts["relation"] / counts["wrong"] if counts.get("wrong") else None}


def quantile(values, p):
    vals = sorted(values)
    x = (len(vals)-1) * p
    lo = int(x)
    hi = min(lo+1, len(vals)-1)
    return vals[lo] + (vals[hi]-vals[lo]) * (x-lo)


def confidence(values):
    valid = [v for v in values if v is not None]
    # Do not condition a ratio/H1 CI on only the replicates with a nonzero denominator.
    return {"ci95": [quantile(valid, .025), quantile(valid, .975)] if len(valid) == len(values) and valid else None,
            "undefined_replicates": len(values)-len(valid)}


def resamples(rows, seed, replicates=2000):
    groups = defaultdict(list)
    for row in rows:
        family_id = row["task"]["family_id"]
        if not family_id:
            raise ValueError("Reviewed family IDs required for cluster bootstrap")
        groups[family_id].append(row)
    keys = sorted(groups)
    rng = random.Random(seed)
    for _ in range(replicates):
        yield [r for key in rng.choices(keys, k=len(keys)) for r in groups[key]]


def compare(a, b, policy, seed):
    # Sample A's source families once and retrieve their exact paired B outputs.
    other = {r["task"]["source_id"]: r for r in b}
    if set(other) != {r["task"]["source_id"] for r in a}:
        raise ValueError("Paired comparison has missing source questions")
    ma, mb = metrics(a, policy), metrics(b, policy)
    point = {"numeric_rate_difference": mb["numeric_rate"]-ma["numeric_rate"],
             "relation_rate_difference": mb["relation_rate"]-ma["relation_rate"],
             "relation_rate_ratio": mb["relation_rate"]/ma["relation_rate"] if ma["relation_rate"] else None}
    boot = {k: [] for k in point}
    for sample in resamples(a, seed):
        sa = metrics(sample, policy)
        sb = metrics([other[r["task"]["source_id"]] for r in sample], policy)
        boot["numeric_rate_difference"].append(sb["numeric_rate"]-sa["numeric_rate"])
        boot["relation_rate_difference"].append(sb["relation_rate"]-sa["relation_rate"])
        boot["relation_rate_ratio"].append(sb["relation_rate"]/sa["relation_rate"] if sa["relation_rate"] else None)
    results = {k: {"estimate": v, **confidence(boot[k])} for k, v in point.items()}
    if not ma["relation_rate"]:
        # Plan: zero ratio denominator -> report difference only.
        results.pop("relation_rate_ratio")
    return {"direction": "B minus A; ratio B/A where defined", "A": ma, "B": mb, **results}


def analyze(path, output, seed):
    bundle = read_json(path)
    if bundle.get("status") != "adjudicated" or bundle.get("data_status") != "formal_reviewed":
        raise ValueError("Formal results require frozen data and completed independent adjudication")
    rows = bundle["items"]
    cells = defaultdict(list)
    task_ids = set()
    for row in rows:
        task = row["task"]
        if task["id"] in task_ids:
            raise ValueError("Duplicate task")
        task_ids.add(task["id"])
        cells[(task["model_family"], task["mode"], task["method"])].append(row)
    expected = {(f, m, method) for f in FAMILIES for m in MODES for method in METHODS}
    if set(cells) != expected:
        raise ValueError("Missing or foreign model/mode/method cell")
    first_ids = None
    for cell in cells.values():
        ids = {r["task"]["source_id"] for r in cell}
        if len(cell) != 150 or len(ids) != 150:
            raise ValueError("Each cell must retain all 150 sources, including failures")
        if first_ids is None:
            first_ids = ids
        if ids != first_ids:
            raise ValueError("Cells use different source questions")
    report = {"source_count": 150, "output_count": len(rows), "bootstrap_replicates": 2000,
              "resampling_unit": "reviewed_source_family", "bootstrap_seed": seed,
              "agreement": bundle["agreement"], "policies": {},
              "interpretation": "H1-H3 are hypotheses; report every prompt variant and both label policies. Exclusive relation is the section-2.4 numeric-provenance operational proxy, not an independently verified relation label."}
    for policy in POLICIES:
        summary = {"cells": {}, "h2_comparisons": {}, "h3_comparisons": {}}
        for key, cell in cells.items():
            point = metrics(cell, policy)
            boot = {k: [] for k in ("numeric_rate", "relation_rate", "h1_relation_share_among_wrong_answers")}
            for sample in resamples(cell, seed):
                m = metrics(sample, policy)
                for k in boot:
                    boot[k].append(m[k])
            summary["cells"]["/".join(key)] = {**point, "confidence": {k: confidence(v) for k, v in boot.items()}}
        for family in FAMILIES:
            for mode in MODES:
                for cot in ("cot_paired_4shot", "cot_existing_abstention"):
                    summary["h2_comparisons"][f"{family}/{mode}/pot_vs_{cot}"] = compare(
                        cells[(family, mode, cot)], cells[(family, mode, "pot")], policy, seed)
            for method in METHODS:
                summary["h3_comparisons"][f"{family}/{method}/high_vs_low"] = compare(
                    cells[(family, "low", method)], cells[(family, "high", method)], policy, seed)
        report["policies"][policy] = summary
    write_new(output, report)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adjudicated", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--seed", type=int, required=True)
    a = p.parse_args()
    analyze(a.adjudicated, a.output, a.seed)
