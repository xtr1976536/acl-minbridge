"""Offline preparation only. Never calls a model, labels data, or executes model code.

The train split, mutations and review records are explicit inputs. An approved
gold program is a fact locator, never an unanswerability certificate.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VISIBLE_KEYS = {"question", "pre_text", "table", "post_text"}


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return digest_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Fail closed rather than replacing a prior annotation or frozen manifest.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def git_commit(path):
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def load_finqa(path):
    rows = read_json(path)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected a nonempty official FinQA record list")
    ids = []
    for row in rows:
        ids.append(row["id"])
        if not isinstance(row["qa"]["question"], str):
            raise ValueError("Question must be text")
        for key in ("pre_text", "post_text", "table"):
            if not isinstance(row[key], list):
                raise ValueError("Expected official FinQA evidence arrays")
        if not row["table"] or any(not isinstance(r, list) for r in row["table"]):
            raise ValueError("Expected table rows")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source IDs")
    return rows


def public_view(row):
    return copy.deepcopy({"question": row["qa"]["question"],
                          "pre_text": row["pre_text"], "table": row["table"],
                          "post_text": row["post_text"]})


def report_group(row):
    # A provisional source-report key, not a claim of semantic family identity.
    name = str(row.get("filename", ""))
    parts = name.replace("\\", "/").split("/")
    return "/".join(parts[:2]) if len(parts) >= 3 else None


def evidence_units(view):
    for field in ("pre_text", "post_text"):
        for i, text in enumerate(view[field]):
            yield f"{field}/{i}", text
    for i, row in enumerate(view["table"]):
        for j, text in enumerate(row):
            yield f"table/{i}/{j}", text


def program_operands(program):
    # Preserve the official expression and literals; do not run eval/exec.
    calls = re.findall(r"\b[a-z_]+\(([^()]*)\)", program)
    return sorted({arg.strip() for call in calls for arg in call.split(",")
                   if arg.strip() and not arg.strip().startswith(("#", "const_"))})


def index_sources(train, provenance, output):
    """Index every source before sampling; never select easy hallucinations."""
    rows = load_finqa(train)
    source = read_json(provenance)
    if source.get("split") != "train" or source.get("path") != "dataset/train.json":
        raise ValueError("Training provenance must explicitly name dataset/train.json")
    if source.get("sha256") != digest_bytes(Path(train).read_bytes()):
        raise ValueError("Train SHA-256 mismatch")
    if not source.get("commit") or not source.get("url"):
        raise ValueError("Missing fixed source commit/URL")
    expected = source.get("expected_records")
    if expected is not None and len(rows) != expected:
        raise ValueError("Train record count differs from provenance")
    indexed = []
    for row in rows:
        view = public_view(row)
        indexed.append({"source_id": row["id"], "source_report_provisional": report_group(row),
                        "family_id": None, "source_visible_sha256": digest(view),
                        "source": view, "gold_private": row["qa"],
                        "operand_locator_hints": program_operands(row["qa"].get("program", "")),
                        "evidence_locations": dict(evidence_units(view)),
                        "status": "not_reviewed_not_selected"})
    write_new(output, {"status": "unreviewed_source_index", "provenance": source,
                       "complete_train_ids_sha256": digest(sorted(r["id"] for r in rows)),
                       "source_count": len(rows), "sources": indexed})


def apply_edits(view, edits):
    """Exact span deletion, with unchanged table shape and sentence boundaries.

    Repeated spans require explicit character offsets. Replacement must be empty
    or a user-approved marker recorded in each edit; policy is not chosen here.
    """
    result = copy.deepcopy(view)
    if set(result) != VISIBLE_KEYS or not edits:
        raise ValueError("Invalid public view or empty deletion record")
    seen = set()
    for edit in edits:
        path = edit["location"]
        if path in seen:
            raise ValueError("One edit per evidence unit; consolidate spans explicitly")
        seen.add(path)
        parts = path.split("/")
        if parts[0] not in ("pre_text", "post_text", "table"):
            raise ValueError("Only evidence may be edited, not the question or metadata")
        if len(parts) != (3 if parts[0] == "table" else 2):
            raise ValueError("Invalid evidence location")
        indexes = [int(x) for x in parts[1:]]
        if any(i < 0 for i in indexes):
            raise ValueError("Negative indexes forbidden")
        parent = result[parts[0]]
        for index in indexes[:-1]:
            parent = parent[index]
        old = parent[indexes[-1]]
        start, end = edit["start"], edit["end"]
        if not (type(start) is int and type(end) is int and 0 <= start < end <= len(old)):
            raise ValueError("Invalid deletion bounds")
        if old[start:end] != edit["original"]:
            raise ValueError("Deletion span drift")
        replacement = edit["replacement"]
        if replacement and not edit.get("replacement_policy_approval"):
            raise ValueError("A nonempty deletion marker needs explicit policy approval")
        if not edit.get("fact_description"):
            raise ValueError("Every deletion needs a semantic fact description")
        parent[indexes[-1]] = old[:start] + replacement + old[end:]
    return result


def draft_mutations(index_path, specifications, output):
    index = read_json(index_path)
    sources = {r["source_id"]: r for r in index["sources"]}
    specs = read_json(specifications)
    drafts, used = [], set()
    for spec in specs:
        source_id = spec["source_id"]
        if source_id in used:
            raise ValueError("Only one pilot variant per source question")
        used.add(source_id)
        src = sources[source_id]
        variant = apply_edits(src["source"], spec["edits"])
        drafts.append({"source_id": source_id, "family_id": spec.get("family_id"),
                       "source_report_provisional": src["source_report_provisional"],
                       "source_visible_sha256": src["source_visible_sha256"],
                       "variant_sha256": digest(variant), "visible": variant,
                       "source_private": src["source"],
                       "edits_private": spec["edits"], "gold_private": src["gold_private"],
                       "reviews": [], "status": "draft_requires_independent_review"})
    write_new(output, {"status": "draft_not_confirmed_unanswerable",
                       "source_index_sha256": digest_bytes(Path(index_path).read_bytes()),
                       "provenance": index["provenance"],
                       "complete_train_ids_sha256": index["complete_train_ids_sha256"],
                       "drafts": drafts})


def validate_reviews(draft):
    reviews = draft.get("reviews", [])
    if len(reviews) != 2 or len({r.get("reviewer") for r in reviews} - {None, ""}) != 2:
        raise ValueError("Two distinct answerability reviewers required")
    for review in reviews:
        if review.get("variant_sha256") != draft["variant_sha256"]:
            raise ValueError("Review does not bind to current visible evidence")
        for flag in ("necessary_fact_removed", "equivalent_disclosures_checked",
                     "alternative_formulas_checked", "alternative_paths_checked",
                     "target_underdetermined", "question_preserved"):
            if review.get(flag) is not True:
                raise ValueError("Unconfirmed review item: " + flag)
        # A short string is not a mathematical proof; these notes expose reasoning
        # to human audit. The gate verifies completion, not semantic correctness.
        for note in ("missing_fact", "equivalent_disclosure_audit", "alternative_path_audit",
                     "underdetermination_reason", "reviewed_at"):
            if not isinstance(review.get(note), str) or not review[note].strip():
                raise ValueError("Missing review evidence: " + note)
        if review.get("decision") != "unanswerable":
            raise ValueError("Answerability review not unanimously unanswerable")


def freeze(drafts_path, family_registry_path, selection_path, output):
    bundle = read_json(drafts_path)
    registry = read_json(family_registry_path)
    selection = read_json(selection_path)
    if not registry.get("reviewed_by") or not registry.get("definition"):
        raise ValueError("Family registry needs an explicitly reviewed definition")
    if not selection.get("approved_by") or not selection.get("sampling_rule"):
        raise ValueError("Explicitly approved selection rule required")
    selected = selection["source_ids"]
    if len(selected) != 150 or len(set(selected)) != 150:
        raise ValueError("Exactly 150 distinct source questions required")
    lookup = {d["source_id"]: d for d in bundle["drafts"]}
    if len(lookup) != len(bundle["drafts"]):
        raise ValueError("Duplicate draft source IDs")
    all_sources = registry["sources"]
    all_ids = [r["source_id"] for r in all_sources]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Duplicate IDs in family registry")
    reg = {r["source_id"]: r for r in all_sources}
    # Registry must cover the complete train source index, checked by its ID hash.
    if (registry.get("complete_train_ids_sha256") != selection.get("complete_train_ids_sha256")
            or registry.get("complete_train_ids_sha256") != bundle.get("complete_train_ids_sha256")):
        raise ValueError("Selection and family registry refer to different source universes")
    if digest(sorted(all_ids)) != registry.get("complete_train_ids_sha256"):
        raise ValueError("Family registry ID universe hash mismatch")
    for row in all_sources:
        if not row.get("family_id") or not row.get("report_id"):
            raise ValueError("Each source needs reviewed report and family identifiers")
    families, reports, frozen = set(), set(), []
    for source_id in selected:
        draft = lookup[source_id]
        if digest(draft["visible"]) != draft["variant_sha256"]:
            raise ValueError("Mutated draft after review")
        if digest(draft["source_private"]) != draft["source_visible_sha256"]:
            raise ValueError("Source evidence drift")
        if apply_edits(draft["source_private"], draft["edits_private"]) != draft["visible"]:
            raise ValueError("Visible variant not reproducible from deletion record")
        if set(draft["visible"]) != VISIBLE_KEYS:
            raise ValueError("Gold or metadata leaked into visible evidence")
        validate_reviews(draft)
        entry = reg[source_id]
        if entry["report_id"] in bundle.get("protected_official_test_reports", []):
            raise ValueError("Selected report overlaps protected official test reports")
        if draft["family_id"] != entry["family_id"]:
            raise ValueError("Draft and reviewed family registry disagree")
        families.add(entry["family_id"])
        reports.add(entry["report_id"])
        frozen.append(draft)
    # Transitive closure over report and family links prevents indirect leakage.
    previous = None
    while previous != (len(families), len(reports)):
        previous = (len(families), len(reports))
        for row in all_sources:
            if row["family_id"] in families or row["report_id"] in reports:
                families.add(row["family_id"])
                reports.add(row["report_id"])
    excluded = sorted(r["source_id"] for r in all_sources
                      if r["family_id"] in families or r["report_id"] in reports)
    if reports.intersection(bundle.get("protected_official_test_reports", [])):
        raise ValueError("Family/report transitive closure reaches protected official test reports")
    demo_reports = {reg[i]["report_id"] for i in bundle.get("demonstration_source_ids", []) if i in reg}
    if reports.intersection(demo_reports):
        raise ValueError("Selected family/report closure overlaps few-shot demonstrations")
    write_new(output, {"status": "frozen_reviewed_150", "provenance": bundle["provenance"],
                       "drafts_sha256": digest_bytes(Path(drafts_path).read_bytes()),
                       "family_registry_sha256": digest_bytes(Path(family_registry_path).read_bytes()),
                       "selection": selection, "sources": frozen,
                       "exclude_from_future_training_and_formal_tests": excluded,
                       "excluded_families": sorted(families), "excluded_reports": sorted(reports)})


def inventory(output):
    pot = ROOT / "reproductions/pot"
    official_path = ROOT / "reproductions/gbfr/data/raw/official/FinQA.json"
    rows = load_finqa(official_path)
    artifacts = []
    for relative in ("reproductions/pot/scripts/protocol.py",
                     "reproductions/pot/scripts/execute_worker.py",
                     "reproductions/pot/vendor/run_finqa.py",
                     "reproductions/pot/vendor/data/finqa_test.json",
                     "reproductions/gbfr/data/raw/official/FinQA.json",
                     "reproductions/verifin/upstream/src/verifiqa/answerers/cot.py",
                     "scripts/logic_final.py"):
        path = ROOT / relative
        artifacts.append({"path": relative, "sha256": digest_bytes(path.read_bytes())})
    # Extract prompt/build function without importing scripts that run API code.
    tree = ast.parse((pot / "vendor/run_finqa.py").read_text())
    prompt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "prompt_4shot" for t in n.targets))
    write_new(output, {"status": "offline_inventory_not_experiment_results",
                       "baseline_commit": git_commit(ROOT),
                       "pot_vendor_commit": git_commit(pot / "vendor"),
                       "logic_vendor_commit": git_commit(ROOT / "upstream/Logic-LLM"),
                       "official_finqa_test_count": len(rows),
                       "official_test_provenance": read_json(official_path.with_suffix(".source.json")),
                       "train_present_in_original_baseline": False,
                       "pilot_official_train_download_present": (HERE / "local/raw/train.json").exists(),
                       "pot_4shot_sha256": digest_bytes(prompt.encode()),
                       "artifacts": artifacts,
                       "findings": ["PoT financial path available; test split only",
                                    "Logic-LM CoT is a different task/domain",
                                    "VeriFin financial CoT includes explicit abstention instruction",
                                    "Do not reuse a test split as the pilot train split"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("inventory")
    p.add_argument("--output", required=True)
    p = commands.add_parser("index")
    p.add_argument("--train", required=True)
    p.add_argument("--provenance", required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("draft")
    p.add_argument("--index", required=True)
    p.add_argument("--edits", required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("freeze")
    p.add_argument("--drafts", required=True)
    p.add_argument("--families", required=True)
    p.add_argument("--selection", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "inventory":
        inventory(args.output)
    elif args.command == "index":
        index_sources(args.train, args.provenance, args.output)
    elif args.command == "draft":
        draft_mutations(args.index, args.edits, args.output)
    else:
        freeze(args.drafts, args.families, args.selection, args.output)


if __name__ == "__main__":
    main()
