"""时间工具：库里存 UTC（naive datetime），“本周”按北京时间周一 0 点计算。"""

from datetime import datetime, timedelta, timezone

# 中国不实行夏令时，用固定偏移即可（Windows 上 zoneinfo 还需要额外装 tzdata）
CN_TZ = timezone(timedelta(hours=8))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def week_start_utc(now_utc: datetime) -> datetime:
    local = now_utc.replace(tzinfo=timezone.utc).astimezone(CN_TZ)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
