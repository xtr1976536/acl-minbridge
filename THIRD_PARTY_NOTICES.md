# Third-party materials

## FinQA

Chen et al., *FinQA: A Dataset of Numerical Reasoning over Financial Data*, EMNLP 2021. Source: https://github.com/czyssrs/FinQA at commit `0f16e2867befa6840783e58be38c9efb9229d742`.

The upstream repository publishes an MIT license (Copyright 2021 Zhiyu Chen), retained in `third_party/FinQA_LICENSE`. The 150-question derivative preserves upstream IDs and original/edited evidence plus explicit modification records. Underlying issuer report material retains its applicable source terms. No original full report PDFs are redistributed.

## Program of Thoughts

Chen, Ma, Wang, and Cohen, *Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks*, TMLR 2023. Source: https://github.com/TIGER-AI-Lab/Program-of-Thoughts at commit `850399c3eff8c37458a9d642c4a98df287f50f3a`.

The minimal FinQA prompt/builder, test-format file and execution utility are retained under the upstream MIT license in `reproductions/pot/vendor/LICENSE` and `third_party/PoT_LICENSE`. The local guarded worker is an execution compatibility layer, not a hostile-code sandbox.

## Chain of Thought and VeriFin

Wei et al., *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models*, https://arxiv.org/abs/2201.11903.

The paired CoT is a local adaptation of the PoT four examples, not an untouched prompt attributed to the CoT or PoT authors.

The abstention-enabled CoT uses the short functional prompt recorded in VeriFin's `CotAnswerer`: https://github.com/verifiedfinance/anon/blob/main/src/verifiqa/answerers/cot.py. Related paper: https://arxiv.org/abs/2608.10213. The exact experimental prompt is preserved as an input record. The upstream VeriFin artifact does not select a software redistribution license, so its full source package/datasets are **not** vendored or relicensed here; `prompts.py` loads the experiment's prompt snapshot instead.

## This repository

Original local implementation code is MIT-licensed in `LICENSE`; this does not replace upstream notices or grant new rights to third-party datasets. Frozen result rows, inputs and prompts retain their recorded provenance. No credentials, full research proposal or private approval conversation is a research artifact in this release.
