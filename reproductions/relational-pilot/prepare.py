"""Offline preparation only. Never calls a model, labels data, or executes model code.

The train split, mutations and review records are explicit inputs. An approved
gold program is a fact locator, never an unanswerability certificate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
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
