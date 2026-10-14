"""工具子系统的运行参数：执行超时与内置网络客户端的请求预算。

与 MemorySettings / RagSettings 同一惯例：子系统 Settings 定义在自己的包里，
由应用层 AgentSettings 组合引用。所有超时单位均为秒；「工具执行总预算」与
「单次 HTTP 请求预算」是两层概念，关系见各字段行内注释。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSettings:
    """工具执行层与内置网络客户端的超时预算（秒）。"""

    default_timeout_seconds: float = 0.3  # 所有工具的默认执行超时，在执行器层生效
    network_timeout_seconds: float = 15.0  # 网络类工具（如天气）专用的执行超时；天气一次调用含地理编码+预报两步串行请求，须留足 2×weather_request_timeout_seconds 的余量，否则网络稍抖即整轮超时
    weather_request_timeout_seconds: float = 6.0  # 天气 HTTP 客户端的请求级超时，与工具执行超时是两层概念
