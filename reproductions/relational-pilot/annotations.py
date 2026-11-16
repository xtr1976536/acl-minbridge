"""Blinded packets, independent labels, and explicit third-person adjudication."""
import argparse
import copy
import json
import random
from pathlib import Path

from prepare import digest, read_json, write_new

LABELS = ("wrong_answer", "correct_refusal", "outside_document_input_number",
          "numeric_hallucination", "relational_hallucination", "other_error")
RESPONSE_TYPES = {"answer", "conditional_answer", "refusal", "other", "unfinished"}


def read_outputs(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate output IDs")
    return rows


def export(data_path, tasks_path, outputs_path, output, seed):
    data, task_bundle = read_json(data_path), read_json(tasks_path)
    sources = {r["source_id"]: r for r in data.get("sources", data.get("drafts", []))}
    tasks = {t["id"]: t for t in task_bundle["tasks"]}
    outputs = {r["id"]: r for r in read_outputs(outputs_path)}
    if set(outputs) != set(tasks):
        raise ValueError("Complete expected task matrix required; failures remain as records")
    ids = list(tasks)
    random.Random(seed).shuffle(ids)
    public, private = [], []
    for task_id in ids:
        task, result = tasks[task_id], outputs[task_id]
        source = sources[task["source_id"]]
        if source["variant_sha256"] != task["variant_sha256"]:
            raise ValueError("Source variant drift")
        blind_id = digest([seed, "blind", task_id])[:24]
        public.append({"blind_id": blind_id, "evidence": source["visible"],
                       "response": result.get("content", ""),
                       "execution_result": result.get("execution"),
                       "visible_trace": result.get("reasoning_content"),
                       "response_type": None, "labels": {k: None for k in LABELS},
                       "step_annotations": [], "rationale": None})
        # API/finish statuses remain in the private key; missing metadata cannot
        # cause unknown/truncated outputs to be counted as successful abstentions.
        private.append({"blind_id": blind_id, "task": task,
                        "status": result["status"], "output_sha256": digest(result),
                        "packet_content_sha256": digest({k: public[-1][k] for k in
                            ("evidence", "response", "execution_result", "visible_trace")})})
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    for role in ("A", "B"):
        write_new(out / f"reviewer_{role}.json", {"reviewer": None, "items": copy.deepcopy(public)})
    write_new(out / "private_key.json", {"data_status": task_bundle["status"], "items": private})


def validate_item(item):
    if item.get("response_type") not in RESPONSE_TYPES:
        raise ValueError("Missing response type")
    if set(item.get("labels", {})) != set(LABELS) or any(type(v) is not bool for v in item["labels"].values()):
        raise ValueError("All independent labels require explicit booleans")
    labels = item["labels"]
    if labels["correct_refusal"] and (labels["wrong_answer"] or item["response_type"] != "refusal"):
        raise ValueError("Inconsistent correct-refusal annotation")
    if labels["wrong_answer"] and item["response_type"] not in ("answer", "conditional_answer"):
        raise ValueError("Wrong-answer denominator includes answers only")
    if not item.get("rationale"):
        raise ValueError("Annotation needs an evidence-based rationale")
    for step in item.get("step_annotations", []):
        for key in ("span", "evidence_support", "logical_correctness", "target_relevance"):
            if key not in step:
                raise ValueError("Step labels must separate support, logic, and relevance")


def agreement(a, b, label):
    av = [x["labels"][label] for x in a]
    bv = [x["labels"][label] for x in b]
    n = len(av)
    if not n:
        return {"n": 0, "agreement": None, "kappa": None}
    observed = sum(x == y for x, y in zip(av, bv)) / n
    pa, pb = sum(av) / n, sum(bv) / n
    expected = pa * pb + (1-pa) * (1-pb)
    return {"n": n, "agreement": observed,
            "kappa": (observed-expected)/(1-expected) if expected < 1 else None}


def merge(a_path, b_path, key_path, adjudication_path, output):
    a, b, key = read_json(a_path), read_json(b_path), read_json(key_path)
    if not a.get("reviewer") or not b.get("reviewer") or a["reviewer"] == b["reviewer"]:
        raise ValueError("Two distinct independent reviewer identities required")
    lookups = [{i["blind_id"]: i for i in pack["items"]} for pack in (a, b, key)]
    if any(len(lookup) != len(pack["items"]) for lookup, pack in zip(lookups, (a,b,key))):
        raise ValueError("Duplicate blind IDs")
    if not (set(lookups[0]) == set(lookups[1]) == set(lookups[2])):
        raise ValueError("Missing or foreign blind IDs")
    adj = read_json(adjudication_path) if adjudication_path else {"reviewer": None, "items": []}
    adjudications = {i["blind_id"]: i for i in adj["items"]}
    rows_a, rows_b, merged, disputes = [], [], [], []
    for blind_id in lookups[0]:
        ia, ib, mapping = [lookup[blind_id] for lookup in lookups]
        validate_item(ia)
        validate_item(ib)
        # Reviewers must have seen the same evidence and output.
        for field in ("evidence", "response", "execution_result", "visible_trace"):
            if ia.get(field) != ib.get(field):
                raise ValueError("Reviewer packet content drift")
        if digest({k: ia.get(k) for k in ("evidence", "response", "execution_result", "visible_trace")}) != mapping["packet_content_sha256"]:
            raise ValueError("Reviewer content does not match original blind packet")
        rows_a.append(ia)
        rows_b.append(ib)
        final = ia
        if (ia["labels"], ia["response_type"]) != (ib["labels"], ib["response_type"]):
            disputes.append(blind_id)
            if blind_id not in adjudications:
                continue
            if not adj.get("reviewer") or adj["reviewer"] in (a["reviewer"], b["reviewer"]):
                raise ValueError("Disagreements need a distinct third adjudicator")
            final = adjudications[blind_id]
            validate_item(final)
        merged.append({**mapping, "annotation": final})
    missing = [i for i in disputes if i not in adjudications]
    write_new(output, {"status": "adjudicated" if not missing else "awaiting_adjudication",
                       "data_status": key["data_status"],
                       "reviewers": [a["reviewer"], b["reviewer"]], "adjudicator": adj.get("reviewer"),
                       "agreement": {label: agreement(rows_a, rows_b, label) for label in LABELS},
                       "disagreements": disputes, "unresolved": missing, "items": merged})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export")
    for arg in ("data", "tasks", "outputs", "output", "seed"):
        e.add_argument("--" + arg, required=True)
    m = sub.add_parser("merge")
    for arg in ("a", "b", "key", "output"):
        m.add_argument("--" + arg, required=True)
    m.add_argument("--adjudication")
    args = p.parse_args()
    if args.command == "export":
        export(args.data, args.tasks, args.outputs, args.output, args.seed)
    else:
        merge(args.a, args.b, args.key, args.adjudication, args.output)
