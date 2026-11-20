# acl-minbridge

## 第一阶段：关系幻觉预研

基于FinQA训练集构造150道不可答题，使用GPT-5.6 Sol、DeepSeek-V4-Pro和Qwen3.8-27B，比较配对CoT、PoT和原有拒答CoT在不同推理强度下的关系幻觉、数值幻觉和拒答表现。

共完成2,700条模型输出：3个模型 × 3种推理框架 × 2档设置 × 150道题。

独立标签统计：数值幻觉227条（8.41%），关系幻觉379条（14.04%），两类同时出现22条。611条错误作答中，含关系幻觉的有379条（62.03%）。

完整结果和中文汇报见：

- [中文汇报PDF](reports/MinBridge_关系幻觉预研_中文汇报.pdf)
- [完整实验记录](results/records/expanded/)
- [统计结果](results/tables/结果统计.json)

## 第二阶段：MinBridge与baseline对比实验

MinBridge与各类baseline将在以下四个任务上进行对比实验，使用FinQA、FinDER及其构造版本，以及MPB。

| 实验 | 目的 | 使用的数据 |
|---|---|---|
| **E1 可答题测试** | 测试答案准确率，以及模型是否错误拒答可答题。 | FinQA官方test集，1,147题。 |
| **E2 不可答题测试** | 测试关系幻觉、数值幻觉及正确拒答的比例。 | FinQA构造题150道、FinDER构造题150道。 |
| **E3 受控对照实验** | 比较删除必要事实与删除无关事实对模型表现的影响。 | 同一批150道FinQA源题的O/K/N版本：O保留原题，K使用E2不可答题，N删除非必要事实但仍可答。 |
| **E4 跨域测试** | 测试非金融缺前提问题上的泛化能力。 | MPB，274题，全部保留为测试。 |

FinDER的150道候选题已完成五轮机器检查，低／中／高删除组各90／30／30题；人工终审和模型实验尚未开展。E3的N组候选已构造，148题与K删除相同数量的事实，第20、103题N与O相同。MPB已收录，尚未运行模型。

- [FinDER最新数据与审核记录](data/finder150/README.md) · [中文审核PDF](reports/FinDER_150题_中文删除标注版.pdf)
- [FinDER构造与重放代码](reproductions/finder150/README.md)
- [FinQA O/K/N配对索引](data/n_control_pair_index.csv) · [N组数据](data/n_control_150.json.gz)
- [MPB数据](data/external/mpb/README.md)
