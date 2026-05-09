# 数据仓库 (Repository)

通过 repository 接口访问存储层，业务逻辑不直接读写 JSON。后续切换到 SQLite 只需更换 repository 实现。

## 概述

```python
# 当前实现
ProfileRepository -> JsonStore
CharacterStateRepository -> JsonStore
RelationshipRepository -> JsonStore

# 未来可切换
ProfileRepository -> SQLiteStore
CharacterStateRepository -> SQLiteStore
RelationshipRepository -> SQLiteStore
```

## ProfileRepository - 角色卡仓库

```python
class ProfileRepository:
    def __init__(self, base_dir: str)
    def get(self, character_id: str) -> Optional[CharacterProfile]
    def save(self, profile: CharacterProfile) -> None
    def delete(self, character_id: str) -> bool
    def list_all(self) -> List[CharacterProfile]
    def get_or_create_by_personality(self, personality_data: Dict) -> CharacterProfile
```

### 使用示例

```python
from nbot.character.repository import ProfileRepository

profile_repo = ProfileRepository(base_dir)

# 获取角色卡
profile = profile_repo.get("neko_girl")

# 保存角色卡
profile_repo.save(profile)

# 列出所有角色卡
profiles = profile_repo.list_all()

# 从旧 personality 数据获取或创建
profile = profile_repo.get_or_create_by_personality({
    "name": "本子娘",
    "personality": "温柔、黏人",
})
```

## CharacterStateRepository - 角色状态仓库

```python
class CharacterStateRepository:
    def __init__(self, base_dir: str)
    def get(self, character_id: str, scope_id: str) -> Optional[CharacterState]
    def get_or_create(
        self,
        character_id: str,
        scope_id: str,
        initial_state: Optional[Dict] = None,
    ) -> CharacterState
    def save(self, state: CharacterState) -> None
    def delete(self, character_id: str, scope_id: str) -> bool
    def list_by_character(self, character_id: str) -> List[CharacterState]
```

### 使用示例

```python
from nbot.character.repository import CharacterStateRepository

state_repo = CharacterStateRepository(base_dir)

# 获取状态
state = state_repo.get("neko_girl", "web:session_123")

# 获取或创建状态
state = state_repo.get_or_create(
    character_id="neko_girl",
    scope_id="web:session_123",
    initial_state={"mood": "开心", "energy": 80}
)

# 保存状态
state_repo.save(state)

# 列出角色的所有状态
states = state_repo.list_by_character("neko_girl")
```

## RelationshipRepository - 关系仓库

```python
class RelationshipRepository:
    def __init__(self, base_dir: str)
    def get(self, character_id: str, target_id: str) -> Optional[RelationshipState]
    def get_or_create(self, character_id: str, target_id: str) -> RelationshipState
    def save(self, relationship: RelationshipState) -> None
    def delete(self, character_id: str, target_id: str) -> bool
    def list_by_character(self, character_id: str) -> List[RelationshipState]
```

### 使用示例

```python
from nbot.character.repository import RelationshipRepository

relationship_repo = RelationshipRepository(base_dir)

# 获取关系
relationship = relationship_repo.get("neko_girl", "user_123")

# 获取或创建关系
relationship = relationship_repo.get_or_create(
    character_id="neko_girl",
    target_id="user_123"
)

# 保存关系
relationship_repo.save(relationship)

# 列出角色的所有关系
relationships = relationship_repo.list_by_character("neko_girl")
```

## 存储位置

数据存储在 `data/character/` 目录：

```
data/character/
├── profiles.json        # 角色卡（ProfileRepository）
├── states.json          # 角色状态（CharacterStateRepository）
├── relationships.json   # 关系状态（RelationshipRepository）
├── memories.json        # 角色记忆
├── events.json          # 事件记录
└── debug_snapshots.json # 调试快照
```

## JSON 存储格式

### profiles.json

```json
{
  "neko_girl": {
    "id": "neko_girl",
    "name": "本子娘",
    "basic_info": "...",
    "personality": "...",
    "initial_state": {"mood": "开心"}
  }
}
```

### states.json

```json
{
  "neko_girl::web:session_123": {
    "character_id": "neko_girl",
    "scope_id": "web:session_123",
    "mood": "开心",
    "mood_intensity": 0.8,
    "energy": 75
  }
}
```

### relationships.json

```json
{
  "neko_girl::user_123": {
    "character_id": "neko_girl",
    "target_id": "user_123",
    "affection": 60,
    "trust": 55,
    "familiarity": 40,
    "dependency": 35,
    "security": 50,
    "jealousy": 0
  }
}
```

## 线程安全

JsonStore 内部使用线程锁保证线程安全：

```python
class JsonStore:
    def __init__(self, file_path: str):
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            data = self._load()
            return data.get(key)
```

## 缓存机制

JsonStore 内部有缓存机制，避免频繁文件 IO：

```python
def _load(self) -> Dict[str, Any]:
    if self._cache is not None:
        return self._cache
    # 从文件加载
    ...
    self._cache = data
    return self._cache
```

## 后续规划

- [ ] SQLiteRepository 实现
- [ ] RedisRepository 实现
- [ ] 缓存策略优化
- [ ] 数据迁移工具
