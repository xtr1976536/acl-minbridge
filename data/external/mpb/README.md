# E4：MPB 274题跨域测试数据

原始数据来自 Ant International 发布的 [MPB_Missing-Premise-Benchmark](https://huggingface.co/datasets/ant-intl/MPB_Missing-Premise-Benchmark)，对应论文 [Ask, Condition or Abstain: Reinforcement Learning for Missing-Premise Reasoning](https://arxiv.org/abs/2608.16554)。

- `MPB.parquet`：未经修改的上游原始文件，共274条。
- `UPSTREAM_README.md`：原样保留的上游数据卡。
- `source.json`：固定版本、来源及SHA-256校验值。
- `LICENSE`：上游数据卡声明的Apache-2.0许可全文。

本项目将全部274题保留为E4测试，不参与训练、提示、阈值或奖励调节。上游分区虽名为`train`，不代表本项目将其用于训练。

模型输入只使用`prompt`。`reward_model`以及`extra_info`中的原题、缺项分析和扰动标签仅用于审核与评分，不发送给被测模型。上游README中的HRB名称和示例占位路径按原样保留；实际数据源以上述链接和`source.json`为准。

当前仅收录数据，尚未进行本项目的E4模型评测。
