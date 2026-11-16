# 复现说明

## 推荐入口

1. `python scripts/verify_release.py`：核对150题、18条件、每条件150条、2,700条输出/标注绑定、原始尝试完整性与最新PDF哈希。
2. `python scripts/recompute.py`：无网络重算两政策、全部条件、研究问题比较和敏感性结果，并与公开JSON逐项对比。
3. `python scripts/run_models.py`：只读展示完整请求数量；`--execute`显式启用新的付费调用。
4. `python scripts/judge_outputs.py`：只读检查主评审请求；`--execute`显式启用新的GPT评审。

每次新API运行必须使用新的`work/`输出目录。不会覆盖旧结果，不会静默重试内容拒绝或账户额度错误。生成程序复用原受限PoT执行器，子进程不接收API密钥环境。

## 文件解压与历史路径

`scripts/materialize.py`依据`publication/materialization.json`校验哈希后解压到历史代码所用的相对目录。已存在且内容不同的本地文件不会被覆盖。该过程只读本仓库，不联网。

`reproductions/relational-pilot/`中保留了本次所有阶段的代码；旧`run.py`是早期固定型号的形式化门槛入口，当前三模型重放使用`run_models.py`。`analyze.py`是尚未进行的独立人工裁决流程；当前机器统计使用`analyze_expanded.py`，两者没有冒充彼此。

## 图表与中文报告

```bash
python scripts/recompute.py --figures
python scripts/recompute.py --report
```

统计重算只需要NumPy；图表需要Matplotlib，中文PDF需要ReportLab/PyPDF以及兼容的中文字体。报告原本在macOS上使用系统宋体/黑体，字体文件不随仓库分发。其他系统可根据本机可用字体调整`make_chinese_briefing.py`的字体注册及`briefing_revision_content.py`排版。最终17页PDF和图像可直接阅读。

新构建的报告可能因字体/库版本而产生不同PDF二进制；这不改变数据和统计。发布文件的精确校验以`publication/files.json`为准。

## 重新构造150题（可选）

本仓库已经公开冻结的150题和必要修改账本。要从上游原始训练集重新构造：

```bash
python scripts/materialize.py
python scripts/fetch_official_finqa.py --download
python reproductions/relational-pilot/v2/build_set.py
```

下载固定提交的官方train/test，训练集校验值为`49f237eb9779b569473b26b08048867d04635a7cc39ad6a7a5664c55bb428db6`。构造过程依赖已发布的150题初始选择、事实修改规则及AI复核记录，不声称它是FinQA总体的无偏随机样本。请先备份本地修改；构造脚本是历史导出器，会重写其本地输出。源题仍待独立人工可答性核验。

## 已知未完成项

- 两条主评审被提供方内容校验拒绝，按未知保留，未尝试绕过。
- 内部机器复核完成656/682条，26条遇到提供方额度不足；另有机械校验/复核未决标记。
- 人工可答性核验、两位人员盲标及独立裁决尚未完成。
- 一条事实去重计数校勘保存在`data/fact_count_erratum.json`；没有依据模型结果改题或重分组。
