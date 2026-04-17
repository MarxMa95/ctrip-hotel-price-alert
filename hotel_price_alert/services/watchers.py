import json
from http import HTTPStatus
from typing import Any, Dict, Tuple

from ..config import APP_BUILD_VERSION, DEFAULT_CHROME_PROFILE, DEFAULT_POLL_INTERVAL_MINUTES, POLL_INTERVAL_SECONDS, PRICE_HISTORY_LIMIT, SOURCE_TIPS
from ..notifications import send_notification
from ..repository import Watcher, create_watcher, find_watcher, list_history, list_watchers, update_watcher
from ..services.checker import check_watcher
from ..utils import utc_now, watcher_next_run_display


def list_watcher_items() -> Dict[str, Any]:
    items = []
    for watcher in list_watchers():
        item = watcher.__dict__.copy()
        item['source_label'] = 'Ctrip'
        item['tip'] = SOURCE_TIPS.get('ctrip', '')
        item['room_type_tags'] = watcher.meta_tags()
        item['history'] = list_history(watcher.id, PRICE_HISTORY_LIMIT)
        item['next_check_at'] = watcher_next_run_display(watcher)
        item['all_time_low_price'] = watcher.all_time_low_price
        item['all_time_low_at'] = watcher.all_time_low_at
        items.append(item)
    return {
        'items': items,
        'poll_interval_seconds': POLL_INTERVAL_SECONDS,
        'build_version': APP_BUILD_VERSION,
    }


def source_presets_payload() -> Dict[str, Any]:
    return {'items': [{'key': 'ctrip', 'label': 'Ctrip', 'tip': SOURCE_TIPS.get('ctrip', ''), 'patterns': []}]}


def normalize_watcher_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    request_headers = str(normalized.get('request_headers', '')).strip()
    if request_headers:
        json.loads(request_headers)
    threshold = normalized.get('threshold_price')
    normalized['threshold_price'] = None if threshold in ('', None) else float(threshold)
    min_expected = normalized.get('min_expected_price')
    normalized['min_expected_price'] = None if min_expected in ('', None) else float(min_expected)
    interval_minutes = normalized.get('poll_interval_minutes')
    normalized['poll_interval_minutes'] = max(1, int(interval_minutes or DEFAULT_POLL_INTERVAL_MINUTES))
    normalized['notify_type'] = (normalized.get('notify_type') or 'feishu').strip() or 'feishu'
    normalized['use_browser'] = True
    normalized['use_app_session_profile'] = True
    normalized['use_local_chrome_profile'] = False
    normalized['chrome_profile_name'] = DEFAULT_CHROME_PROFILE
    normalized['room_type_meta'] = str(normalized.get('room_type_meta', '')).strip()
    return normalized


def validate_required_fields(payload: Dict[str, Any], required: list[str]) -> list[str]:
    return [field for field in required if field != 'id' and not str(payload.get(field, '')).strip()]


def create_watcher_from_payload(payload: Dict[str, Any]) -> int:
    return create_watcher(normalize_watcher_payload(payload))


def update_watcher_from_payload(payload: Dict[str, Any]) -> None:
    update_watcher(int(payload['id']), normalize_watcher_payload(payload))


def run_check_now(watcher_id: int) -> Tuple[Dict[str, Any], int]:
    watcher = find_watcher(int(watcher_id))
    if not watcher:
        return {'error': 'Watcher not found'}, HTTPStatus.NOT_FOUND
    result = check_watcher(watcher)
    status = HTTPStatus.OK if result.get('ok') else HTTPStatus.BAD_REQUEST
    return result, status


def build_test_notification_watcher(webhook: str, notify_type: str = 'feishu') -> Watcher:
    return Watcher(
        id=0,
        name='Test Alert',
        hotel_name='Test Hotel',
        source_type='ctrip',
        target_url='https://example.com',
        room_type_keyword='Deluxe King Room',
        room_type_meta='Breakfast included | Free cancellation',
        price_pattern='',
        currency='CNY',
        notify_type=notify_type or 'feishu',
        notify_target=webhook,
        threshold_price=999.0,
        min_expected_price=None,
        poll_interval_minutes=DEFAULT_POLL_INTERVAL_MINUTES,
        request_headers='{}',
        use_local_chrome_profile=0,
        chrome_profile_name=DEFAULT_CHROME_PROFILE,
        use_app_session_profile=0,
        use_browser=1,
        last_error=None,
        is_active=1,
        last_price=None,
        last_checked_at=None,
        last_notified_price=None,
        last_price_note=None,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def send_test_notification(webhook: str, notify_type: str = 'feishu') -> None:
    send_notification(build_test_notification_watcher(webhook, notify_type=notify_type), 888.0, is_test=True)
