import random
import threading
import time
from typing import Any, Dict, Optional

from ..config import DEFAULT_POLL_INTERVAL_MINUTES, POLL_JITTER_SECONDS
from ..extractors import extract_price_for_watcher
from ..fetchers import browser_fetch, browser_fetch_with_app_session, browser_fetch_with_local_profile, fetch_text
from ..notifications import notification_reason, send_notification, should_notify
from ..repository import Watcher, list_watchers, update_check_result
from ..utils import parse_utc_timestamp, source_default_headers


def check_watcher(watcher: Watcher) -> Dict[str, Any]:
    try:
        headers = watcher.parsed_headers() or source_default_headers(watcher.source_type)
        if watcher.use_browser and watcher.use_app_session_profile:
            text = browser_fetch_with_app_session(watcher.target_url, headers, watcher.source_type, watcher.room_type_keyword)
        elif watcher.use_browser and watcher.use_local_chrome_profile:
            text = browser_fetch_with_local_profile(watcher.target_url, headers, watcher.source_type, watcher.chrome_profile_name, watcher.room_type_keyword)
        else:
            text = browser_fetch(watcher.target_url, headers, watcher.source_type, watcher.room_type_keyword) if watcher.use_browser else fetch_text(watcher.target_url, headers)
        setattr(watcher, '_runtime_price_note', None)
        current_price = extract_price_for_watcher(text, watcher)
        notify_reason = notification_reason(watcher, current_price)
        notify = bool(notify_reason)
        if notify:
            send_notification(watcher, current_price, reason=notify_reason)
        update_check_result(watcher.id, current_price, notify, None, getattr(watcher, '_runtime_price_note', None))
        return {'ok': True, 'price': current_price, 'notified': notify, 'price_note': getattr(watcher, '_runtime_price_note', None)}
    except Exception as exc:
        update_check_result(watcher.id, watcher.last_price, False, str(exc), getattr(watcher, '_runtime_price_note', None))
        payload = {'ok': False, 'error': str(exc)}
        if 'Invalid header value' in str(exc):
            payload['error'] = 'The request headers contain invalid content. This usually means the Cookie value includes line breaks or special characters. Please paste the full Cookie string again.'
        debug_payload = getattr(exc, 'debug_payload', None)
        if debug_payload:
            payload['debug'] = debug_payload
        return payload


class Poller(threading.Thread):
    daemon = True

    def __init__(self) -> None:
        super().__init__()
        self._stop_event = threading.Event()
        self._next_run_at: Dict[int, float] = {}

    def stop(self) -> None:
        self._stop_event.set()

    def _schedule_next(self, watcher: Watcher, base_time: Optional[float] = None) -> None:
        base = time.time() if base_time is None else base_time
        interval_seconds = max(60, int(watcher.poll_interval_minutes or DEFAULT_POLL_INTERVAL_MINUTES) * 60)
        jitter = random.randint(-POLL_JITTER_SECONDS, POLL_JITTER_SECONDS)
        self._next_run_at[watcher.id] = base + interval_seconds + jitter

    def _initial_due_at(self, watcher: Watcher) -> float:
        interval_seconds = max(60, int(watcher.poll_interval_minutes or DEFAULT_POLL_INTERVAL_MINUTES) * 60)
        last_checked = parse_utc_timestamp(watcher.last_checked_at)
        now_ts = time.time()
        if not last_checked:
            return now_ts + random.randint(0, POLL_JITTER_SECONDS)
        last_ts = last_checked.timestamp()
        due = last_ts + interval_seconds + random.randint(-POLL_JITTER_SECONDS, POLL_JITTER_SECONDS)
        return due if due > now_ts else now_ts + random.randint(0, POLL_JITTER_SECONDS)

    def run(self) -> None:
        while not self._stop_event.is_set():
            watchers = list_watchers()
            active_ids = {watcher.id for watcher in watchers if watcher.is_active}
            for watcher_id in list(self._next_run_at):
                if watcher_id not in active_ids:
                    self._next_run_at.pop(watcher_id, None)
            now_ts = time.time()
            for watcher in watchers:
                if not watcher.is_active:
                    continue
                due_at = self._next_run_at.get(watcher.id)
                if due_at is None:
                    due_at = self._initial_due_at(watcher)
                    self._next_run_at[watcher.id] = due_at
                if now_ts >= due_at:
                    check_watcher(watcher)
                    self._schedule_next(watcher, time.time())
            self._stop_event.wait(1)
