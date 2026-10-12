from __future__ import annotations

import asyncio
import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from nonebot import get_bot, get_driver, on_regex, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

try:
    scheduler = require("nonebot_plugin_apscheduler").scheduler
except Exception:
    scheduler = None


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-morningpaper",
    description="群聊早报，定时推送联合早报和 AI 前沿 RSS 摘要。",
    usage="早报：立即查看早报\n发送早报：超级用户立即推送到当前群或配置群",
    type="application",
    homepage="https://github.com/PeachCoda/nonebot-plugin-morningpaper",
    supported_adapters={"~onebot.v11"},
)


@dataclass
class HotItem:
    title: str
    url: str | None = None
    extra: str | None = None


@dataclass
class SourceResult:
    name: str
    items: list[HotItem]
    error: str | None = None


def _config_dict() -> dict[str, Any]:
    config = get_driver().config
    if hasattr(config, "model_dump"):
        return config.model_dump()
    return config.dict()


def _get_config(name: str, default: Any) -> Any:
    config = _config_dict()
    return config.get(name.lower(), config.get(name.upper(), default))


def _as_int(name: str, default: int) -> int:
    value = _get_config(name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_list(name: str, default: list[Any]) -> list[Any]:
    value = _get_config(name, default)
    if isinstance(value, list):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [part.strip() for part in value.split(",") if part.strip()]
        return parsed if isinstance(parsed, list) else default
    return default


def _clean_title(value: str | None) -> str:
    title = value or ""
    for _ in range(5):
        decoded = html.unescape(title)
        if decoded == title:
            break
        title = decoded
    return title.strip()


GROUPS = [int(group_id) for group_id in _as_list("morningpaper_groups", [])]
HOUR = _as_int("morningpaper_hour", 8)
MINUTE = _as_int("morningpaper_minute", 30)
TOP_N = max(1, min(_as_int("morningpaper_top_n", 5), 10))
SOURCES = [
    str(source).lower()
    for source in _as_list("morningpaper_sources", ["zaobao", "ai"])
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

AI_KEYWORDS = (
    "AI",
    "AIGC",
    "Agent",
    "Agents",
    "LLM",
    "OpenAI",
    "Claude",
    "Anthropic",
    "DeepSeek",
    "大模型",
    "模型",
    "智能体",
    "人工智能",
    "机器学习",
    "深度学习",
    "强化学习",
    "生成式",
    "多模态",
    "推理",
    "训练",
    "RAG",
    "向量",
    "GPU",
    "英伟达",
)

RSS_SOURCES: dict[str, dict[str, Any]] = {
    "zaobao": {
        "name": "联合早报",
        "urls": ["https://hub.slarker.me/zaobao/realtime/china"],
    },
    "ai": {
        "name": "AI前沿",
        "urls": [
            "https://www.infoq.cn/feed",
            "https://openai.com/blog/rss.xml",
            "https://blog.google/technology/ai/rss/",
            "https://hnrss.org/newest?q=AI",
        ],
        "keywords": AI_KEYWORDS,
    },
    "ithome": {
        "name": "IT之家",
        "urls": ["https://www.ithome.com/rss/"],
    },
    "infoq": {
        "name": "AI前沿",
        "urls": ["https://www.infoq.cn/feed"],
        "keywords": AI_KEYWORDS,
    },
}


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(element: ET.Element, *names: str) -> str:
    for child in element:
        if _strip_namespace(child.tag) in names and child.text:
            return _clean_title(child.text)
    return ""


def _child_link(element: ET.Element) -> str | None:
    for child in element:
        if _strip_namespace(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text:
            return child.text.strip()
    return None


def _feed_entries(root: ET.Element) -> list[ET.Element]:
    rss_items = root.findall("./channel/item")
    if rss_items:
        return rss_items
    return [element for element in root.iter() if _strip_namespace(element.tag) == "entry"]


def _parse_feed(text: str, keywords: tuple[str, ...] | None = None) -> list[HotItem]:
    root = ET.fromstring(text)
    items: list[HotItem] = []
    seen: set[str] = set()
    for entry in _feed_entries(root):
        title = _child_text(entry, "title")
        if not title or title in seen:
            continue
        description = _child_text(entry, "description", "summary", "content")
        description = _clean_title(re.sub(r"<[^>]+>", "", description))
        if keywords:
            text_for_filter = f"{title}\n{description}".lower()
            if not any(keyword.lower() in text_for_filter for keyword in keywords):
                continue
        seen.add(title)
        items.append(HotItem(title=title, url=_child_link(entry)))
    return items


async def fetch_rss_source(client: httpx.AsyncClient, source: str, limit: int) -> SourceResult:
    config = RSS_SOURCES[source]
    urls = [str(url) for url in config["urls"]]
    keywords = config.get("keywords")
    per_feed_limit = limit if len(urls) == 1 else 2
    parsed_by_feed: list[list[HotItem]] = []
    errors: list[str] = []
    for url in urls:
        try:
            response = await client.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
            response.raise_for_status()
            parsed_by_feed.append(_parse_feed(response.text, keywords))
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")

    items: list[HotItem] = []
    seen: set[str] = set()
    for parsed in parsed_by_feed:
        for item in parsed[:per_feed_limit]:
            if item.title in seen:
                continue
            seen.add(item.title)
            items.append(item)
            if len(items) >= limit:
                return SourceResult(str(config["name"]), items)
    for parsed in parsed_by_feed:
        for item in parsed[per_feed_limit:]:
            if item.title in seen:
                continue
            seen.add(item.title)
            items.append(item)
            if len(items) >= limit:
                return SourceResult(str(config["name"]), items)

    if items:
        return SourceResult(str(config["name"]), items)
    return SourceResult(str(config["name"]), [], "; ".join(errors) or "RSS 无可用条目")


async def collect_sources() -> list[SourceResult]:
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_rss_source(client, source, TOP_N)
            for source in SOURCES
            if source in RSS_SOURCES
        ]
        if not tasks:
            return []
        return await asyncio.gather(*tasks)


def format_digest(results: list[SourceResult]) -> Message:
    now = datetime.now().strftime("%m-%d %H:%M")
    lines = [f"早报 {now}", ""]
    for result in results:
        lines.append(f"{result.name}:")
        if result.items:
            for index, item in enumerate(result.items, 1):
                line = f"{index}. {item.title}"
                if item.extra:
                    line += f" ({item.extra})"
                lines.append(line)
        else:
            lines.append(f"暂不可用：{result.error or '未知错误'}")
        lines.append("")
    return Message("\n".join(lines).strip())


async def build_digest() -> Message:
    return format_digest(await collect_sources())


async def send_to_configured_groups(bot: Bot | None = None) -> None:
    if not GROUPS:
        logger.warning("MORNINGPAPER_GROUPS 未配置，跳过早报推送")
        return
    bot = bot or get_bot()
    message = await build_digest()
    for group_id in GROUPS:
        try:
            await bot.send_group_msg(group_id=group_id, message=message)
        except Exception as exc:
            logger.warning(f"发送早报到群 {group_id} 失败：{type(exc).__name__}: {exc}")
        await asyncio.sleep(1.5)


morningpaper_matcher = on_regex(r"^早报$", priority=20)
push_matcher = on_regex(r"^发送早报$", priority=20, permission=SUPERUSER)


@morningpaper_matcher.handle()
async def _() -> None:
    await morningpaper_matcher.finish(await build_digest())


@push_matcher.handle()
async def _(bot: Bot, event: MessageEvent) -> None:
    if isinstance(event, GroupMessageEvent):
        await bot.send_group_msg(group_id=event.group_id, message=await build_digest())
    else:
        await send_to_configured_groups(bot)
    await push_matcher.finish("早报已发送")


if scheduler:
    scheduler.add_job(send_to_configured_groups, "cron", hour=HOUR, minute=MINUTE, id="morningpaper")
    logger.info(f"MorningPaper 已设定于 {HOUR:02d}:{MINUTE:02d} 推送，群：{GROUPS or '未配置'}")
else:
    logger.warning("未检测到 nonebot_plugin_apscheduler，MorningPaper 定时推送禁用")
