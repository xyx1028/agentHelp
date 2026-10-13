"""天气预报的 LangChain 工具适配层。

把无状态的 OpenMeteoWeatherClient 包装为 LangChain 工具；网络调用耗时
不可控，注册时须标记专用执行超时（覆盖执行器默认的 0.3s 兜底）。
"""

from langchain_core.tools import tool

from ..weather import OpenMeteoWeatherClient
from .registry import ToolRegistration


def create_weather_tool(
    weather_client: OpenMeteoWeatherClient,
    *,
    timeout_seconds: float,
) -> ToolRegistration:
    """创建天气工具，并为网络请求标记专用执行超时。"""

    @tool
    def get_weather_forecast(city: str, forecast_days: int = 1) -> str:
        """查询指定城市未来 1 到 7 天的天气、温度区间和最大降水概率。用户询问天气、气温、降雨或天气相关出行建议时使用。"""
        return weather_client.get_forecast(city, forecast_days=forecast_days)

    return ToolRegistration(tool=get_weather_forecast, timeout_seconds=timeout_seconds)
