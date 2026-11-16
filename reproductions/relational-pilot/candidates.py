"""Draft candidates for human review; this is not a 150-item gold dataset.

No model outputs are used for selection. Exact-value duplicates are removed in
all evidence units; unit-scaled paraphrases and alternative paths still require
human review. No statement here certifies semantic unanswerability.
"""
import argparse
import copy
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from prepare import (HERE, apply_edits, digest, evidence_units, program_operands,
                     read_json, write_new)
from prompts import demo_questions


NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")


def numeric_tokens(text):
    result = []
    for match in NUMBER.finditer(str(text)):
        try:
            result.append((Decimal(match[0].replace(",", "")), match.start(), match.end()))
        except InvalidOperation:
            pass
    return result


def norm(text):
    return " ".join(text.lower().split())


def build(index_path, output, queue_seed):
    index = read_json(index_path)
    questions = {norm(q) for q in demo_questions()}
    demo_sources = [s for s in index["sources"] if norm(s["source"]["question"]) in questions]
    demo_reports = {s["source_report_provisional"] for s in demo_sources}
    drafts, excluded = [], []
    # Hash ordering creates a reproducible review queue, not a frozen sampling rule.
    sources = sorted(index["sources"], key=lambda s: digest([queue_seed, s["source_id"]]))
    for src in sources:
        if src["source_report_provisional"] in demo_reports:
            excluded.append({"source_id": src["source_id"], "reason": "demonstration_source_report"})
            continue
        options = []
        for arg in program_operands(src["gold_private"].get("program", "")):
            try:
                value = Decimal(arg.replace(",", ""))
            except InvalidOperation:
                continue
            # Constant-like and year-like values need case-specific treatment.
            if abs(value) <= 10 or (value == value.to_integral_value() and 1900 <= abs(value) <= 2100):
                continue
            if any(v == value for v, *_ in numeric_tokens(src["source"]["question"])):
                continue
            units = []
            protected_match = False
            for location, text in evidence_units(src["source"]):
                if not any(abs(v) == abs(value) for v, *_ in numeric_tokens(text)):
                    continue
                # Preserve headings and row labels, avoiding invalid problem structure.
                if location.startswith("table/") and (location.split("/")[1] == "0" or location.endswith("/0")):
                    protected_match = True
                    break
                units.append((location, text))
            if units and not protected_match:
                options.append((len(units), str(value), units))
        if not options:
            excluded.append({"source_id": src["source_id"], "reason": "no_conservative_numeric_operand_candidate"})
            continue
        _, value, units = min(options, key=lambda x: (x[0], x[1]))
        edits = [{"location": loc, "start": 0, "end": len(text), "original": text,
                  "replacement": "", "fact_description": f"Draft removal of evidence unit containing gold operand {value}; semantic identity requires review"}
                 for loc, text in units]
        variant = apply_edits(src["source"], edits)
        # Flag, do not silently treat numeric coincidences as financial identities.
        scaled = []
        base = abs(Decimal(value))
        scaled_values = {base / 100, base * 100, base / 1000, base * 1000,
                         base / 1000000, base * 1000000}
        for loc, text in evidence_units(variant):
            if any(abs(v) in scaled_values for v, *_ in numeric_tokens(text)):
                scaled.append(loc)
        drafts.append({"source_id": src["source_id"], "family_id": None,
                       "source_report_provisional": src["source_report_provisional"],
                       "source_visible_sha256": src["source_visible_sha256"],
                       "variant_sha256": digest(variant), "visible": variant,
                       "source_private": copy.deepcopy(src["source"]),
                       "gold_private": src["gold_private"], "edits_private": edits,
                       "removed_operand_hint": value,
                       "possible_unit_scaled_disclosures": scaled,
                       "reviews": [], "status": "automatic_draft_not_verified_unanswerable"})
    write_new(output, {"status": "review_queue_not_final_sample", "queue_seed": queue_seed,
                       "queue_order": "sha256([seed, source_id]); all eligible records retained",
                       "provenance": index["provenance"],
                       "complete_train_ids_sha256": index["complete_train_ids_sha256"],
                       "demonstration_source_ids": [s["source_id"] for s in demo_sources],
                       "demonstration_reports_excluded": sorted(x for x in demo_reports if x),
                       "candidate_count": len(drafts), "excluded_count": len(excluded),
                       "excluded": excluded, "drafts": drafts})
    return len(drafts), len(excluded)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--queue-seed", required=True)
    a = p.parse_args()
    print(json.dumps(dict(zip(("candidates", "excluded"), build(a.index, a.output, a.queue_seed)))))
