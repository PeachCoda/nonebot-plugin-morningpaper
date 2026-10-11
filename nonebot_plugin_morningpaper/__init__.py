from __future__ import annotations

import asyncio
import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

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
    description="群聊早报，定时推送百度、贴吧、IT之家热点摘要。",
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
    for source in _as_list("morningpaper_sources", ["baidu", "tieba", "ithome"])
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


async def _get_json(client: httpx.AsyncClient, url: str, **kwargs: Any) -> Any:
    response = await client.get(url, timeout=10, follow_redirects=True, **kwargs)
    response.raise_for_status()
    return response.json()


async def fetch_baidu(client: httpx.AsyncClient, limit: int) -> SourceResult:
    try:
        payload = await _get_json(
            client,
            "https://top.baidu.com/api/board?platform=wise&tab=realtime",
            headers={**HEADERS, "Referer": "https://top.baidu.com/board?tab=realtime"},
        )
        content = payload.get("data", {}).get("cards", [{}])[0].get("content", [])
        raw_items = content[0].get("content", []) if content else []
        items: list[HotItem] = []
        for raw in raw_items:
            title = _clean_title(str(raw.get("word") or raw.get("query") or ""))
            if not title:
                continue
            url = html.unescape(str(raw.get("url") or "").strip()) or f"https://www.baidu.com/s?wd={quote(title)}"
            extra = str(raw.get("hotScore") or raw.get("score") or "").strip() or None
            items.append(HotItem(title=title, url=url, extra=extra))
            if len(items) >= limit:
                break
        return SourceResult("百度", items)
    except Exception as exc:
        return SourceResult("百度", [], f"{type(exc).__name__}: {exc}")


async def fetch_tieba(client: httpx.AsyncClient, limit: int) -> SourceResult:
    try:
        response = await client.get(
            "http://tieba.baidu.com/hottopic/browse/topicList?res_type=1",
            headers={**HEADERS, "Referer": "http://tieba.baidu.com/"},
            timeout=8,
            follow_redirects=True,
        )
        response.raise_for_status()
        items: list[HotItem] = []
        for raw_title in re.findall(
            r'<a[^>]+class="[^"]*topic[^"]*"[^>]*>(.*?)</a>',
            response.text,
            flags=re.S,
        ):
            title = _clean_title(re.sub(r"<[^>]+>", "", raw_title))
            if title:
                items.append(HotItem(title=title))
            if len(items) >= limit:
                break
        return SourceResult("贴吧", items)
    except Exception as exc:
        return SourceResult("贴吧", [], f"{type(exc).__name__}: {exc}")


async def fetch_ithome(client: httpx.AsyncClient, limit: int) -> SourceResult:
    try:
        response = await client.get("https://www.ithome.com/rss/", headers=HEADERS, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        items: list[HotItem] = []
        for item in root.findall("./channel/item")[:limit]:
            title = _clean_title(item.findtext("title"))
            url = (item.findtext("link") or "").strip() or None
            if title:
                items.append(HotItem(title=title, url=url))
        return SourceResult("IT之家", items)
    except Exception as exc:
        return SourceResult("IT之家", [], f"{type(exc).__name__}: {exc}")


async def collect_sources() -> list[SourceResult]:
    fetchers = {
        "baidu": fetch_baidu,
        "tieba": fetch_tieba,
        "ithome": fetch_ithome,
    }
    async with httpx.AsyncClient() as client:
        tasks = [
            fetchers[source](client, TOP_N)
            for source in SOURCES
            if source in fetchers
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
