# nonebot-plugin-morningpaper

NoneBot2 群聊早报插件，定时推送知乎、B站、IT之家热点摘要。

这个插件的目标是轻量、少依赖、适合小 ECS：机器人只在固定时间抓取少量数据并发送一条早报，不做批量下载、不做重型爬虫。

## 功能

- 定时向指定 QQ 群发送早报
- 手动发送 `早报` 查看当前摘要
- 超级用户发送 `发送早报` 立即推送
- 数据源：
  - 知乎热榜
  - B站热搜
  - IT之家 RSS
- 单个数据源失败时不会影响其他数据源

## 安装

```bash
pip install git+https://github.com/PeachCoda/nonebot-plugin-morningpaper.git
```

在 `pyproject.toml` 中启用：

```toml
[tool.nonebot]
plugins = [
    "nonebot_plugin_morningpaper",
]
```

插件依赖 `nonebot_plugin_apscheduler` 提供定时任务。

## 配置

在 `.env.*` 中配置：

```env
MORNINGPAPER_GROUPS=[142979214]
MORNINGPAPER_HOUR=8
MORNINGPAPER_MINUTE=30
MORNINGPAPER_TOP_N=5
MORNINGPAPER_SOURCES=["zhihu","bilibili","ithome"]
```

可选配置：

```env
MORNINGPAPER_ZHIHU_API_URL=
```

知乎官方接口可能因机房网络、风控或认证限制不可用。如果你有可用的国内聚合接口，可以填入 `MORNINGPAPER_ZHIHU_API_URL` 作为优先数据源。接口返回结构支持常见的 `data` / `list` / `items` 列表格式，条目字段支持 `title` / `name` / `keyword` / `query`。

建议同时设置 apscheduler 时区：

```env
APSCHEDULER_CONFIG='{"apscheduler.timezone":"Asia/Shanghai"}'
```

## 命令

```text
早报
发送早报
```

`发送早报` 需要 `SUPERUSER` 权限。`早报` 不需要命令前缀，因为插件使用正则匹配。

## 注意

- B站和 IT之家通常可以在国内 ECS 直连。
- 知乎热榜经常对机房网络返回 401/403，插件会显示“知乎暂不可用”并继续发送其他来源。
- 不建议把推送频率设太高，早晚各一条以内比较合适。
