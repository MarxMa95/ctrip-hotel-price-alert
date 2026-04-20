import json
import ssl
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict

from .config import APP_BUILD_VERSION, FIXED_SOURCE_TYPE, INDEX_HTML, STATIC_DIR
from .fetchers import discover_chrome_profiles
from .repository import delete_watcher, set_watcher_active
from .services.session_api import (
    debug_session_screenshot_payload,
    finish_session_login,
    session_status_payload,
    start_session_login,
    startup_session_check_payload,
    verify_session_payload,
)
from .services.watchers import (
    create_watcher_from_payload,
    list_watcher_items,
    run_check_now,
    send_test_notification,
    source_presets_payload,
    update_watcher_from_payload,
    validate_required_fields,
)


class AppHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode('utf-8')
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = file_path.read_bytes()
        content_type = 'text/css; charset=utf-8' if file_path.suffix == '.css' else 'text/plain; charset=utf-8'
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/':
            self._send_html(INDEX_HTML)
            return
        if parsed.path == '/api/watchers':
            self._send_json(list_watcher_items())
            return
        if parsed.path == '/api/version':
            self._send_json({'build_version': APP_BUILD_VERSION})
            return
        if parsed.path == '/api/source-presets':
            self._send_json(source_presets_payload())
            return
        if parsed.path == '/api/chrome-profiles':
            self._send_json({'items': discover_chrome_profiles()})
            return
        if parsed.path == '/api/app-session-status':
            source_type = urllib.parse.parse_qs(parsed.query).get('source_type', [FIXED_SOURCE_TYPE])[0].strip() or FIXED_SOURCE_TYPE
            self._send_json(session_status_payload(source_type))
            return
        if parsed.path == '/api/startup-session-check':
            params = urllib.parse.parse_qs(parsed.query)
            source_type = params.get('source_type', [FIXED_SOURCE_TYPE])[0].strip()
            result, status = startup_session_check_payload(source_type)
            self._send_json(result, status)
            return
        if parsed.path.startswith('/static/'):
            self._send_static(STATIC_DIR / parsed.path.removeprefix('/static/'))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        payload = json.loads(raw.decode('utf-8'))

        if parsed.path == '/api/watchers':
            return self._handle_create_watcher(payload)
        if parsed.path == '/api/update-watcher':
            return self._handle_update_watcher(payload)
        if parsed.path == '/api/check-now':
            return self._handle_check_now(payload)
        if parsed.path in ('/api/test-notify', '/api/test-feishu'):
            return self._handle_test_notify(payload)
        if parsed.path == '/api/start-ctrip-login':
            self._send_json(start_session_login(payload))
            return
        if parsed.path == '/api/finish-ctrip-login':
            self._send_json(finish_session_login(payload))
            return
        if parsed.path == '/api/verify-app-session':
            return self._handle_verify_app_session(payload)
        if parsed.path == '/api/debug-app-session-screenshot':
            return self._handle_debug_app_session_screenshot(payload)
        if parsed.path == '/api/toggle':
            set_watcher_active(int(payload['id']), 1 if bool(payload.get('is_active')) else 0)
            self._send_json({'ok': True})
            return
        if parsed.path == '/api/delete':
            delete_watcher(int(payload['id']))
            self._send_json({'ok': True})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_create_watcher(self, payload: Dict[str, Any]) -> None:
        required = ['name', 'hotel_name', 'source_type', 'target_url', 'notify_target']
        missing = validate_required_fields(payload, required)
        if missing:
            self._send_json({'error': f'Missing fields: {", ".join(missing)}'}, HTTPStatus.BAD_REQUEST)
            return
        try:
            watcher_id = create_watcher_from_payload(payload)
            self._send_json({'ok': True, 'id': watcher_id}, HTTPStatus.CREATED)
        except json.JSONDecodeError:
            self._send_json({'error': 'Request headers in advanced settings must be valid JSON'}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({'error': str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_update_watcher(self, payload: Dict[str, Any]) -> None:
        required = ['id', 'name', 'hotel_name', 'source_type', 'target_url', 'notify_target']
        missing = validate_required_fields(payload, required)
        if missing:
            self._send_json({'error': f'Missing fields: {", ".join(missing)}'}, HTTPStatus.BAD_REQUEST)
            return
        try:
            update_watcher_from_payload(payload)
            self._send_json({'ok': True})
        except json.JSONDecodeError:
            self._send_json({'error': 'Request headers in advanced settings must be valid JSON'}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({'error': str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_check_now(self, payload: Dict[str, Any]) -> None:
        result, status = run_check_now(int(payload['id']))
        self._send_json(result, status)

    def _handle_test_notify(self, payload: Dict[str, Any]) -> None:
        webhook = str(payload.get('notify_target', '')).strip()
        notify_type = str(payload.get('notify_type', 'feishu')).strip() or 'feishu'
        if not webhook:
            self._send_json({'error': 'Please provide a notification target or bot configuration first'}, HTTPStatus.BAD_REQUEST)
            return
        try:
            send_test_notification(webhook, notify_type=notify_type)
            self._send_json({'ok': True})
        except ssl.SSLCertVerificationError:
            self._send_json({'error': 'Local Python certificate validation failed. Restart the service with the stable launcher and try again.'}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({'error': f'Test notification failed: {exc}'}, HTTPStatus.BAD_REQUEST)

    def _handle_verify_app_session(self, payload: Dict[str, Any]) -> None:
        try:
            result, status = verify_session_payload(payload)
            self._send_json(result, status)
        except json.JSONDecodeError:
            self._send_json({'error': 'Request headers in advanced settings must be valid JSON'}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            response_payload = {'error': str(exc)}
            debug_payload = getattr(exc, 'debug_payload', None)
            if debug_payload:
                response_payload['debug'] = debug_payload
            self._send_json(response_payload, HTTPStatus.BAD_REQUEST)

    def _handle_debug_app_session_screenshot(self, payload: Dict[str, Any]) -> None:
        try:
            self._send_json(debug_session_screenshot_payload(payload))
        except json.JSONDecodeError:
            self._send_json({'error': 'Request headers in advanced settings must be valid JSON'}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({'error': str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: Any) -> None:
        return
