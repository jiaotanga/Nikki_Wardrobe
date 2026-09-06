# 数据集构建流程

`data_pipeline` 保存从本地数据集快照构建运行时数据库的代码。目前只处理部件 JSON 和对应图片，不包含视觉描述、文本向量或图片向量生成。

## 输入和输出

```text
data/raw/items/{item_id}.json
data/raw/images/{item_id}.png
                ↓
python -m data_pipeline.build_database
                ↓
data/database/dressup.db
```

构建过程会检查 JSON 文件名、内部部件 ID 和图片文件名是否一一对应，并在临时数据库完整构建和外键检查成功后替换正式数据库。

## 使用

在项目根目录运行：

```powershell
python -m data_pipeline.build_database
```

也可以显式指定路径：

```powershell
python -m data_pipeline.build_database `
  --source data/raw/items `
  --images data/raw/images `
  --output data/database/dressup.db
```
