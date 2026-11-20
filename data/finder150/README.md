# FinDER人工改造题：150题

从FinDER选取150道源题，删除必要数量事实及对应的重复披露或恢复路径，构造候选不可答材料。低、中、高删除组分别为90、30、30题。删除比例按删除的去重数量事实数除以原始可见材料中的数量事实数计算。

- `model_inputs_150.json`：最新英文问题和删后材料，适配现有CoT/PoT输入格式。
- `final_150_review.json.gz`：原文、删后材料、数量事实清单、删除位置、公式及五轮机器审核记录。
- `construction_plan.json.gz`、`selected_sources.json.gz`：最终删除方案及150条未经修改的源记录，用于独立重放。
- `group_index.csv`、`origin_index.json`：分组、删除比例和题源类型。
- `latest_checks.json`、`audit_summary.json`：当前150题检查及状态；`history/`保留之前审核过程。
- `translations_zh.json.gz`、术语表及中文文本：重建中文审核PDF所需材料。
- `pdf_validation.json`、`layout_source_validation.json`、`release_manifest.json`：PDF完整性、数字保留和文件校验。

源数据及派生数据遵循上游标注的[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)，并须署名原作者。来源、固定版本和论文见`source.json`及仅清理行尾空格的`UPSTREAM_README.md`。本数据的许可不由仓库根目录的软件许可替代。

数据已完成五轮程序与同一AI助手的检查，仍为候选不可答题；这些检查不等同于独立人工金标。当前无FinDER模型实验结果。历史阶段记录中的中间源题已被最终删除方案取代；正式运行应仅使用本目录的最新英文模型输入。
