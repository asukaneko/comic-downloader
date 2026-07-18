"""ReAct Agent — 基于 AgentHarness 的 Reasoning + Acting 实现。

历史版本通过 prompt + 文本解析（思考:/行动:/输入:/观察结果:）驱动工具循环，
依赖模型按格式输出。现版本改用 function-calling，复用 AgentHarness 的状态管理、
错误处理、可观测性能力。ThoughtStep / ReActResult 数据结构保留为公开 API。

若模型不支持 function-calling，AgentHarness 会自然降级为单轮直接回答，
等价于"模型认为当前信息已足够，无需工具"。
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from nbot.plugins.skills.base import SkillContext, SkillRegistry
from nbot.plugins.manager import get_plugin_manager
from nbot.core.agent_service import (
    AgentHarness,
    ToolLoopHooks,
    ToolLoopModelError,
)

_log = logging.getLogger(__name__)


@dataclass
class ThoughtStep:
    """思考步骤（保留为公开 API，兼容老调用方）。"""
    step: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[str] = None
    observation: Optional[str] = None
    is_final: bool = False


@dataclass
class ReActResult:
    """思考链结果（保留为公开 API）。"""
    success: bool
    final_answer: str
    thought_steps: List[ThoughtStep] = field(default_factory=list)
    error: Optional[str] = None
    iterations: int = 0
    usage: Dict[str, int] = field(default_factory=dict)


def _skill_to_tool_schema(skill) -> Optional[Dict[str, Any]]:
    """把 SkillRegistry 中的 skill 转为 OpenAI function-calling tool schema。"""
    params = getattr(skill, "parameters", None) or {}
    # 若 skill 未声明 parameters，给一个宽松的单参数 schema
    if not params:
        params = {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "传递给技能的输入文本",
                }
            },
            "required": [],
        }
    return {
        "type": "function",
        "function": {
            "name": skill.name,
            "description": skill.description or f"Skill: {skill.name}",
            "parameters": params,
        },
    }


class ReActAgent:
    """ReAct (Reasoning + Acting) Agent — 基于 AgentHarness 实现。

    通过 AgentHarness + function-calling 驱动「思考 → 工具调用 → 观察」循环，
    直到模型给出最终答案或达到最大迭代次数。
    """

    def __init__(self, max_iterations: int = 5, timeout: int = 60):
        # max_iterations 与 AgentHarness 的 max_iterations 语义一致
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.plugin_manager = get_plugin_manager()

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------
    async def think(self, question: str, context: SkillContext, ai_client) -> ReActResult:
        """执行思考链。

        Args:
            question: 用户问题
            context: 技能执行上下文
            ai_client: AI 客户端（需支持 chat_completion 接口）

        Returns:
            ReActResult: 思考结果，包含 thought_steps / final_answer / usage 等
        """
        # 构建 tools schema（从 SkillRegistry.get_enabled() 动态生成）
        enabled_skills = SkillRegistry.get_enabled()
        tools_schema = []
        for skill_name, skill in enabled_skills.items():
            schema = _skill_to_tool_schema(skill)
            if schema:
                tools_schema.append(schema)

        # 若没有可用工具，直接走单轮对话
        if not tools_schema:
            _log.warning("[ReAct] 没有可用工具，降级为单轮直接回答")
            return await self._think_no_tools(question, context, ai_client)

        # 思考链历史（与 AgentHarness.trace 并行维护，用于公开 API）
        thought_steps: List[ThoughtStep] = []

        # ------------------------------------------------------------------
        # model_call 回调：把 ai_client 适配为 AgentHarness 期望的格式
        # ------------------------------------------------------------------
        def _model_call(msgs, stop_event=None):
            # 把 system prompt 注入 skills 描述
            messages = list(msgs)
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] += "\n\n" + self._skills_prompt()
            else:
                messages.insert(0, {"role": "system", "content": self._skills_prompt()})

            response = ai_client.chat_completion(
                messages=messages,
                stream=False,
                tools=tools_schema,
                tool_choice="auto",
            )

            # 提取字段（兼容 OpenAI SDK 对象和 dict 两种形式）
            choice = getattr(response, "choices", [None])[0]
            if choice is None and isinstance(response, dict):
                choice = response.get("choices", [{}])[0]
            message = (
                getattr(choice, "message", None)
                if choice is not None and not isinstance(choice, dict)
                else (choice or {}).get("message", {})
            )

            content = (
                getattr(message, "content", None)
                if not isinstance(message, dict)
                else message.get("content", "")
            ) or ""
            thinking = (
                getattr(message, "reasoning_content", None)
                or getattr(message, "thinking", None)
                if not isinstance(message, dict)
                else message.get("reasoning_content") or message.get("thinking") or ""
            ) or ""

            # 转换 tool_calls
            raw_tool_calls = (
                getattr(message, "tool_calls", None)
                if not isinstance(message, dict)
                else message.get("tool_calls")
            ) or []
            normalized_tool_calls = []
            for tc in raw_tool_calls:
                fn = getattr(tc, "function", None) or (
                    tc.get("function", {}) if isinstance(tc, dict) else {}
                )
                fn_name = (
                    getattr(fn, "name", None)
                    or (fn.get("name") if isinstance(fn, dict) else "")
                    or ""
                )
                raw_args = (
                    getattr(fn, "arguments", None)
                    or (fn.get("arguments") if isinstance(fn, dict) else None)
                )
                if isinstance(raw_args, str):
                    try:
                        import json
                        arguments = json.loads(raw_args)
                    except Exception:
                        arguments = {"_raw": raw_args}
                elif isinstance(raw_args, dict):
                    arguments = raw_args
                else:
                    arguments = {}
                tc_id = (
                    getattr(tc, "id", None)
                    or (tc.get("id") if isinstance(tc, dict) else "")
                    or ""
                )
                normalized_tool_calls.append(
                    {"id": tc_id, "name": fn_name, "arguments": arguments}
                )

            # usage
            usage_obj = getattr(response, "usage", None)
            usage_dict: Dict[str, int] = {}
            if usage_obj is not None:
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    v = getattr(usage_obj, k, None)
                    if v is None and isinstance(usage_obj, dict):
                        v = usage_obj.get(k, 0)
                    usage_dict[k] = int(v or 0)

            finish_reason = (
                getattr(choice, "finish_reason", None)
                if choice is not None and not isinstance(choice, dict)
                else (choice or {}).get("finish_reason", "")
            ) or ""

            return {
                "content": content,
                "thinking_content": thinking,
                "tool_calls": normalized_tool_calls,
                "finish_reason": finish_reason,
                "usage": usage_dict,
                "_model_id": getattr(ai_client, "model", "") or "",
                "_model_name": getattr(ai_client, "model", "") or "",
            }

        # ------------------------------------------------------------------
        # tool_executor 回调：调 plugin_manager.execute_skill
        # ------------------------------------------------------------------
        def _tool_executor(tool_call, thinking_content, iteration, msgs):
            skill_name = tool_call.get("name", "")
            arguments = tool_call.get("arguments", {}) or {}
            action_input = arguments.get("message") or arguments.get("input") or ""
            if isinstance(action_input, dict):
                action_input = str(action_input)

            _log.info(
                f"[ReAct] Step {iteration + 1}: action={skill_name}, input={action_input[:100]}"
            )

            # 把 thinking_content 作为 thought（如果模型有推理内容）
            if thinking_content:
                thought_steps.append(
                    ThoughtStep(
                        step=iteration + 1,
                        thought=thinking_content,
                        action=skill_name,
                        action_input=action_input,
                    )
                )

            try:
                # 在 asyncio 事件循环中同步调用异步方法
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 我们已经在 async 上下文中，但 AgentHarness 的 tool_executor 是同步回调。
                    # 用 asyncio.run_coroutine_threadsafe 或直接创建 task 等待
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.plugin_manager.execute_skill(
                                skill_name, context, message=action_input
                            ),
                        )
                        result = future.result(timeout=self.timeout)
                else:
                    result = asyncio.run(
                        self.plugin_manager.execute_skill(
                            skill_name, context, message=action_input
                        )
                    )
            except Exception as e:
                _log.error(f"[ReAct] Action execution error: {e}")
                return {"success": False, "error": str(e)}

            observation = result.content if result.success else f"技能执行失败: {result.error}"

            # 更新最后一个 thought_step 的 observation
            if thought_steps and thought_steps[-1].action == skill_name:
                thought_steps[-1].observation = observation
            else:
                thought_steps.append(
                    ThoughtStep(
                        step=iteration + 1,
                        thought="",
                        action=skill_name,
                        action_input=action_input,
                        observation=observation,
                    )
                )

            return {
                "success": result.success,
                "content": result.content,
                "data": result.data,
                "error": result.error,
            }

        # ------------------------------------------------------------------
        # hooks：记录 token 用量（保持原 ReAct 的 token 统计行为）
        # ------------------------------------------------------------------
        from nbot.core.token_stats import get_token_stats_manager, PURPOSE_REACT

        stats_mgr = get_token_stats_manager()
        total_usage: Dict[str, int] = {}

        def _on_iteration_start(iteration, msgs):
            _log.info(f"[ReAct] Iteration {iteration + 1}/{self.max_iterations}")

        def _on_tool_start(tool_call, thinking_content, iteration, msgs):
            # token 统计：每次调用工具前记录上一轮 usage
            # 实际 usage 累计由 AgentHarness 内部完成
            pass

        def _on_tool_result(tool_call, tool_result, thinking_content, iteration, msgs):
            # 返回 None 让 AgentHarness 用默认 tool message 格式
            return None

        cli_hooks = ToolLoopHooks(
            on_iteration_start=_on_iteration_start,
            on_tool_start=_on_tool_start,
            on_tool_result=_on_tool_result,
        )

        # ------------------------------------------------------------------
        # 构造并运行 AgentHarness
        # ------------------------------------------------------------------
        harness = AgentHarness(
            initial_messages=[{"role": "user", "content": question}],
            model_call=_model_call,
            tool_executor=_tool_executor,
            max_iterations=self.max_iterations,
            max_consecutive_errors=3,
            hooks=cli_hooks,
        )

        try:
            loop_result = harness.run()
        except ToolLoopModelError as e:
            return ReActResult(
                success=False,
                final_answer=f"模型调用失败（迭代 {e.iteration}）: {e.original}",
                thought_steps=thought_steps,
                error=str(e.original),
                iterations=e.iteration,
            )

        # 累计 token 用量并记录到 stats
        total_usage = loop_result.usage or {}
        if any(total_usage.values()):
            try:
                stats_mgr.record_usage(
                    prompt_tokens=total_usage.get("prompt_tokens", 0),
                    completion_tokens=total_usage.get("completion_tokens", 0),
                    total_tokens=total_usage.get("total_tokens", 0),
                    model=loop_result.model_id or "",
                    channel_type="react",
                    source="react",
                    purpose=PURPOSE_REACT,
                )
            except Exception as stats_err:
                _log.debug(f"[ReAct] 记录 token 用量失败: {stats_err}")

        # 补充最后一个 ThoughtStep（最终答案的"思考"）
        final_step = ThoughtStep(
            step=loop_result.iterations,
            thought=loop_result.final_content,
            is_final=True,
        )
        thought_steps.append(final_step)

        return ReActResult(
            success=True,
            final_answer=loop_result.final_content,
            thought_steps=thought_steps,
            iterations=loop_result.iterations,
            usage=total_usage,
        )

    # ------------------------------------------------------------------
    # 工具不可用时的降级路径
    # ------------------------------------------------------------------
    async def _think_no_tools(
        self, question: str, context: SkillContext, ai_client
    ) -> ReActResult:
        """没有可用工具时，直接让模型回答。"""
        try:
            response = ai_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一个善于思考的AI助手。"},
                    {"role": "user", "content": question},
                ],
                stream=False,
            )
            content = ai_client.clean_response(
                getattr(response.choices[0].message, "content", "")
            )
            return ReActResult(
                success=True,
                final_answer=content,
                thought_steps=[
                    ThoughtStep(step=1, thought=content, is_final=True)
                ],
                iterations=1,
            )
        except Exception as e:
            return ReActResult(
                success=False,
                final_answer=f"调用AI出错: {e}",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _skills_prompt(self) -> str:
        """生成注入 system prompt 的工具描述。"""
        skills = SkillRegistry.get_enabled()
        if not skills:
            return ""
        lines = ["\n\n## 可用工具"]
        for name, skill in skills.items():
            desc = skill.description or ""
            lines.append(f"- {name}: {desc}")
        lines.append("\n当需要使用工具时，通过 function-calling 调用对应工具。")
        return "\n".join(lines)


react_agent: Optional[ReActAgent] = None


def get_react_agent() -> ReActAgent:
    """获取 ReAct Agent 单例"""
    global react_agent
    if react_agent is None:
        react_agent = ReActAgent()
    return react_agent
