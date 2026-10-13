"""统一执行工具调用，并将失败转换为模型可见的 observation。

设计要点：工具未注册、超时、抛异常都不向上抛出，而是变成文本 observation
交还给模型，由模型向用户说明「查询失败/资料不足」——保证 LangGraph 图
不会因单个工具的故障整体崩溃。
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from .registry import ToolRegistry


class ReadOnlyToolExecutor:
    """负责工具白名单、专用超时和错误 observation，Agent 不依赖具体工具实现。"""

    def __init__(self, registry: ToolRegistry, default_timeout_seconds: float):
        if default_timeout_seconds <= 0:
            raise ValueError("默认工具超时必须大于 0。")
        self._tools_by_name = {item.name: item for item in registry.tools}
        self._default_timeout_seconds = default_timeout_seconds
        self._timeouts_by_name = registry.timeouts_by_name

    def execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[ToolMessage]:
        """依次执行一轮工具调用，把每个结果（含失败说明）封装为 ToolMessage。"""
        observations = []
        for call in tool_calls:
            tool_name = call["name"]
            tool_to_call = self._tools_by_name.get(tool_name)
            if tool_to_call is None:
                # 白名单防线：模型幻觉出的未注册工具直接拒绝，绝不执行。
                content = f"工具错误：不允许调用 {tool_name}；当前只允许已注册的只读工具。"
            else:
                # 超时两级裁决：单工具显式配置优先，否则回落到执行器默认值。
                timeout_seconds = self._timeouts_by_name.get(tool_name, self._default_timeout_seconds)
                print(f"[Tool] 执行只读工具 {tool_name}，参数：{call['args']}")
                content = self._call_safely(tool_to_call, call["args"], timeout_seconds)
            print(f"[Tool] observation：{content}")
            observations.append(ToolMessage(content=content, tool_call_id=call["id"], name=tool_name))
        return observations

    @staticmethod
    def _call_safely(
        tool_to_call: BaseTool,
        arguments: dict[str, Any],
        timeout_seconds: float,
    ) -> str:
        """在单线程池中执行工具并限时等待；超时或异常都转为文本而非抛出。

        借助 ThreadPoolExecutor 是因为 LangChain 工具本身没有超时参数；
        超时的工作线程无法被强制杀死，只能取消等待、放弃其结果。
        """
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(tool_to_call.invoke, arguments)
        try:
            return str(future.result(timeout=timeout_seconds))
        except TimeoutError:
            future.cancel()
            return f"工具超时：{tool_to_call.name} 超过 {timeout_seconds} 秒，已停止等待。请说明暂时无法查询。"
        except Exception as error:  # 工具错误转为模型可见的 observation，不让整张图崩溃。
            return f"工具错误：{tool_to_call.name} 返回 {type(error).__name__}：{error}。请说明查询失败，不要编造结果。"
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
