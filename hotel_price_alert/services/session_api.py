import json
from http import HTTPStatus
from typing import Any, Dict, Tuple

from ..fetchers import browser_capture_with_app_session
from ..session import (
    app_session_profile_status,
    finish_login_and_save_session,
    launch_login_and_save_session,
    session_default_target_url,
    startup_all_session_checks,
    startup_session_check,
    verify_app_session,
)
from ..utils import merge_cookie_into_headers, normalize_headers


def session_status_payload(source_type: str) -> Dict[str, Any]:
    return app_session_profile_status(source_type)


def startup_session_check_payload(source_type: str) -> Tuple[Dict[str, Any], int]:
    result = startup_session_check(source_type) if source_type else startup_all_session_checks()
    status = HTTPStatus.OK if result.get('ok') else HTTPStatus.BAD_REQUEST
    return result, status


def start_session_login(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_type = str(payload.get('source_type', 'ctrip')).strip() or 'ctrip'
    target_url = str(payload.get('target_url', '')).strip() or session_default_target_url(source_type)
    return launch_login_and_save_session(source_type, target_url)


def finish_session_login(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_type = str(payload.get('source_type', 'ctrip')).strip() or 'ctrip'
    return finish_login_and_save_session(source_type)


def verify_session_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    source_type = str(payload.get('source_type', 'ctrip')).strip() or 'ctrip'
    target_url = str(payload.get('target_url', '')).strip()
    if not target_url:
        return {'error': '请先填写酒店链接'}, HTTPStatus.BAD_REQUEST
    request_headers = str(payload.get('request_headers', '')).strip()
    headers = normalize_headers(request_headers or '{}', 'ctrip')
    headers = merge_cookie_into_headers(headers, str(payload.get('cookie', '')))
    result = verify_app_session(target_url, headers, source_type)
    status = HTTPStatus.OK if result.get('ok') else HTTPStatus.BAD_REQUEST
    return result, status


def debug_session_screenshot_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_type = str(payload.get('source_type', 'ctrip')).strip() or 'ctrip'
    target_url = str(payload.get('target_url', '')).strip()
    if not target_url:
        raise ValueError('请先填写酒店链接')
    request_headers = str(payload.get('request_headers', '')).strip()
    headers = normalize_headers(request_headers or '{}', 'ctrip')
    headers = merge_cookie_into_headers(headers, str(payload.get('cookie', '')))
    room_keyword = str(payload.get('room_type_keyword', '')).strip()
    focus_room = bool(payload.get('focus_room'))
    result = browser_capture_with_app_session(target_url, headers, source_type, room_keyword, focus_room=focus_room)
    return {'ok': True, **result}
