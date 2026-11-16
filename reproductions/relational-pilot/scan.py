"""Numeric alternative-path hints, not semantic proofs of answerability."""
import argparse
import copy
from fractions import Fraction

from candidates import numeric_tokens
from prepare import evidence_units, read_json, write_new


def alternate_paths(view, target, max_witnesses=10):
    # Include all visible numeric tokens, including the question and headings.
    values = {}
    for location, text in [("question", view["question"]), *evidence_units(view)]:
        for number, start, end in numeric_tokens(text):
            values.setdefault(Fraction(number), f"{location}[{start}:{end}]")
    target = Fraction(str(target))
    paths = []
    if target in values:
        paths.append({"steps": 0, "expression": values[target], "reason": "same_numeric_value_remains"})
    # Store witnesses for one-op results. At most two total arithmetic operators.
    intermediate = {}
    for a in values:
        for b in values:
            operations = [(a+b, "+"), (a-b, "-"), (a*b, "*")]
            if b:
                operations.append((a/b, "/"))
            for result, op in operations:
                intermediate.setdefault(result, f"({values[a]} {op} {values[b]})")
    if target in intermediate:
        paths.append({"steps": 1, "expression": intermediate[target]})
    for leaf, location in values.items():
        needed = [(target-leaf, "({v} + {x})"), (target+leaf, "({v} - {x})"),
                  (leaf-target, "({x} - {v})")]
        if leaf:
            needed += [(target/leaf, "({v} * {x})"), (target*leaf, "({v} / {x})")]
        if target:
            needed.append((leaf/target, "({x} / {v})"))
        for value, template in needed:
            if value in intermediate and not (template == "({x} / {v})" and not value):
                paths.append({"steps": 2, "expression": template.format(v=intermediate[value], x=location)})
            if len(paths) >= max_witnesses:
                break
        if len(paths) >= max_witnesses:
            break
    return {"distinct_numeric_values": len(values), "max_arithmetic_operators": 2,
            "unit_and_semantic_validation": "required_human_review",
            "warning": "Numeric coincidences are not evidence-supported financial formulas; absence of a hit is not proof of unanswerability",
            "witnesses": paths[:max_witnesses]}


def make_review_batch(queue, count, output):
    data = read_json(queue)
    batch = copy.deepcopy(data)
    batch["drafts"] = batch["drafts"][:count]
    batch["status"] = "first_review_batch_not_frozen_not_a_gold_sample"
    batch["batch_count"] = len(batch["drafts"])
    batch["selection_note"] = "First entries of the documented hash-ordered candidate queue; may be replaced after review, never selected using model outcomes"
    for draft in batch["drafts"]:
        draft["numeric_path_scan"] = alternate_paths(draft["visible"], draft["removed_operand_hint"])
    write_new(output, batch)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queue", required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    if a.count <= 0:
        p.error("count must be positive")
    make_review_batch(a.queue, a.count, a.output)
