"""通过 Open-Meteo 查询天气预报的只读客户端。

Open-Meteo 是免费 API（无需 API key），但预报接口只认经纬度不认城市名，
因此查询分两步：先经地理编码 API 把城市名转成坐标，再调预报 API 取逐日数据。
返回数据全链路 Fail Fast 校验，所有异常统一收敛为 WeatherServiceError，
上层（工具适配层与执行器）只需捕获这一种异常。客户端无状态，可脱离 Agent 单独使用。
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# 第一步：地理编码接口，把城市名解析为经纬度（count=1 只取最匹配结果）。
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
# 第二步：预报接口，按坐标返回逐日天气码、气温和降水概率。
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# WMO 天气码 → 中文描述映射表，未收录的代码会原样展示编号。
_WEATHER_DESCRIPTIONS = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}


class WeatherServiceError(RuntimeError):
    """天气服务无法返回可靠预报时抛出。"""


class OpenMeteoWeatherClient:
    """用城市名定位并读取未来天气预报，不保存任何查询数据。"""

    def __init__(self, request_timeout_seconds: float = 3.0):
        if request_timeout_seconds <= 0:
            raise ValueError("weather_request_timeout_seconds 必须大于 0。")
        self._request_timeout_seconds = request_timeout_seconds

    def get_forecast(self, city: str, *, forecast_days: int = 1) -> str:
        """返回指定城市未来 1 到 7 天的天气、温度区间和降水概率。"""
        city = city.strip()
        if not city:
            raise ValueError("城市不能为空。")
        if not 1 <= forecast_days <= 7:
            raise ValueError("forecast_days 必须在 1 到 7 之间。")

        # 两步查询：城市名 → 经纬度 → 逐日预报，最后格式化为中文文本供模型阅读。
        location = self._geocode(city)
        forecast = self._fetch_forecast(location, forecast_days)
        return _format_forecast(city, location, forecast)

    def _geocode(self, city: str) -> dict[str, Any]:
        """把城市名解析为最匹配地点的经纬度；找不到或缺坐标即抛 WeatherServiceError。"""
        payload = self._request_json(
            _GEOCODING_URL,
            {"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        locations = payload.get("results")
        if not isinstance(locations, list) or not locations:
            raise WeatherServiceError(f"未找到城市“{city}”，请提供更具体的城市名称。")
        location = locations[0]
        if not isinstance(location, dict) or "latitude" not in location or "longitude" not in location:
            raise WeatherServiceError(f"天气服务未返回城市“{city}”的有效坐标。")
        return location

    def _fetch_forecast(self, location: dict[str, Any], forecast_days: int) -> dict[str, Any]:
        """按坐标拉取逐日预报，并要求响应必须包含 daily 字段。"""
        payload = self._request_json(
            _FORECAST_URL,
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": forecast_days,
            },
        )
        daily = payload.get("daily")
        if not isinstance(daily, dict):
            raise WeatherServiceError("天气服务未返回逐日预报数据。")
        return payload

    def _request_json(self, base_url: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """发起一次 GET 请求并把响应解析为 JSON 对象；网络与解析错误统一转为 WeatherServiceError。"""
        request = Request(
            f"{base_url}?{urlencode(parameters)}",
            headers={"Accept": "application/json", "User-Agent": "agent_platform/1.0"},
        )
        try:
            with urlopen(request, timeout=self._request_timeout_seconds) as response:
                raw_payload = response.read()
        except (HTTPError, URLError, OSError, TimeoutError) as error:
            raise WeatherServiceError(f"天气服务请求失败：{error}") from error

        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WeatherServiceError("天气服务返回了无法解析的数据。") from error
        if not isinstance(payload, dict):
            raise WeatherServiceError("天气服务返回了非对象格式的数据。")
        if payload.get("error"):
            raise WeatherServiceError(str(payload.get("reason", "天气服务返回错误。")))
        return payload


def _format_forecast(city: str, location: dict[str, Any], forecast: dict[str, Any]) -> str:
    """把逐日数组翻译为中文逐行预报文本，作为工具 observation 供模型引用。"""
    daily = forecast["daily"]
    dates = _daily_values(daily, "time")
    codes = _daily_values(daily, "weather_code")
    highs = _daily_values(daily, "temperature_2m_max")
    lows = _daily_values(daily, "temperature_2m_min")
    precipitation_probabilities = _daily_values(daily, "precipitation_probability_max")
    # 五个逐日字段必须等长，否则说明上游数据不完整，Fail Fast。
    lengths = {len(dates), len(codes), len(highs), len(lows), len(precipitation_probabilities)}
    if len(lengths) != 1:
        raise WeatherServiceError("天气服务返回的逐日字段长度不一致。")

    location_name = str(location.get("name") or city)
    country = str(location.get("country") or "")
    location_label = "，".join(part for part in (location_name, country) if part)
    timezone = str(forecast.get("timezone") or location.get("timezone") or "当地时区")
    lines = [f"天气预报（来源：Open-Meteo；地点：{location_label}；时区：{timezone}）："]
    for date, code, high, low, precipitation_probability in zip(
        dates,
        codes,
        highs,
        lows,
        precipitation_probabilities,
    ):
        try:
            description = _WEATHER_DESCRIPTIONS.get(int(code), f"天气代码 {code}")
            temperature = f"{float(low):.1f}–{float(high):.1f}°C"
            precipitation = f"{round(float(precipitation_probability))}%"
        except (TypeError, ValueError) as error:
            raise WeatherServiceError("天气服务返回了无效的逐日数值。") from error
        lines.append(f"{date}：{description}，{temperature}，最大降水概率 {precipitation}。")
    return "\n".join(lines)


def _daily_values(daily: dict[str, Any], field_name: str) -> list[Any]:
    """从 daily 中取出非空列表字段；字段缺失或为空即抛 WeatherServiceError。"""
    values = daily.get(field_name)
    if not isinstance(values, list) or not values:
        raise WeatherServiceError(f"天气服务未返回 {field_name} 数据。")
    return values
