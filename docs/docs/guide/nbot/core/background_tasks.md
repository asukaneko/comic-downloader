# background_tasks - 后台任务调度

## 概述

`background_tasks.py` 提供 NekoBot 内部非关键操作的统一后台任务调度，基于 `concurrent.futures.ThreadPoolExecutor` 实现。

**设计目的：** 避免自动记忆抽取、剧情选项生成等"重活"阻塞主回复链路，让首条回复尽快触达用户。

**核心特性：**
- **线程池调度** - 基于 `ThreadPoolExecutor` 的轻量线程池，并发度由环境变量 `NBOT_BACKGROUND_TASK_WORKERS` 控制
- **串行锁** - `serial_key` 让同一来源的任务按序执行，避免读写竞态
- **去重保护** - `unique_key` 丢弃同 key 的进行中任务（典型场景：会话改名）
- **失败容错** - 任务异常不会冒泡到主调用方，仅记录到日志

## 核心 API

### submit_background_task(name, func, *args, serial_key="", unique_key="", **kwargs)

提交一个 best-effort 后台任务。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 任务名称，用于日志 |
| `func` | `Callable` | 实际执行函数 |
| `*args` | - | 透传给 `func` 的位置参数 |
| `serial_key` | `str` | 同 key 的任务串行执行（获取进程内锁后调用） |
| `unique_key` | `str` | 同 key 的进行中任务被丢弃（不会排队） |
| `**kwargs` | - | 透传给 `func` 的关键字参数 |

**返回：** `Optional[Future]`，当 `unique_key` 命中进行中任务时返回 `None`。

```python
from nbot.core.background_tasks import submit_background_task

submit_background_task(
    "auto_memory",
    extract_and_save_turn_memories,
    ctx, callbacks, result,
    serial_key="auto_memory",
)

submit_background_task(
    "plot_choice_generation",
    run_plot_generation,
    serial_key=f"plot:{conversation_id}",
)
```

## 工作机制

### 串行锁 (`serial_key`)

当多个任务共享同一个 `serial_key` 时，会按提交顺序串行执行；不同 `serial_key` 之间互不影响。

```python
# 同一会话的剧情选项生成始终串行，避免节点竞态
submit_background_task(
    "plot_choice_generation",
    run_plot_generation,
    serial_key=f"plot:{conversation_id}",
)
```

### 去重保护 (`unique_key`)

`unique_key` 用于丢弃同 key 的进行中任务。典型场景：用户连续触发"重命名会话"时，第二次提交应被丢弃。

```python
# 第二次同名 session 的重命名任务会直接返回 None
submit_background_task(
    "session_rename",
    rename_session,
    session_id="s_123",
    new_name="新名字",
    unique_key=f"rename:s_123",
)
```

### 异常处理

后台任务异常不会冒泡，失败信息会通过 `_log.warning` 记录：

```
[BackgroundTask] auto_memory failed: <exception>
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NBOT_BACKGROUND_TASK_WORKERS` | `4` | 线程池大小，非法值回落为 4 |

## 当前使用方

| 任务 | 调用方 | 关键参数 |
|------|--------|----------|
| `auto_memory` | `AIPipeline._phase_post_turn` | `serial_key="auto_memory"` |
| `plot_choice_generation` | `AIPipeline._run_plot_choice_generation` | `serial_key=f"plot:{conversation_id}"` |

## 目录结构

```
nbot/core/
└── background_tasks.py    # 线程池 + 串行锁 + 去重 + 失败回调
```

## 进程退出

模块在 `atexit` 注册 `_shutdown_executor()`，进程退出时 `wait=False` + `cancel_futures=False` 优雅关闭线程池。
