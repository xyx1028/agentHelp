"""只读工具定义及统一的工具执行边界。"""

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Iterable

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool


@tool
def travel_guide(city: str) -> str:
    """读取一个城市的示例旅行资料。仅查询，不会修改任何数据。"""
    guides = {
        "杭州": "证据：西湖适合步行；灵隐寺适合半日游；河坊街有本地小吃。",
        "北京": "证据：故宫需提前预约；颐和园适合白天游览；地铁是主要出行方式。",
        "上海": "证据：外滩适合傍晚；豫园附近有传统小吃；地铁覆盖主要景点。",
    }
    if city == "超时城市":
        time.sleep(0.8)  # 仅用于离线 timeout 场景，验证超时分支。
    if city == "错误城市":
        raise ValueError("示例资料库没有该城市")
    return guides.get(city, f"证据：示例资料库暂未收录“{city}”。")


READ_ONLY_TOOLS: tuple[BaseTool, ...] = (travel_guide,)


class ReadOnlyToolExecutor:
    """负责工具白名单、超时和错误 observation，Agent 本身不关心具体工具细节。"""

    def __init__(self, tools: Iterable[BaseTool], timeout_seconds: float):
        self._tools_by_name = {item.name: item for item in tools}
        self._timeout_seconds = timeout_seconds

    def execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[ToolMessage]:
        observations = []
        for call in tool_calls:
            tool_name = call["name"]
            tool_to_call = self._tools_by_name.get(tool_name)
            if tool_to_call is None:
                content = f"工具错误：不允许调用 {tool_name}；当前只允许已注册的只读工具。"
            else:
                print(f"[Tool] 执行只读工具 {tool_name}，参数：{call['args']}")
                content = self._call_safely(tool_to_call, call["args"])
            print(f"[Tool] observation：{content}")
            observations.append(ToolMessage(content=content, tool_call_id=call["id"], name=tool_name))
        return observations

    def _call_safely(self, tool_to_call: BaseTool, arguments: dict[str, Any]) -> str:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(tool_to_call.invoke, arguments)
        try:
            return str(future.result(timeout=self._timeout_seconds))
        except TimeoutError:
            future.cancel()
            return f"工具超时：{tool_to_call.name} 超过 {self._timeout_seconds} 秒，已停止等待。请说明暂时无法查询。"
        except Exception as error:  # 工具错误转为模型可见的 observation，不让整张图崩溃。
            return f"工具错误：{tool_to_call.name} 返回 {type(error).__name__}：{error}。请说明查询失败，不要编造结果。"
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
