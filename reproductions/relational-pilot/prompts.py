"""Native PoT prompt reuse and two separately named CoT treatments."""
import ast
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POT_SCRIPTS = ROOT / "reproductions/pot/scripts"
sys.path.insert(0, str(POT_SCRIPTS))
from protocol import official  # AST extraction, no API import


METHODS = ("cot_paired_4shot", "pot", "cot_existing_abstention")
SOLUTIONS = (
    "The table reports 14001 of available-for-sale investments and 26302 of total "
    "cash and investments for December 29, 2012. Calculate the requested share as "
    "14001 / 26302. Final answer: approximately 0.5323169341 (53.23169341%).",
    "The text reports 12 days exceeding $210 million and 261 trading days. Calculate "
    "12 / 261. Final answer: approximately 0.04597701149 (4.597701149%).",
    "The disclosed intangible amounts are 75.0 million and 72.7 million. The text "
    "says amortization is straight-line over periods of up to 20 years; using 20 "
    "years gives (75.0 + 72.7) / 20 = 7.385 million per year. Final answer: "
    "7.385 million per year using a 20-year period.",
    "The table reports 28.76 billion in 2007 and 23.89 billion in 2008. Calculate "
    "the percentage change relative to 2007: (23.89 - 28.76) / 28.76. Final "
    "answer: approximately -0.1693324061 (-16.93324061%).",
)


@lru_cache(maxsize=1)
def parts():
    demo, builder, _, meta = official("finqa")
    blocks = [block.strip() for block in demo.strip().split("\n\n\n") if block.strip()]
    if len(blocks) != 4 or any("\n#Python\n" not in b for b in blocks):
        raise ValueError("PoT demonstration source changed; inspect before adapting")
    return demo, builder, meta, blocks


@lru_cache(maxsize=1)
def paired_demo():
    _, _, _, blocks = parts()
    examples = []
    for block, solution in zip(blocks, SOLUTIONS):
        evidence = block.split("\n#Python\n")[0]
        evidence = evidence.replace("and then write code to answer a question:",
                                    "and then explain the facts, formula and calculation to answer a question:", 1)
        examples.append(evidence + "\nReasoning:\n" + solution)
    return "\n\n\n".join(examples)


@lru_cache(maxsize=1)
def existing_template():
    import json
    path = ROOT / "data/prompt_snapshot.json"
    return json.loads(path.read_text(encoding="utf-8"))["cot_existing_abstention"]


def processed(view):
    # The exact data conversion used by the existing PoT input format.
    return {"question": view["question"],
            "text": " ".join(view["pre_text"] + view["post_text"]),
            "table": "\n".join(" | ".join(c or "-" for c in row) for row in view["table"])}


def messages(method, view):
    demo, builder, _, _ = parts()
    item = processed(view)
    if method == "pot":
        return [{"role": "system", "content": "Complete the Python program requested by the final example. Return only executable Python statements assigning ans (and units when the examples use units). No Markdown fences or prose. Do not repeat the examples."},
                {"role": "user", "content": demo + "\n\n" + builder(item)}]
    if method == "cot_paired_4shot":
        final = builder(item).replace("and then write code to answer a question:",
                                      "and then explain the facts, formula and calculation to answer a question:", 1)
        final = final.removesuffix("#Python\n") + "Reasoning:\n"
        return [{"role": "user", "content": paired_demo() + "\n\n" + final}]
    if method == "cot_existing_abstention":
        # Retain existing prompt wording; adapt only the FinanceBench evidence input.
        evidence = "[provided_evidence]\n" + item["text"] + "\n" + item["table"]
        return [{"role": "user", "content": existing_template().format(
            question=item["question"], evidence=evidence)}]
    raise ValueError(method)


def demo_questions():
    return [b.split("Question: ", 1)[1].split("\n#Python", 1)[0].strip()
            for b in parts()[3]]


if __name__ == "__main__":
    print("# Prompt review\n\n## Paired 4-shot CoT\n\n" + paired_demo())
    print("\n\n## Existing financial CoT (abstention instruction retained)\n\n" + existing_template())
    print("\n\n## PoT\n\nThe original 4-shot prompt is preserved without rewriting.\n")
    print(parts()[0])
