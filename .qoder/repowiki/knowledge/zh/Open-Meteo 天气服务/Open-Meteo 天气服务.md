---
kind: external_dependency
name: Open-Meteo 天气服务
slug: open-meteo
category: external_dependency
category_hints:
    - client_constraint
scope:
    - '**'
---

### 角色
提供免费的地理编码与天气预报接口，被 weather 模块用于查询未来 1–7 天的天气、温度和降水概率。

### 稳定约束
- 无需 API Key，直接 HTTP 调用其 Geocoding API 与 Forecast API。
- 客户端实现需遵循 open-meteo.com 官方文档约定的端点与参数格式。