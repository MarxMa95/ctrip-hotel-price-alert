import json
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from .config import DEFAULT_POLL_INTERVAL_MINUTES


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def utc_now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = str(value).replace(' UTC', '')
        return datetime.strptime(normalized, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    except Exception:
        return None


def parse_hhmm(value: Optional[str]) -> Optional[time]:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        hour_text, minute_text = raw.split(':', 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return time(hour=hour, minute=minute)
    except Exception:
        return None


def is_now_in_quiet_hours(start_value: Optional[str], end_value: Optional[str], now: Optional[datetime] = None) -> bool:
    start = parse_hhmm(start_value)
    end = parse_hhmm(end_value)
    if not start or not end:
        return False
    current = (now or utc_now_datetime()).astimezone(ZoneInfo('Asia/Shanghai')).time()
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


def utc8_day_range(now: Optional[datetime] = None) -> tuple[str, str]:
    current = (now or utc_now_datetime()).astimezone(ZoneInfo('Asia/Shanghai'))
    start_local = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        end_local.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
    )


def watcher_next_run_display(watcher: Any) -> Optional[str]:
    interval_seconds = max(60, int(getattr(watcher, 'poll_interval_minutes', 0) or DEFAULT_POLL_INTERVAL_MINUTES) * 60)
    last_checked = parse_utc_timestamp(getattr(watcher, 'last_checked_at', None))
    if last_checked is None:
        return None
    next_dt = last_checked.timestamp() + interval_seconds
    return datetime.fromtimestamp(next_dt, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def source_default_headers(source_type: str) -> Dict[str, str]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 HotelPriceAlert/1.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
    }
    if source_type == 'ctrip':
        headers['Referer'] = 'https://hotels.ctrip.com/'
    return headers


def normalize_headers(raw_headers: Any, source_type: str) -> Dict[str, str]:
    headers = source_default_headers(source_type)
    if isinstance(raw_headers, str) and raw_headers.strip():
        parsed = json.loads(raw_headers)
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                headers[str(key)] = str(value)
    elif isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            headers[str(key)] = str(value)
    return headers


def merge_cookie_into_headers(headers: Dict[str, str], cookie_text: str) -> Dict[str, str]:
    cookie = re.sub(r'\s+', ' ', cookie_text).strip()
    if not cookie:
        return headers
    merged = dict(headers)
    merged['Cookie'] = cookie
    return merged


def normalize_target_url(url: str, source_type: str, preferred_currency: str = 'CNY') -> str:
    return str(url or '').strip()
