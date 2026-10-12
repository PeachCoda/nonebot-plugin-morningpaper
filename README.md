# nonebot-plugin-morningpaper

NoneBot2 群聊早报插件，定时推送百度热榜和 AI 前沿摘要。

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
MORNINGPAPER_TOP_N=10
MORNINGPAPER_SOURCES='["baidu","ai"]'
MORNINGPAPER_TRANSLATE_AI=true
APSCHEDULER_CONFIG='{"apscheduler.timezone":"Asia/Shanghai"}'
```

`MORNINGPAPER_SOURCES` 可选：`baidu`、`ai`、`ithome`、`infoq`。
`baidu` 推送百度实时热榜并跳过置顶项，`ai` 聚合 OpenAI、Google AI、Hacker News AI 与 InfoQ 中文 RSS，并会尽量把英文标题翻译成中文。

## 安装

```bash
pip install git+https://github.com/PeachCoda/nonebot-plugin-morningpaper.git
```

在 `pyproject.toml` 的 `plugins` 中加入：

```toml
"nonebot_plugin_morningpaper"
```
