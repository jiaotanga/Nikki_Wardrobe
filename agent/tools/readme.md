# Tools

`agent/tools` 保存 Wardrobe Agent 使用的查询、推荐和编辑工具。

## 查询数据格式

工具使用 `WardrobeQuery` 表示查询条件：

```python
WardrobeQuery(
    main_style=None,
    quality=None,
    primary_color=None,
    item_name=None,
    semantic_query=None,
    keywords=(),
)
```

指定某类部件的独立条件时使用 `ItemRequest`：

```python
ItemRequest(
    item_type="tops",
    query=WardrobeQuery(primary_color="红色"),
)
```

`item_type` 可以在 `item_name` 已指定时为 `None`，工具会通过确切名称找到部件及其真实类别。

## 工具功能

### `WardrobeQueryParserTool`

将用户自然语言解析并校验为 `WardrobeQuery`。

### `OutfitRecommendationTool`

- `query_items(query, item_type=None)`：使用 SQLite 硬筛选、关键词匹配和文本向量检索获得候选部件。
- `recommend_item(query, item_type=None)`：从候选中推荐一个部件；未指定类别时必须提供 `item_name`。
- `run(query, item_requests=())`：先调用 `recommend_item` 完成各项指定要求，再补齐其他类别并组成整套搭配。
- `load_outfit(outfit_id)`：从数据库读取已有套装。

Planner 会将用户对不同部件提出的独立要求解析为 `item_requests`，Agent 再传给 `run`。

### `ItemSearchTool`

复用 `OutfitRecommendationTool.query_items`，返回指定类别或名称的搜索结果。

### `OutfitItemReplacementTool`

复用 `OutfitRecommendationTool.recommend_item`，替换当前搭配中的指定类别部件。

### `SemanticSearch`

加载本地 Qwen 文本向量模型和离线向量文件，在 SQLite 硬筛选后的候选中返回语义最相近的部件编号。

### `ToolRegistry`

按工具名称保存并调用 Agent 可执行函数。

## 调用关系

```text
WardrobeAgent
├─ WardrobeQueryParserTool
├─ ItemSearchTool
│  └─ OutfitRecommendationTool.query_items
├─ OutfitItemReplacementTool
│  └─ OutfitRecommendationTool.recommend_item
│     └─ OutfitRecommendationTool.query_items
└─ OutfitRecommendationTool.run
   ├─ OutfitRecommendationTool.recommend_item
   │  └─ OutfitRecommendationTool.query_items
   └─ OutfitRecommendationTool.query_items
      └─ SemanticSearch（存在 semantic_query 时）
```
