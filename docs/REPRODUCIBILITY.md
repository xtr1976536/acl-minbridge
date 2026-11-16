# 复现说明

## 推荐入口

1. `python scripts/verify_release.py`：核对150题、18条件、每条件150条、2,700条输出/标注绑定、原始尝试完整性与最新PDF哈希。
2. `python scripts/recompute.py`：无网络重算两政策、全部条件、研究问题比较和敏感性结果，并与公开JSON逐项对比。
3. `python scripts/run_models.py`：只读展示完整请求数量；`--execute`显式启用新的付费调用。
4. `python scripts/judge_outputs.py`：只读检查主评审请求；`--execute`显式启用新的GPT评审。

每次新API运行必须使用新的`work/`输出目录。不会覆盖旧结果，不会静默重试内容拒绝或账户额度错误。生成程序复用原受限PoT执行器，子进程不接收API密钥环境。

## 文件解压与历史路径

`scripts/materialize.py`依据`publication/materialization.json`校验哈希后解压到历史代码所用的相对目录。已存在且内容不同的本地文件不会被覆盖。该过程只读本仓库，不联网。

`reproductions/relational-pilot/`保留本次实际使用的生成、补跑、机审、源材料诊断、统计和报告代码。`run.py`仅保留实际PoT执行器调用函数；当前API重放入口是`run_models.py`。没有执行过的旧型号运行器、人工裁决/正式分析占位流程及其配置与测试已删除。API校准和原版8,192-token记录确实属于本次实验，仅作为追溯材料保留。

`reproductions/pot/`只含FinQA四示例及输入构造函数、受限执行器与其依赖工具。未发布或运行FinQA官方测试集评测，也没有包含其他数据集的PoT分支。可选的数据构造下载官方test仅用于核对源报告隔离，不会作为本次150题的评测输入。

运行本阶段测试前先执行`python scripts/materialize.py`，使压缩发布的数据出现在测试所需的本地兼容路径。随后运行`python -m unittest discover -s reproductions/relational-pilot/tests -q`和`python -m unittest discover -s reproductions/relational-pilot/v2 -p test_review_set.py -q`。共23项检查只覆盖本次实际输入构造、提示、程序执行和统计语义，不包含未执行的人工裁决占位流程。

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
