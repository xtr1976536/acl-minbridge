# FinDER 150题构造与检查

最新数据位于 `data/finder150/`，中文审核PDF位于 `reports/FinDER_150题_中文删除标注版.pdf`。数据属于人工改造题，尚未运行模型、尚未经人工金标确认。

```bash
python reproductions/finder150/replay.py
```

该命令使用保存的150条原始FinDER记录和最终删除方案，重新执行每个删除位置，逐项比较最终审核数据和英语模型输入，并核对发布文件哈希。仅使用Python标准库，不调用API。

`build_finder.py`保留初始数量事实提取与恢复路径筛查实现。最终源题替换、人工判断式的语义修正及删除集合，以`construction_plan.json.gz`为准；重新执行启发式筛选不能替代冻结的审核结果。

如需重新排版PDF：先运行`replay.py --materialize`，再运行`render_pdf.py --build-only`。需安装ReportLab，并提供STHeiti字体；可通过`FINDER_PDF_FONT`指定兼容的TrueType字体路径。`--build-only`使用冻结中文译文，不重新调用翻译模型。在线重新取得源数据须固定`data/finder150/source.json`中的提交及校验值。
