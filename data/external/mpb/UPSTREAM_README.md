---
pretty_name: "MPB: Missing-Premise Reasoning Benchmark"
license: apache-2.0
language:
  - en
task_categories:
  - question-answering
  - text-generation
size_categories:
  - n<1K
tags:
  - benchmark
  - reasoning
  - missing-premise
  - uncertainty
  - abstention
  - clarification
  - text
---

# HRB: Missing-Premise Reasoning Benchmark

HRB is the Hugging Face release of the **Missing-Premise Benchmark (MPB)** introduced in [*Ask, Condition or Abstain: Reinforcement Learning for Missing-Premise Reasoning*](https://arxiv.org/abs/2608.16554).

The benchmark contains **274 human-verified instances** designed to evaluate whether a language model can recognize when a problem is underdetermined and respond constructively—by asking for the missing premise, conditioning its answer on an unknown variable, or abstaining—instead of fabricating a definite answer.

## Benchmark Overview

HRB covers mathematical, logical, and real-world word problems. Each instance is created by transforming a well-posed source problem into a fluent but underdetermined problem with a localized informational gap.

The benchmark covers six missing-premise perturbation categories:

- **Relationship Removal**: removes a relation required to determine the answer.
- **Relationship Unquantifiable Replacement**: replaces a precise relation with an indefinite one.
- **Numerical Value Removal**: removes a required numerical value.
- **Entity Disruption**: replaces a relevant entity with an unrelated but plausible entity.
- **Qualifier Disruption**: changes or removes a qualifier required by the original constraint.
- **Condition Contraction**: restricts the domain of a condition so that it no longer covers the query.

HRB is constructed from a held-out candidate pool and is not included in the 120K missing-premise instances used for ACA-RL training.

## Data Construction and Verification

Source problems are drawn from [Tong et al. (2023)](https://arxiv.org/abs/2310.12342) and [DeepScaleR](https://huggingface.co/datasets/agentica-org/DeepScaleR-Preview-Dataset).

Construction follows a multi-stage process:

1. A reasoning graph is built for each well-posed source problem.
2. A premise on the solution path is removed or modified.
3. The perturbed conditions are rewritten into a fluent problem statement.
4. Automated checks remove malformed or still-answerable examples.
5. Three human experts verify the original and perturbed problem pair, the missing-premise analysis, and the overall example quality.

Conceptually, each benchmark instance contains:

- the original well-posed problem;
- the perturbed missing-premise problem;
- an annotation describing the informational gap;
- the perturbation category and associated metadata.

Please refer to the Dataset Viewer for the serialized column names.

## Loading the Dataset

```python
from datasets import load_dataset

dataset = load_dataset("YOUR_ORG/HRB")

print(dataset)

for split_name, split in dataset.items():
    print(split_name, split.column_names)
    print(split[0])
```

This example discovers the available splits and columns rather than assuming a fixed schema.

## Evaluation

A model response is assigned to one of five terminal behavior categories:

| Behavior | Score | Description |
|---|---:|---|
| Silent Hallucination | 0 | Produces a definite answer using fabricated or unstated information |
| Explicit Assumption | 25 | States an unsupported assumption and answers under that assumption |
| Abstention | 50 | Recognizes that the problem is underspecified and declines to give a definite answer |
| Conditional Formulation | 75 | Represents the missing information as a variable and provides a conditional answer |
| Active Elicitation | 100 | Asks for the specific missing premise needed to answer the question |

The benchmark-level **Behavior Score** is the arithmetic mean of the per-instance scores.

The accompanying paper uses GPT-5 as the behavior judge. In a sampled agreement study, human annotations agreed with the judge on approximately 98% of GPT-5 responses and 95% of Qwen3-235B-A22B-Instruct responses.

For reproducible comparisons, evaluations should report:

- model and checkpoint;
- reasoning or direct-answer mode;
- generation parameters;
- judge model and prompt;
- overall Behavior Score;
- behavior distribution;
- per-perturbation scores.

## Intended Uses

HRB is intended for:

- evaluating missing-premise recognition;
- measuring hallucination, assumption, abstention, conditioning, and clarification behavior;
- comparing uncertainty-aware reasoning methods;
- diagnosing behavior across different types of informational gaps.

HRB is not designed to measure factual knowledge, probability calibration, retrieval ability, or multi-turn clarification success.

## Limitations

- The benchmark contains 274 instances and may not represent the full diversity of real-world underspecification.
- Its examples are produced through controlled structural perturbations and may not capture all organic, implicit, or semantic ambiguities.
- Active elicitation is evaluated as a single-turn textual response; the benchmark does not test whether a model can acquire the missing information through subsequent interaction or tool use.
- The Behavior Score encodes a specific preference hierarchy and should not be interpreted as a calibrated uncertainty measure.
- Automatic judging may introduce evaluator bias despite the reported human-agreement checks.

## Citation

```bibtex
@misc{tong2026ask,
  title        = {Ask, Condition or Abstain: Reinforcement Learning for Missing-Premise Reasoning},
  author       = {Yongqi Tong and Zhenyu Zhang and Zimi Liu and Kewei Fu and
                  Mingli Song and Haofei Zhang and Junshao Zhang and Hong Zhu and
                  Jiang-Ming Yang and Xin Zhang and Jianshe Li},
  year         = {2026},
  eprint       = {2608.16554},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL},
  url          = {https://arxiv.org/abs/2608.16554}
}
```