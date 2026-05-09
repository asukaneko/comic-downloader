# 数据模型

实时情感引擎定义了一套完整的数据模型，用于描述角色、状态、关系和记忆。

## CharacterProfile - 静态角色卡

描述角色的固定设定，与旧 personality.json 格式兼容。

```python
@dataclass
class CharacterProfile:
    id: str                 # 角色唯一标识
    name: str               # 角色名称
    version: int = 1        # 版本号

    description: str = ""   # 角色描述
    avatar: str = ""        # 头像
    portrait: str = ""      # 立绘
    tags: List[str] = []    # 标签

    basic_info: str = ""    # 基本信息
    personality: str = ""   # 性格特点
    scenario: str = ""      # 背景设定
    first_message: str = "" # 开场白
    example_dialogues: str = ""  # 示例对话
    response_format: str = ""    # 回复格式
    rules: List[str] = []   # 行为规则

    initial_state: Dict = {}     # 初始状态
    metadata: Dict = {}          # 元数据
    system_prompt: str = ""      # 旧字段兼容
```

### 从旧格式转换

```python
# 从旧 personality dict 转换
profile = CharacterProfile.from_personality_dict({
    "name": "本子娘",
    "basicInfo": "...",
    "personality": "...",
    "scenario": "...",
    "state": {"affection": 50, "mood": "开心"}
})

# 转回旧格式
personality_dict = profile.to_personality_dict()
```

## CharacterState - 角色运行时状态

每个 scope_id（会话/用户）独立的角色动态状态。

```python
@dataclass
class CharacterState:
    character_id: str       # 角色ID
    scope_id: str           # 作用域ID (如: web:session_id, qq_private:user_id)

    mood: str = "平静"      # 当前心情
    mood_intensity: float = 0.5  # 情绪强度 0.0-1.0
    energy: int = 70        # 精力 0-100

    scene: Dict = {}        # 场景信息
    last_active_at: str = ""     # 最后活跃时间
    updated_at: str = ""         # 更新时间
```

### scope_id 格式

```
web:{session_id}              # Web 会话
qq_private:{user_id}          # QQ 私聊
qq_group:{group_id}:{user_id} # QQ 群聊（每个用户独立）
```

## RelationshipState - 关系状态

角色与目标用户的六维关系模型。

```python
@dataclass
class RelationshipState:
    character_id: str       # 角色ID
    target_id: str          # 目标用户ID

    affection: int = 50     # 好感/亲密倾向 (0-100)
    trust: int = 50         # 信任度 (0-100)
    familiarity: int = 30   # 熟悉度 (0-100)
    dependency: int = 30    # 依赖度 (0-100)
    security: int = 50      # 安全感 (0-100)
    jealousy: int = 0       # 嫉妒 (0-100)

    updated_at: str = ""    # 更新时间
```

### 六维关系说明

| 维度 | 说明 | 影响 |
|------|------|------|
| affection | 好感/亲密倾向 | 角色对用户的亲近程度 |
| trust | 信任度 | 角色对用户的信任程度 |
| familiarity | 熟悉度 | 影响随便程度和玩笑强度 |
| dependency | 依赖度 | 影响黏人程度 |
| security | 安全感 | 低时更容易不安/试探 |
| jealousy | 嫉妒 | 占有欲相关 |

## CharacterMemory - 角色记忆

```python
@dataclass
class CharacterMemory:
    id: str                 # 记忆ID
    character_id: str       # 角色ID
    target_id: str          # 目标用户ID

    type: str = "long"      # 记忆类型
    title: str = ""         # 标题
    summary: str = ""       # 摘要
    content: str = ""       # 内容

    importance: int = 5     # 重要程度 1-10
    emotion_impact: Dict = {}    # 情绪影响
    source_turn_id: str = None   # 来源回合ID

    created_at: str = ""    # 创建时间
    expires_at: str = None  # 过期时间
```

### 记忆类型

```
preference   # 用户偏好
promise      # 承诺
event        # 事件
relationship # 关系节点
fact         # 稳定事实
short        # 短期记忆
long         # 长期记忆
```

## ReactionPlan - 反应计划

每轮对话前生成，控制角色的回复策略。

```python
@dataclass
class ReactionPlan:
    intent: str = "respond"          # 意图: respond/ask/initiate
    tone: str = "natural"            # 语气

    visible_emotion: str = "平静"    # 表面情绪
    hidden_emotion: str = ""         # 内心情绪

    should_reference_memory: bool = False  # 是否引用记忆
    memory_ids: List[str] = []       # 引用的记忆ID

    style_controls: Dict = {}        # 风格控制
    state_deltas: Dict = {}          # 状态变化量
    relationship_deltas: Dict = {}   # 关系变化量
```

### 语气类型

```
natural        # 自然
happy_clingy   # 开心黏人
hurt_but_soft  # 受伤但温柔
shy_happy      # 害羞开心
hurt_scared    # 受伤害怕
touched        # 感动
blissful       # 幸福
```

### 风格控制

```python
style_controls = {
    "length": "medium",        # short/medium/long
    "action_detail": "medium", # low/medium/high
    "initiative": "medium",    # low/medium/high
}
```

## CharacterIdentity - 角色身份标识

用于在 Pipeline 中传递角色上下文。

```python
@dataclass
class CharacterIdentity:
    character_id: str       # 角色ID
    target_id: str          # 目标用户ID
    scope_id: str           # 作用域ID
    channel: str            # 频道: web/qq/telegram
```

## CharacterTurnContext - 回合上下文

包含 before_turn 的全部产出。

```python
@dataclass
class CharacterTurnContext:
    profile: CharacterProfile           # 角色卡
    state: CharacterState               # 角色状态
    relationship: RelationshipState     # 关系状态
    memories: List[CharacterMemory]     # 相关记忆
    signals: Any                        # 信号分析结果
    plan: ReactionPlan                  # 反应计划
    prompt_text: str                    # 编译后的提示词
```

## 使用示例

### 创建角色卡

```python
from nbot.character.models import CharacterProfile

profile = CharacterProfile(
    id="neko_girl",
    name="本子娘",
    basic_info="一只可爱的猫娘",
    personality="温柔、黏人、有点害羞",
    scenario="在一个安静的咖啡馆里",
    rules=["用可爱的语气说话", "经常喵喵叫"],
    initial_state={"mood": "开心", "energy": 80}
)
```

### 创建角色状态

```python
from nbot.character.models import CharacterState

state = CharacterState(
    character_id="neko_girl",
    scope_id="web:session_123",
    mood="开心",
    mood_intensity=0.8,
    energy=75
)
```

### 创建关系状态

```python
from nbot.character.models import RelationshipState

relationship = RelationshipState(
    character_id="neko_girl",
    target_id="user_456",
    affection=60,
    trust=55,
    familiarity=40,
    dependency=35,
    security=50
)
```

### 序列化与反序列化

```python
# 转字典
state_dict = state.to_dict()
rel_dict = relationship.to_dict()

# 从字典恢复
state = CharacterState.from_dict(state_dict)
relationship = RelationshipState.from_dict(rel_dict)
```
