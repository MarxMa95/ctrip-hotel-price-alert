import random
import threading
import time
from typing import Any, Dict, Optional

from ..config import DEFAULT_POLL_INTERVAL_MINUTES, POLL_JITTER_SECONDS
from ..extractors import extract_price_for_watcher
from ..fetchers import browser_fetch, browser_fetch_with_app_session, browser_fetch_with_local_profile, fetch_text
from ..notifications import notification_decision, send_notification
from ..repository import Watcher, append_notification_event, list_watchers, update_check_result
from ..utils import utc_now
from ..utils import parse_utc_timestamp, source_default_headers


def summarize_runtime_error(error: Exception) -> str:
    message = str(error or '').strip()
    if 'Invalid header value' in message:
        return 'Invalid header content detected. This usually means the Cookie value contains a newline or special character. Paste the full Cookie again.'
    if message.startswith('Room keyword not found:'):
        return 'Room keyword not found (Suggestions: 1. confirm whether this room type is sold out or no longer listed; 2. if it is still available, paste the full room name from the page and try again.)'
    return message or 'Check failed'


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
        decision = notification_decision(watcher, current_price)
        notify_reason = decision.reason
        notify = bool(decision.notify and notify_reason)
        if not notify and decision.blocked_by == 'quiet_hours':
            setattr(watcher, '_runtime_price_note', 'A notification condition was met, but the watcher is currently inside quiet hours')
        elif not notify and decision.blocked_by == 'daily_notification_limit':
            setattr(watcher, '_runtime_price_note', 'A notification condition was met, but the daily notification limit has already been reached')
        elif not notify and decision.blocked_by == 'notify_only_target_hit':
            setattr(watcher, '_runtime_price_note', 'The price dropped, but this watcher only sends alerts when the target price is reached')
        elif not notify and decision.blocked_by == 'min_price_drop_amount' and decision.price_drop_amount is not None:
            setattr(watcher, '_runtime_price_note', f'The price dropped by {decision.price_drop_amount:.2f}, but it did not reach the minimum drop threshold for alerts')
        if notify:
            send_notification(watcher, current_price, reason=notify_reason)
            append_notification_event(watcher.id, current_price, notify_reason, utc_now())
        update_check_result(watcher.id, current_price, notify, None, getattr(watcher, '_runtime_price_note', None))
        return {'ok': True, 'price': current_price, 'notified': notify, 'price_note': getattr(watcher, '_runtime_price_note', None)}
    except Exception as exc:
        summarized_error = summarize_runtime_error(exc)
        update_check_result(watcher.id, watcher.last_price, False, summarized_error, getattr(watcher, '_runtime_price_note', None))
        payload = {'ok': False, 'error': summarized_error}
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
