# nonebot-plugin-morningpaper

NoneBot2 群聊早报插件，定时推送知乎、百度、贴吧、IT之家、InfoQ 热点摘要。

## 功能

- 定时向指定 QQ 群发送早报
- 群内发送 `早报` 可手动查看
- 超级用户发送 `发送早报` 可立即推送
- 单个数据源失败时，不影响其他数据源发送

## 配置

```env
MORNINGPAPER_GROUPS=[142979214]
MORNINGPAPER_HOUR=8
MORNINGPAPER_MINUTE=30
MORNINGPAPER_TOP_N=5
MORNINGPAPER_SOURCES=["baidu","tieba","ithome"]
MORNINGPAPER_ZHIHU_ACCESS_SECRET=
APSCHEDULER_CONFIG='{"apscheduler.timezone":"Asia/Shanghai"}'
```

`MORNINGPAPER_SOURCES` 可选：`zhihu`、`baidu`、`tieba`、`ithome`、`infoq`。
启用 `zhihu` 需要配置知乎开放平台 Access Secret。

## 安装

```bash
pip install git+https://github.com/PeachCoda/nonebot-plugin-morningpaper.git
```

在 `pyproject.toml` 的 `plugins` 中加入：

```toml
"nonebot_plugin_morningpaper"
```
