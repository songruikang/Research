# 待办事项

## 支线任务

### Few-shot 11 条返回 0 行
- **状态**: 待排查
- **描述**: `few_shot_pairs.json` 中 FS11/13/16/20/26/27/30/32/34/37/38 共 11 条 SQL dry-run 返回 0 行
- **疑似原因**: mock 数据的 `collect_time` 时间戳不在 `NOW() - INTERVAL '24 hours/7 days'` 范围内。数据生成脚本刷新过时间戳但可能未覆盖所有 KPI 表
- **排查路径**: 检查 scripts/ 下时间戳刷新脚本覆盖了哪些表，对比 0 行 SQL 涉及的表
- **优先级**: 低，不影响 few-shot 作为示例的质量
