# acl-minbridge

MinBridge 第一阶段：FinQA不可答题上的数值幻觉与关系幻觉预研。

本仓库公开已运行的代码、150道题的版本与修改记录、2,700条完整模型输出、GPT机器标注、分析结果、图表及中文汇报。**完整研究计划、密钥、内部沟通记录和本机环境没有包含在发布中。**

## 中文汇报

**[阅读最新中文汇报 PDF](reports/MinBridge_关系幻觉预研_中文汇报.pdf)**（17页，24张表，5幅图）。

报告包含当前严格判定定义、150题中真实的关系错误实例、两种CoT的来源与实际提示，以及以下三个研究问题：

1. 关系幻觉是否存在，比例如何？
2. 不同推理框架下，关系幻觉的分布如何？
3. 推理强度对关系幻觉有何影响？

## 数据与当前状态

150道源题来自150份FinQA训练集报告，低/中/高删除组为90/30/30。每题运行三个模型、三套提示和两档设置：`150 × 3 × 3 × 2 = 2,700` 条输出。

| 项目 | 当前公开记录 |
|---|---:|
| 正常结束生成 | 2,700 / 2,700 |
| 生成连接中断或长度截断 | 0 |
| GPT主评审尝试 | 2,700 |
| 有效结构化主评审返回 | 2,698 |
| 内部机器复核完成 | 656 / 682 |
| 未决/校验标记 | 46条（标记可能重叠） |

2条主评审受到提供方内容校验拒绝，26条内部复核未完成；全部保留未知/未决状态。**生成已经完成，不代表独立人工审核和标注已经完成。** 382条PoT程序没有得到有效数值，其中包含拒答，不能直接当作幻觉。后续需要人工检查源题可答性、机器标注及程序无数值的原因。

## 结果快照

下表为当前GPT机审统计，分母均保留全部2,700条输出，不是2,700道独立源题。

| 测量口径 | 数值幻觉 | 关系幻觉/关系代理 | 同时出现 |
|---|---:|---:|---:|
| 数字溯源互斥代理 | 227（8.41%） | 384（14.22%） | 0 |
| 独立标签 | 227（8.41%） | 379（14.04%） | 22 |

独立标签下，611条错误作答中379条含关系幻觉，占62.03%。这与“全部输出中14.04%”使用不同分母。合法条件回答与明确放弃的错误思路单列；未知记录不等于已确认无幻觉。只有原未完成条件获得更大预算，本批属于适应性预算后的探索比较，不能据此宣称严格同预算的因果效应或已验证的人工金标。

## 文件位置

| 路径 | 内容 |
|---|---|
| [`reports/`](reports/) | 最新修订中文PDF及图表 |
| [`data/`](data/) | 英文输入150题、原题/修改/事实账本、构造审核记录和已知校勘 |
| [`results/tables/`](results/tables/) | 逐条输出与评审CSV、分条件比例、统计JSON、可答性诊断 |
| [`results/records/expanded/`](results/records/expanded/) | 更新输出、所有补跑/机审/内部复核尝试和被冻结的请求 |
| [`results/records/english150-20261116-v2/`](results/records/english150-20261116-v2/) | 原始统一8,192-token版本及请求记录 |
| [`results/calibration/`](results/calibration/) | 接口及生成预算校准记录，不能追加进主矩阵分母 |
| [`reproductions/relational-pilot/`](reproductions/relational-pilot/) | 实际使用的生成、判读、分析、构造和报告代码 |
| [`scripts/`](scripts/) | 安全的公开入口：离线核验、重算、显式付费重跑 |
| [`publication/`](publication/) | 文件清单、哈希、完整性及两轮公开检查记录 |

较大的JSONL和CSV以标准gzip无损压缩，文件名以`.gz`结尾；Python标准库即可读取。记录中含可公开的金融证据、模型可见回答/思考与用量，不含API凭证。原题金标仅用于核查，**不能混入生成模型输入**。

## 离线核验与重算

Python 3.12，推荐独立虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/verify_release.py
python scripts/recompute.py
```

这些命令不读取API密钥、不发起模型调用。重算会验证结果与发布统计完全一致；解压的兼容目录和重新生成的文件位于已忽略的`local/`、`output/`等目录。

重绘图或构建报告见[复现说明](docs/REPRODUCIBILITY.md)。原图和最终PDF已直接提供，不必为了阅读报告安装绘图库或字体。

## API重跑（需要自行提供凭证并承担费用）

默认仅检查请求，不调用API：

```bash
python scripts/run_models.py
python scripts/judge_outputs.py --limit 6
```

只有显式添加`--execute`才提交请求；密钥从环境变量或不回显的终端输入读取。不要将密钥写入代码、命令行实参、配置文件、Issue或提交记录。

```bash
python scripts/run_models.py --provider openai --limit 1 --execute --out work/new-generation
python scripts/judge_outputs.py --limit 1 --execute --out work/new-judge
```

模型和提示设置见[方法与数据说明](docs/METHODS_AND_DATA.md)。本次实际用到的三API生成、补跑、PoT执行、机审和统计脚本保留；旧型号运行器与未执行的正式裁决占位流程已清除；保留了150题实际构造用的候选、隔离和证据路径扫描代码。公开入口不会覆盖已发布结果，遇到API或内容校验错误会停下并保存状态。

## 署名与第三方材料

FinQA与PoT保留其MIT许可证和来源。原有拒答CoT记录为VeriFin代码中的功能性提示；没有重新发布VeriFin的完整代码包。两种CoT的来源、适配与限制见[第三方材料说明](THIRD_PARTY_NOTICES.md)。本仓库不声称提出了原始CoT或PoT方法。
