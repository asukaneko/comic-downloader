# 信号分析器 (SignalAnalyzer)

SignalAnalyzer 分析用户输入中的情绪信号，为 ReactionPlanner 和 StateMachine 提供输入。

## 概述

第一版使用关键词规则，后续可替换为 LLM 分析。

```python
class SignalAnalyzer:
    def analyze(
        self,
        user_message: str,
        state: Optional[CharacterState] = None,
        relationship: Optional[RelationshipState] = None,
    ) -> UserSignals
```

## UserSignals 数据结构

```python
@dataclass
class UserSignals:
    praise_score: float = 0.0      # 夸奖信号
    rejection_score: float = 0.0   # 拒绝信号
    affection_score: float = 0.0   # 亲密信号
    hostility_score: float = 0.0   # 敌意信号
    care_score: float = 0.0        # 关心信号
    intimacy_score: float = 0.0    # 亲密信号
    question_score: float = 0.0    # 提问信号
    command_score: float = 0.0     # 命令信号

    detected_keywords: List[str] = []  # 检测到的关键词
```

## 关键词规则表

```python
_KEYWORD_RULES = {
    "praise": {
        "keywords": ["可爱", "好棒", "厉害", "优秀", "真好", "最棒", "最喜欢", "爱你", "厉害了", "好厉害", "真棒", "棒"],
        "score": 0.6,
    },
    "rejection": {
        "keywords": ["别烦", "讨厌", "走开", "滚", "不要你", "离我远点", "别管我", "别理我", "闭嘴", "烦死了"],
        "score": 0.7,
    },
    "affection": {
        "keywords": ["摸摸", "抱抱", "亲亲", "喜欢你", "想你", "爱你", "贴贴", "蹭蹭", "牵手", "在一起"],
        "score": 0.7,
    },
    "hostility": {
        "keywords": ["恨你", "去死", "废物", "垃圾", "蠢", "笨蛋", "丑", "恶心"],
        "score": 0.8,
    },
    "care": {
        "keywords": ["你还好吗", "辛苦了", "累不累", "注意休息", "别太累", "关心", "担心你", "照顾好自己"],
        "score": 0.5,
    },
    "intimacy": {
        "keywords": ["晚安", "早安", "想你了", "陪我", "一起", "永远", "一直", "不会离开"],
        "score": 0.5,
    },
}
```

## 分析流程

```
analyze
├── 关键词匹配
│   └── 多个关键词叠加，上限 1.0
├── 问号检测
│   └── question_score = 0.5
├── 命令式检测
│   └── command_score = 0.4
└── 关系状态修正
    ├── 安全感 < 30
    │   ├── rejection_score *= 1.3
    │   └── hostility_score *= 1.2
    └── 上限 1.0
```

## 关键词匹配

```python
def _contains_any(text: str, keywords: List[str]) -> List[str]:
    """检查文本中是否包含关键词，返回匹配到的关键词列表"""
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]
```

## 信号强度计算

```python
# 关键词匹配
matched = _contains_any(user_message, rule["keywords"])
if matched:
    score = rule["score"]
    # 多个关键词叠加，但上限为 1.0
    adjusted = min(score + len(matched) * 0.1, 1.0)
    signals.detected_keywords.extend(matched)
```

## 关系状态修正

```python
# 安全感低时，更容易感到不安
if relationship and relationship.security < 30:
    if signals.rejection_score > 0:
        signals.rejection_score = min(signals.rejection_score * 1.3, 1.0)
    if signals.hostility_score > 0:
        signals.hostility_score = min(signals.hostility_score * 1.2, 1.0)
```

## 使用示例

```python
from nbot.character.policies import SignalAnalyzer

analyzer = SignalAnalyzer()

# 分析用户消息
signals = analyzer.analyze(
    "你真可爱",
    state=state,
    relationship=relationship
)

print(signals.praise_score)      # 0.7
print(signals.detected_keywords)  # ["可爱"]

# 分析负面消息
signals = analyzer.analyze("别烦我")
print(signals.rejection_score)   # 0.7
print(signals.detected_keywords)  # ["别烦"]
```

## 调试输出

```python
{
  "praise_score": 0.7,
  "rejection_score": 0.0,
  "affection_score": 0.0,
  "hostility_score": 0.0,
  "care_score": 0.0,
  "intimacy_score": 0.0,
  "question_score": 0.0,
  "command_score": 0.0,
  "detected_keywords": ["可爱"]
}
```

## 扩展规则

可以通过继承 SignalAnalyzer 来扩展规则：

```python
class CustomSignalAnalyzer(SignalAnalyzer):
    def analyze(self, user_message, state=None, relationship=None):
        signals = super().analyze(user_message, state, relationship)

        # 自定义规则
        if "自定义关键词" in user_message:
            signals.custom_score = 0.5

        return signals
```

## 后续改进

- [ ] LLM 驱动的信号分析
- [ ] 上下文感知（结合历史消息）
- [ ] 情感强度分级
- [ ] 多语言支持
