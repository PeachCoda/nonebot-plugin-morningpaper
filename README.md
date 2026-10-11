# nonebot-plugin-morningpaper

NoneBot2 群聊早报插件，定时推送微博、百度、IT之家热点摘要。

这个插件的目标是轻量、少依赖、适合小 ECS：机器人只在固定时间抓取少量数据并发送一条早报，不做批量下载、不做重型爬虫。

## 功能

- 定时向指定 QQ 群发送早报
- 手动发送 `早报` 查看当前摘要
- 超级用户发送 `发送早报` 立即推送
- 数据源：
  - 微博热搜
  - 百度热点
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
MORNINGPAPER_SOURCES=["weibo","baidu","ithome"]
```

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

- 微博、百度、IT之家通常可以在国内 ECS 直连。
- 任一数据源暂时不可用时，插件会标出错误并继续发送其他来源。
- 不建议把推送频率设太高，早晚各一条以内比较合适。
