# MemoryFile 数据模型

MemoryFS 中的逻辑记忆文件，代表一个可由角色读取的记忆单元。

## 字段

```python
from nbot.memory.models import MemoryFile

mf = MemoryFile(
    path="characters/neko_girl/users/user_123.md",
    character_id="neko_girl",
    target_id="user_123",
    title="用户关系摘要",
    content="用户喜欢动漫，性格内向...",
    summary="与用户的互动记录",
    tags=["relationship", "user"],
    importance=0.8,
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 逻辑路径（唯一标识） |
| `character_id` | `str` | 关联角色 ID |
| `target_id` | `str` | 目标用户/会话 ID |
| `title` | `str` | 文件标题 |
| `content` | `str` | 文件内容 |
| `summary` | `str` | 内容摘要（prompt 注入时优先使用） |
| `tags` | `list[str]` | 标签列表 |
| `importance` | `float` | 重要性权重（0-1） |
| `version` | `int` | 版本号（自动递增） |
| `source_event_id` | `str` | 来源事件 ID |
| `memory_ids` | `list[str]` | 关联的记忆 ID 列表 |
| `updated_at` | `str` | 最后更新时间 |

## to_prompt_text()

格式化为 prompt 注入文本。优先使用 summary，截断 at 500 字符。

```python
text = mf.to_prompt_text()
# 返回: "【用户关系摘要】\n与用户的互动记录"
```
