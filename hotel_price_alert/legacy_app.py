import json
import os
import random
import re
import shutil
import sqlite3
import ssl
import threading
import tempfile
import time
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

try:
    import certifi
except Exception:
    certifi = None

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / 'data.db'
STATIC_DIR = BASE_DIR / 'static'
TEMPLATE_PATH = BASE_DIR / 'templates' / 'index.html'
POLL_INTERVAL_SECONDS = 300
DEFAULT_POLL_INTERVAL_MINUTES = 5
POLL_JITTER_SECONDS = 10
ROOM_SNIPPET_RADIUS = 1200
ROOM_PREVIEW_LIMIT = 12
PRICE_HISTORY_LIMIT = 30
DEFAULT_CHROME_USER_DATA_DIR = Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome'
DEFAULT_CHROME_PROFILE = 'Default'
APP_SESSION_PROFILE_ROOT = BASE_DIR / 'session_profiles'
APP_BUILD_VERSION = '2026-04-10-ctrip-refactor-shell-v1'
APP_SESSION_LOGIN_LOCK = threading.Lock()
APP_SESSION_LOGIN_THREADS: Dict[str, threading.Thread] = {}
APP_SESSION_LOGIN_STOP_EVENTS: Dict[str, threading.Event] = {}
APP_SESSION_LOGIN_PROCESSES: Dict[str, subprocess.Popen] = {}
APP_SESSION_DEBUG_PORTS: Dict[str, int] = {'ctrip': 9435}
FIXED_SOURCE_TYPE = 'ctrip'
APP_PORT = 8766
APP_SESSION_LOGIN_STATES: Dict[str, Dict[str, Any]] = {
    key: {
        'running': False,
        'target_url': '',
        'last_error': '',
        'last_started_at': None,
        'last_completed_at': None,
        'window_opened': False,
    }
    for key in ['ctrip']
}

CREATE_WATCHERS_SQL = '''
CREATE TABLE IF NOT EXISTS watchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    hotel_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    target_url TEXT NOT NULL,
    room_type_keyword TEXT NOT NULL DEFAULT '',
    room_type_meta TEXT NOT NULL DEFAULT '',
    price_pattern TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CNY',
    notify_type TEXT NOT NULL DEFAULT 'feishu',
    notify_target TEXT NOT NULL,
    threshold_price REAL,
    min_expected_price REAL,
    poll_interval_minutes INTEGER NOT NULL DEFAULT 5,
    request_headers TEXT NOT NULL DEFAULT '{}',
    use_local_chrome_profile INTEGER NOT NULL DEFAULT 0,
    chrome_profile_name TEXT NOT NULL DEFAULT 'Default',
    use_app_session_profile INTEGER NOT NULL DEFAULT 0,
    use_browser INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_price REAL,
    last_checked_at TEXT,
    last_notified_price REAL,
    last_price_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
'''

CREATE_HISTORY_SQL = '''
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watcher_id INTEGER NOT NULL,
    price REAL NOT NULL,
    checked_at TEXT NOT NULL
);
'''

DEFAULT_PATTERNS = {
    'ctrip': [
        r'"price"\s*:\s*"?(\d+(?:\.\d+)?)"?',
        r'"salePrice"\s*:\s*"?(\d+(?:\.\d+)?)"?',
        r'"discountPrice"\s*:\s*"?(\d+(?:\.\d+)?)"?',
        r'"displayPrice"\s*:\s*"?(\d+(?:\.\d+)?)"?',
        r'[¥￥]\s*(\d+(?:\.\d+)?)',
    ],
}

SOURCE_LABELS = {
    'ctrip': 'Ctrip',
}

SOURCE_TIPS = {
    'ctrip': 'It is best to copy a hotel detail URL from Ctrip after you have already selected the stay dates and room type.',
}

INDEX_HTML = TEMPLATE_PATH.read_text(encoding='utf-8') if TEMPLATE_PATH.exists() else ''
BROWSER_LOCK = threading.Lock()
PLAYWRIGHT_CACHE_DIR = Path.home() / 'Library' / 'Caches' / 'ms-playwright'
SYSTEM_BROWSER_CANDIDATES = [
    Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
    Path('/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
    Path('/Applications/Chromium.app/Contents/MacOS/Chromium'),
    Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
]


def _iter_browser_candidates(playwright: Any = None, prefer_system: bool = False) -> List[Path]:
    cache_candidates: List[Path] = []

    candidate_patterns = [
        'chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium',
        'chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium',
        'chromium-*/chrome-mac/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
        'chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
    ]
    for pattern in candidate_patterns:
        cache_candidates.extend(sorted(PLAYWRIGHT_CACHE_DIR.glob(pattern)))

    candidates = list(SYSTEM_BROWSER_CANDIDATES) + cache_candidates if prefer_system else cache_candidates + list(SYSTEM_BROWSER_CANDIDATES)
    seen = set()
    ordered: List[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if candidate.exists() and key not in seen:
            seen.add(key)
            ordered.append(candidate)
    return ordered


def resolve_chromium_executable(playwright: Any = None, prefer_system: bool = False) -> str:
    candidates = _iter_browser_candidates(prefer_system=prefer_system)
    if candidates:
        return str(candidates[0])
    raise FileNotFoundError(f'No usable Chromium or system Chrome executable was found. Checked: {PLAYWRIGHT_CACHE_DIR}')


def cleanup_persistent_profile_locks(profile_dir: Path) -> None:
    lock_names = [
        'SingletonLock',
        'SingletonCookie',
        'SingletonSocket',
        'DevToolsActivePort',
        'RunningChromeVersion',
        'Last Version',
    ]
    for name in lock_names:
        target = profile_dir / name
        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
        except Exception:
            pass


def copytree_ignore_runtime_entries(_dir: str, names: List[str]) -> set[str]:
    ignored = {
        'SingletonLock',
        'SingletonCookie',
        'SingletonSocket',
        'DevToolsActivePort',
        'RunningChromeVersion',
        'lockfile',
        '.org.chromium.Chromium',
    }
    return {name for name in names if name in ignored or name.endswith('.lock')}


def utc_now() -> str:
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')


def parse_utc_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = str(value).replace(' UTC', '')
        return datetime.strptime(normalized, '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def watcher_next_run_display(watcher: 'Watcher') -> Optional[str]:
    interval_seconds = max(60, int(watcher.poll_interval_minutes or DEFAULT_POLL_INTERVAL_MINUTES) * 60)
    last_checked = parse_utc_timestamp(watcher.last_checked_at)
    if last_checked is None:
        return None
    next_dt = last_checked.timestamp() + interval_seconds
    return datetime.fromtimestamp(next_dt).strftime('%Y-%m-%d %H:%M:%S UTC')


def build_ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def http_open(request: urllib.request.Request, timeout: int = 15):
    context = build_ssl_context()
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, name: str, ddl: str) -> None:
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(watchers)').fetchall()}
    if name not in columns:
        conn.execute(f'ALTER TABLE watchers ADD COLUMN {ddl}')


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(CREATE_WATCHERS_SQL)
        conn.execute(CREATE_HISTORY_SQL)
        ensure_column(conn, 'room_type_keyword', "room_type_keyword TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'room_type_meta', "room_type_meta TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'price_pattern', "price_pattern TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'currency', "currency TEXT NOT NULL DEFAULT 'CNY'")
        ensure_column(conn, 'notify_type', "notify_type TEXT NOT NULL DEFAULT 'feishu'")
        ensure_column(conn, 'min_expected_price', 'min_expected_price REAL')
        ensure_column(conn, 'poll_interval_minutes', 'poll_interval_minutes INTEGER NOT NULL DEFAULT 5')
        ensure_column(conn, 'request_headers', "request_headers TEXT NOT NULL DEFAULT '{}'")
        ensure_column(conn, 'use_local_chrome_profile', 'use_local_chrome_profile INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'chrome_profile_name', "chrome_profile_name TEXT NOT NULL DEFAULT 'Default'")
        ensure_column(conn, 'use_app_session_profile', 'use_app_session_profile INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'use_browser', 'use_browser INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'last_error', 'last_error TEXT')
        ensure_column(conn, 'last_price_note', 'last_price_note TEXT')
        conn.commit()


@dataclass
class Watcher:
    id: int
    name: str
    hotel_name: str
    source_type: str
    target_url: str
    room_type_keyword: str
    room_type_meta: str
    price_pattern: str
    currency: str
    notify_type: str
    notify_target: str
    threshold_price: Optional[float]
    min_expected_price: Optional[float]
    poll_interval_minutes: int
    request_headers: str
    use_local_chrome_profile: int
    chrome_profile_name: str
    use_app_session_profile: int
    use_browser: int
    last_error: Optional[str]
    is_active: int
    last_price: Optional[float]
    last_checked_at: Optional[str]
    last_notified_price: Optional[float]
    last_price_note: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> 'Watcher':
        data = dict(row)
        data.setdefault('room_type_keyword', '')
        data.setdefault('room_type_meta', '')
        data.setdefault('price_pattern', '')
        data.setdefault('currency', 'CNY')
        data.setdefault('notify_type', 'feishu')
        data.setdefault('min_expected_price', None)
        data.setdefault('poll_interval_minutes', DEFAULT_POLL_INTERVAL_MINUTES)
        data.setdefault('request_headers', '{}')
        data.setdefault('use_local_chrome_profile', 0)
        data.setdefault('chrome_profile_name', DEFAULT_CHROME_PROFILE)
        data.setdefault('use_app_session_profile', 0)
        data.setdefault('use_browser', 1)
        data.setdefault('last_error', None)
        data.setdefault('last_price_note', None)
        return cls(**data)

    def parsed_headers(self) -> Dict[str, str]:
        try:
            parsed = json.loads(self.request_headers or '{}')
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def meta_tags(self) -> List[str]:
        if not self.room_type_meta.strip():
            return []
        return [item for item in self.room_type_meta.split(' | ') if item]


def list_watchers() -> List[Watcher]:
    with db_connection() as conn:
        rows = conn.execute('SELECT * FROM watchers WHERE source_type = ? ORDER BY id DESC', (FIXED_SOURCE_TYPE,)).fetchall()
    return [Watcher.from_row(row) for row in rows]


def find_watcher(watcher_id: int) -> Optional[Watcher]:
    for watcher in list_watchers():
        if watcher.id == watcher_id:
            return watcher
    return None


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


def create_watcher(payload: Dict[str, Any]) -> int:
    now = utc_now()
    source_type = payload['source_type'].strip()
    normalized_headers = normalize_headers(payload.get('request_headers', '{}'), source_type)
    normalized_headers = merge_cookie_into_headers(normalized_headers, str(payload.get('cookie', '')))
    request_headers = json.dumps(normalized_headers, ensure_ascii=False)
    with db_connection() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO watchers (
                name, hotel_name, source_type, target_url, room_type_keyword,
                room_type_meta, price_pattern, currency, notify_type, notify_target, threshold_price, min_expected_price, poll_interval_minutes,
                request_headers, use_local_chrome_profile, chrome_profile_name, use_app_session_profile, use_browser, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                payload['name'].strip(),
                payload['hotel_name'].strip(),
                source_type,
                payload['target_url'].strip(),
                payload.get('room_type_keyword', '').strip(),
                payload.get('room_type_meta', '').strip(),
                payload.get('price_pattern', '').strip(),
                payload.get('currency', 'CNY').strip() or 'CNY',
                payload.get('notify_type', 'feishu').strip() or 'feishu',
                payload['notify_target'].strip(),
                payload.get('threshold_price'),
                payload.get('min_expected_price'),
                int(payload.get('poll_interval_minutes', DEFAULT_POLL_INTERVAL_MINUTES)),
                request_headers,
                1 if bool(payload.get('use_local_chrome_profile')) else 0,
                str(payload.get('chrome_profile_name') or DEFAULT_CHROME_PROFILE).strip() or DEFAULT_CHROME_PROFILE,
                1 if bool(payload.get('use_app_session_profile')) else 0,
                1 if bool(payload.get('use_browser', True)) else 0,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)




def update_watcher(watcher_id: int, payload: Dict[str, Any]) -> None:
    now = utc_now()
    source_type = payload['source_type'].strip()
    normalized_headers = normalize_headers(payload.get('request_headers', '{}'), source_type)
    normalized_headers = merge_cookie_into_headers(normalized_headers, str(payload.get('cookie', '')))
    request_headers = json.dumps(normalized_headers, ensure_ascii=False)
    with db_connection() as conn:
        conn.execute(
            '''
            UPDATE watchers
            SET name = ?, hotel_name = ?, source_type = ?, target_url = ?, room_type_keyword = ?,
                room_type_meta = ?, price_pattern = ?, currency = ?, notify_type = ?, notify_target = ?,
                threshold_price = ?, min_expected_price = ?, poll_interval_minutes = ?, request_headers = ?,
                use_local_chrome_profile = ?, chrome_profile_name = ?, use_app_session_profile = ?, use_browser = ?, updated_at = ?
            WHERE id = ?
            ''',
            (
                payload['name'].strip(),
                payload['hotel_name'].strip(),
                source_type,
                payload['target_url'].strip(),
                payload.get('room_type_keyword', '').strip(),
                payload.get('room_type_meta', '').strip(),
                payload.get('price_pattern', '').strip(),
                payload.get('currency', 'CNY').strip() or 'CNY',
                payload.get('notify_type', 'feishu').strip() or 'feishu',
                payload['notify_target'].strip(),
                payload.get('threshold_price'),
                payload.get('min_expected_price'),
                int(payload.get('poll_interval_minutes', DEFAULT_POLL_INTERVAL_MINUTES)),
                request_headers,
                1 if bool(payload.get('use_local_chrome_profile')) else 0,
                str(payload.get('chrome_profile_name') or DEFAULT_CHROME_PROFILE).strip() or DEFAULT_CHROME_PROFILE,
                1 if bool(payload.get('use_app_session_profile')) else 0,
                1 if bool(payload.get('use_browser', True)) else 0,
                now,
                watcher_id,
            ),
        )
        conn.commit()
def set_watcher_active(watcher_id: int, is_active: int) -> None:
    with db_connection() as conn:
        conn.execute('UPDATE watchers SET is_active = ?, updated_at = ? WHERE id = ?', (is_active, utc_now(), watcher_id))
        conn.commit()


def delete_watcher(watcher_id: int) -> None:
    with db_connection() as conn:
        conn.execute('DELETE FROM price_history WHERE watcher_id = ?', (watcher_id,))
        conn.execute('DELETE FROM watchers WHERE id = ?', (watcher_id,))
        conn.commit()


def fetch_text(url: str, headers: Dict[str, str]) -> str:
    request = urllib.request.Request(url, headers=headers)
    with http_open(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or 'utf-8'
        return response.read().decode(charset, errors='ignore')


def extract_ctrip_room_blocks(page: Any) -> List[Dict[str, Any]]:
    script = r"""
() => {
  const nodes = Array.from(document.querySelectorAll('*'));
  const roomHint = /(房|床|套房|双早|大床|双床|Deluxe|King|Twin|Suite|Room|Villa|泳池|水疗|Spa|Pool)/i;
  const todayPriceHint = /(今日价格|选择房间|起订|预订)/i;
  const taxHint = /(含税\/?费|含税费|税费均|含税\/费\s*均)/i;
  const breakfastHint = /(含早|双早|单早|早餐|Breakfast)/i;
  const cancelHint = /(免费取消|不可取消|不可退款|免费退|No refund|Free cancellation)/i;
  const payHint = /(到店付|在线付|预付|Pay at property|Prepay)/i;
  const badRoomNameHint = /(photo gallery|照片|查看所有|Go to main content|房型摘要|携程旅行网|联系客服|我的订单|房间详情 房型摘要)/i;
  const badPriceContextHint = /(张照片|平方米|m²|平米|楼层|邮编|地址|Batok Bay|Wi-Fi|可住人数|1张|2张|3张|4张)/i;
  const currencyPriceRegex = /[¥￥]\s*([0-9][0-9,]{2,}(?:\.\d{1,2})?)/g;

  const pickText = (node) => {
    if (!node) return '';
    const preferred = [
      node.innerText || '',
      node.getAttribute?.('aria-label') || '',
      node.getAttribute?.('title') || '',
      node.getAttribute?.('data-title') || '',
      node.getAttribute?.('alt') || '',
      node.textContent || '',
    ];
    for (const value of preferred) {
      const text = String(value || '').replace(/\u00a0/g, ' ').trim();
      if (text) return text;
    }
    return '';
  };

  const normalizeValue = (raw) => Number(String(raw || '').replace(/,/g, '').replace(/[^\d.]/g, ''));

  const currencyPricesWithPos = (text) => {
    const items = [];
    for (const match of String(text || '').matchAll(currencyPriceRegex)) {
      const value = normalizeValue(match[1]);
      if (value >= 500 && value <= 100000) {
        items.push({ value, pos: match.index || 0 });
      }
    }
    return items;
  };

  const nearestFollowingPrice = (text, hintRegex, maxDistance = 80) => {
    const hints = Array.from(String(text || '').matchAll(new RegExp(hintRegex.source, 'ig')));
    const prices = currencyPricesWithPos(text);
    const results = [];
    for (const hint of hints) {
      const hintPos = hint.index || 0;
      const candidate = prices.find((item) => item.pos >= hintPos && item.pos - hintPos <= maxDistance);
      if (candidate) {
        const near = String(text || '').slice(Math.max(0, hintPos - 12), Math.min(String(text || '').length, candidate.pos + 24));
        if (!badPriceContextHint.test(near)) results.push(candidate.value);
      }
    }
    return results;
  };

  const collectPriceCandidates = (text) => {
    const sourceText = String(text || '');
    const candidates = [];

    for (const value of nearestFollowingPrice(sourceText, taxHint, 100)) {
      candidates.push({ value, score: 100, source: 'tax_included' });
    }
    for (const value of nearestFollowingPrice(sourceText, todayPriceHint, 80)) {
      candidates.push({ value, score: 80, source: 'today_price' });
    }

    const prices = currencyPricesWithPos(sourceText);
    for (const item of prices) {
      const near = sourceText.slice(Math.max(0, item.pos - 24), Math.min(sourceText.length, item.pos + 24));
      let score = 10;
      if (taxHint.test(near)) score += 30;
      if (todayPriceHint.test(near)) score += 18;
      if (badPriceContextHint.test(near)) score -= 40;
      candidates.push({ value: item.value, score, source: 'currency' });
    }

    candidates.sort((a, b) => (b.score - a.score) || (a.value - b.value));
    return candidates;
  };

  const findRoomName = (text) => {
    const lines = String(text || '').split(/\n+/).map(s => s.trim()).filter(Boolean);
    for (const line of lines) {
      if (line.length > 80) continue;
      if (badRoomNameHint.test(line)) continue;
      if (roomHint.test(line)) return line;
    }
    return '';
  };

  const seen = new Set();
  const results = [];
  const pushResult = (roomName, blockText, tags) => {
    if (!roomName || badRoomNameHint.test(roomName)) return;
    const candidates = collectPriceCandidates(blockText).filter((item) => item.value >= 500);
    if (!candidates.length) return;
    const best = candidates[0];
    const key = `${roomName}__${best.value}`;
    if (seen.has(key)) return;
    seen.add(key);
    results.push({
      room_name: roomName,
      price: best.value,
      tags,
      raw_text: String(blockText || '').slice(0, 420) + ` [price_source=${best.source}; candidates=${candidates.slice(0, 4).map(item => item.value).join('/')}]`,
    });
  };

  for (const node of nodes) {
    const selfText = pickText(node);
    if (!selfText) continue;
    if (!roomHint.test(selfText) && !todayPriceHint.test(selfText) && !taxHint.test(selfText)) continue;

    let container = node;
    let bestText = selfText;
    let depth = 0;
    while (container && depth < 6) {
      const currentText = pickText(container);
      if (currentText && currentText.length <= 1800) bestText = currentText;
      if (roomHint.test(bestText) && (todayPriceHint.test(bestText) || taxHint.test(bestText))) break;
      container = container.parentElement;
      depth += 1;
    }

    const roomName = findRoomName(bestText) || findRoomName(selfText);
    if (!roomName) continue;

    const tags = [];
    const breakfast = bestText.match(breakfastHint);
    const cancel = bestText.match(cancelHint);
    const pay = bestText.match(payHint);
    if (breakfast) tags.push(breakfast[1]);
    if (cancel) tags.push(cancel[1]);
    if (pay) tags.push(pay[1]);

    pushResult(roomName, bestText, tags);
  }

  return results.slice(0, 30);
}
"""
    try:
        items = page.evaluate(script)
        return items if isinstance(items, list) else []
    except Exception:
        return []

def extract_room_blocks_for_source(page: Any, source_type: str, room_keyword: str = '') -> List[Dict[str, Any]]:
    return extract_ctrip_room_blocks(page)


def detect_page_signals(source_type: str, final_url: str, title: str, lower_preview: str, room_block_count: int) -> Dict[str, Any]:
    risk_like = any(token in lower_preview for token in ['验证', 'captcha', '风控', '访问异常', '稍后再试'])
    booking_like = False
    if source_type == 'ctrip':
        login_like = ('passport.ctrip.com' in final_url) or any(token in lower_preview for token in ['账号密码登录', '手机号查单', '验证码登录', '登录首页']) or ('登录首页' in title)
        booking_like = ('/booknew' in final_url) or ('您的详细资讯' in title) or any(token in lower_preview for token in ['预订详情', '最后一步', '住客资料', '房间整晚保留'])
    else:
        login_like = any(token in lower_preview for token in ['登录', 'login', '手机号', '验证', '验证码'])
    return {
        'login_like': login_like,
        'risk_like': risk_like,
        'booking_like': booking_like,
        'empty_room_like': room_block_count == 0,
    }


def encode_room_blocks(items: List[Dict[str, Any]]) -> str:
    if not items:
        return ''
    return '\n'.join([
        f"ROOM_BLOCK||{item.get('room_name', '')}||{item.get('price', '')}||{' | '.join(item.get('tags', []))}||{item.get('raw_text', '')}"
        for item in items
    ])


def encode_page_debug(debug_info: Dict[str, Any]) -> str:
    if not debug_info:
        return ''
    payload = json.dumps(debug_info, ensure_ascii=False)
    return f"PAGE_DEBUG||{payload}"


def parse_room_blocks(text: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith('ROOM_BLOCK||'):
            continue
        parts = line.split('||', 4)
        if len(parts) < 5:
            continue
        room_name = parts[1].strip()
        price_text = parts[2].strip()
        tags_text = parts[3].strip()
        raw_text = parts[4].strip()
        try:
            price = float(price_text.replace(',', ''))
        except ValueError:
            continue
        items.append({'room_name': room_name, 'price': price, 'tags': [tag for tag in tags_text.split(' | ') if tag], 'raw_text': raw_text})
    return items


def parse_page_debug(text: str) -> Dict[str, Any]:
    for line in text.splitlines():
        if not line.startswith('PAGE_DEBUG||'):
            continue
        raw = line.split('||', 1)[1]
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def room_like_lines(text: str) -> List[str]:
    text = search_text_only(text)
    lines = [normalize_room_name(line) for line in text.splitlines()]
    lines = [line for line in lines if line and not looks_garbled(line)]
    room_hint = re.compile(r'(房|床|套房|双早|大床|双床|Deluxe|King|Twin|Suite|Room|Villa|泳池|水疗|Spa|Pool)', re.I)
    results = []
    seen = set()
    for index, line in enumerate(lines):
        if not room_hint.search(line):
            continue
        block = ' '.join(lines[max(0, index - 1): index + 3])
        if block in seen:
            continue
        seen.add(block)
        results.append(block)
        if len(results) >= 20:
            break
    return results


def room_candidate_summaries(text: str, limit: int = 8) -> List[str]:
    block_items = parse_room_blocks(text)
    search_text = search_text_only(text)
    summaries: List[str] = []
    if block_items:
        for item in block_items[:limit]:
            room_name = str(item.get('room_name', '')).strip()
            price = item.get('price')
            tags = item.get('tags', []) or []
            tag_text = f" [{' / '.join(tags)}]" if tags else ''
            if room_name:
                summaries.append(f"{room_name} ¥{price}{tag_text}")
        if summaries:
            return summaries

    for line in room_like_lines(text)[:limit]:
        summaries.append(line[:100])
    return summaries


def raw_html_keyword_snippets(text: str, room_keyword: str, limit: int = 4) -> List[str]:
    marker = '\n\n<!--RAW_HTML-->\n'
    if marker not in text:
        return []
    raw_html = text.split(marker, 1)[1]
    snippets: List[str] = []
    seen = set()
    for variant in keyword_variants(room_keyword)[:6]:
        try:
            pattern = re.escape(variant)
            match = re.search(pattern, raw_html, re.I)
        except re.error:
            match = None
        if not match:
            continue
        start = max(0, match.start() - 500)
        end = min(len(raw_html), match.end() + 1800)
        snippet = raw_html[start:end]
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        if snippet and snippet not in seen:
            seen.add(snippet)
            snippets.append(snippet[:2200])
        if len(snippets) >= limit:
            break
    return snippets


def build_room_debug_payload(text: str, room_keyword: str, watcher: Optional[Watcher] = None) -> Dict[str, Any]:
    page_debug = parse_page_debug(text)
    matched_blocks: List[Dict[str, Any]] = []
    if watcher is not None:
        try:
            matched_blocks = matched_room_blocks(text, watcher)[:10]
        except Exception:
            matched_blocks = []
    snippets: List[str] = []
    for variant in keyword_variants(room_keyword)[:6]:
        search_text = search_text_only(text)
        try:
            match = re.search(re.escape(variant), search_text, re.I)
        except re.error:
            match = None
        if not match:
            continue
        start = max(0, match.start() - 220)
        end = min(len(search_text), match.end() + 380)
        snippet = search_text[start:end].replace('\n', ' ')
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet[:600])
        if len(snippets) >= 4:
            break
    return {
        'room_keyword': room_keyword,
        'keyword_variants': keyword_variants(room_keyword),
        'room_candidates': room_candidate_summaries(text, 10),
        'room_like_lines': room_like_lines(text)[:10],
        'matched_room_blocks': matched_blocks,
        'keyword_snippets': snippets,
        'raw_html_snippets': raw_html_keyword_snippets(text, room_keyword),
        'page_debug': page_debug,
    }


def expand_dynamic_sections(page: Any, source_type: str) -> None:
    selectors: List[str] = []
    if source_type == 'ctrip':
        selectors = [
            'text=全部房型', 'text=查看全部房型', 'text=展开全部房型', 'text=更多房型', 'text=全部展开'
        ]
    try:
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = min(locator.count(), 4)
                for index in range(count):
                    item = locator.nth(index)
                    if item.is_visible(timeout=600):
                        item.click(timeout=800)
                        page.wait_for_timeout(700)
            except Exception:
                continue
        wheel_rounds = 6
        for _ in range(wheel_rounds):
            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(700)
    except Exception:
        pass

def prepare_local_chrome_profile(profile_name: str) -> tuple[Path, str]:
    source_root = DEFAULT_CHROME_USER_DATA_DIR
    source_profile = source_root / profile_name
    if not source_root.exists():
        raise FileNotFoundError(f'Local Chrome user data directory was not found: {source_root}')
    if not source_profile.exists():
        raise FileNotFoundError(f'Local Chrome profile was not found: {source_profile}')

    temp_root = Path(tempfile.mkdtemp(prefix='hotel-alert-chrome-'))
    local_state = source_root / 'Local State'
    if local_state.exists():
        shutil.copy2(local_state, temp_root / 'Local State')
    shutil.copytree(source_profile, temp_root / profile_name, dirs_exist_ok=True)
    return temp_root, profile_name


def prepare_app_session_profile_copy(source_type: str) -> tuple[Path, Path]:
    profile_dir = ensure_app_session_profile_dir(source_type)
    temp_root = Path(tempfile.mkdtemp(prefix=f'hotel-alert-{source_type}-session-'))
    cleanup_persistent_profile_locks(profile_dir)
    if profile_dir.exists():
        shutil.copytree(
            profile_dir,
            temp_root,
            dirs_exist_ok=True,
            ignore=copytree_ignore_runtime_entries,
            ignore_dangling_symlinks=True,
        )
    cleanup_persistent_profile_locks(temp_root)
    default_dir = temp_root / 'Default'
    default_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir, temp_root


def session_login_label(source_type: str) -> str:
    return 'Ctrip'


def session_default_target_url(source_type: str) -> str:
    return 'https://hotels.ctrip.com/'


def resolve_login_browser_executable() -> str:
    for candidate in SYSTEM_BROWSER_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError('No supported system browser was found for login. Install Google Chrome and try again.')


def ensure_app_session_profile_dir(source_type: str) -> Path:
    profile_dir = APP_SESSION_PROFILE_ROOT / source_type
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def app_session_cookie_snapshot_path(source_type: str) -> Path:
    return ensure_app_session_profile_dir(source_type) / 'cookies.snapshot.json'


def load_app_session_cookie_snapshot(source_type: str) -> List[Dict[str, Any]]:
    path = app_session_cookie_snapshot_path(source_type)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        cookies = payload.get('cookies') if isinstance(payload, dict) else payload
        if isinstance(cookies, list):
            return [item for item in cookies if isinstance(item, dict)]
    except Exception:
        return []
    return []


def save_app_session_cookie_snapshot(source_type: str, cookies: List[Dict[str, Any]]) -> int:
    normalized: List[Dict[str, Any]] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get('domain') or '')
        name = str(cookie.get('name') or '')
        if 'ctrip' not in domain and 'ctrip' not in name.lower():
            continue
        item = dict(cookie)
        if item.get('sameSite') not in {'Strict', 'Lax', 'None'}:
            item['sameSite'] = 'Lax'
        normalized.append(item)
    path = app_session_cookie_snapshot_path(source_type)
    path.write_text(json.dumps({'updated_at': utc_now(), 'cookies': normalized}, ensure_ascii=False), encoding='utf-8')
    return len(normalized)


def export_app_session_cookies_via_cdp(source_type: str) -> Dict[str, Any]:
    debug_port = int(APP_SESSION_DEBUG_PORTS.get(source_type) or 0)
    if debug_port <= 0 or not can_connect_app_session_debug_port(source_type):
        return {'ok': False, 'cookie_count': 0, 'message': 'No reachable debug port was found for the dedicated browser session'}
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{debug_port}')
        contexts = browser.contexts
        if not contexts:
            return {'ok': False, 'cookie_count': 0, 'message': 'Connected to the dedicated browser, but no usable browser context was available'}
        cookies = contexts[0].cookies()
        cookie_count = save_app_session_cookie_snapshot(source_type, cookies)
        return {
            'ok': cookie_count > 0,
            'cookie_count': cookie_count,
            'path': str(app_session_cookie_snapshot_path(source_type)),
            'message': f'Exported {cookie_count} cookie snapshot entries' if cookie_count > 0 else 'No valid cookie snapshot could be exported',
        }
    finally:
        playwright.stop()


def ctrip_profile_has_auth_cookie(profile_dir: Path) -> bool:
    cookie_db = profile_dir / 'Default' / 'Cookies'
    if not cookie_db.exists():
        return False
    try:
        conn = sqlite3.connect(f'file:{cookie_db}?mode=ro', uri=True)
        try:
            row = conn.execute(
                "select 1 from cookies where host_key like '%ctrip%' and name in ('cticket','login_uid','AHeadUserInfo') limit 1"
            ).fetchone()
            return bool(row)
        finally:
            conn.close()
    except Exception:
        return False


def rebuild_clean_ctrip_profile_dir(profile_dir: Path) -> Optional[str]:
    if not profile_dir.exists():
        profile_dir.mkdir(parents=True, exist_ok=True)
        return None
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir = profile_dir.with_name(f"{profile_dir.name}.backup-{timestamp}")
    try:
        cleanup_persistent_profile_locks(profile_dir)
        profile_dir.rename(backup_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        return str(backup_dir)
    except Exception:
        shutil.rmtree(profile_dir, ignore_errors=True)
        profile_dir.mkdir(parents=True, exist_ok=True)
        return None

def _set_app_session_login_state(source_type: str, **kwargs: Any) -> None:
    with APP_SESSION_LOGIN_LOCK:
        state = APP_SESSION_LOGIN_STATES.setdefault(source_type, {
            'running': False,
            'target_url': '',
            'last_error': '',
            'last_started_at': None,
            'last_completed_at': None,
            'window_opened': False,
            'reset_backup_dir': '',
        })
        state.update(kwargs)


def _app_session_login_worker(source_type: str, target_url: str, stop_event: threading.Event) -> None:
    _set_app_session_login_state(source_type,
        running=True,
        target_url=target_url,
        last_error='',
        last_started_at=utc_now(),
        window_opened=False,
    )
    process = None
    try:
        executable_path = resolve_login_browser_executable()
        profile_dir = ensure_app_session_profile_dir(source_type)
        reset_backup_dir = None
        if source_type == 'ctrip' and not ctrip_profile_has_auth_cookie(profile_dir):
            reset_backup_dir = rebuild_clean_ctrip_profile_dir(profile_dir)
        cleanup_persistent_profile_locks(profile_dir)
        command = [
            executable_path,
            f'--user-data-dir={profile_dir}',
            '--profile-directory=Default',
            '--no-first-run',
            '--no-default-browser-check',
        ]
        debug_port = int(APP_SESSION_DEBUG_PORTS.get(source_type) or 0)
        if debug_port > 0:
            command.append(f'--remote-debugging-port={debug_port}')
        command.append(target_url)
        process = subprocess.Popen(command)
        with APP_SESSION_LOGIN_LOCK:
            APP_SESSION_LOGIN_PROCESSES[source_type] = process
        _set_app_session_login_state(source_type, window_opened=True, reset_backup_dir=reset_backup_dir or '')
        while not stop_event.is_set():
            if process.poll() is not None:
                break
            time.sleep(0.8)
    except Exception as exc:
        _set_app_session_login_state(source_type, last_error=str(exc))
    finally:
        still_running = bool(process and process.poll() is None)
        with APP_SESSION_LOGIN_LOCK:
            APP_SESSION_LOGIN_PROCESSES.pop(source_type, None)
        _set_app_session_login_state(source_type, running=False, window_opened=still_running, last_completed_at=utc_now())


def launch_login_and_save_session(source_type: str, target_url: str) -> Dict[str, Any]:
    profile_dir = ensure_app_session_profile_dir(source_type)
    label = session_login_label(source_type)
    with APP_SESSION_LOGIN_LOCK:
        thread = APP_SESSION_LOGIN_THREADS.get(source_type)
        if thread and thread.is_alive():
            return {
                'ok': True,
                'already_running': True,
                'message': f'The {label} login window is already open. Complete the login there, then click “I Finished Login”.',
                'profile_dir': str(profile_dir),
            }
        stop_event = threading.Event()
        thread = threading.Thread(target=_app_session_login_worker, args=(source_type, target_url, stop_event), daemon=True)
        APP_SESSION_LOGIN_STOP_EVENTS[source_type] = stop_event
        APP_SESSION_LOGIN_THREADS[source_type] = thread
        thread.start()

    for _ in range(20):
        time.sleep(0.15)
        state = app_session_profile_status(source_type)
        if state.get('last_error'):
            raise RuntimeError(state['last_error'])
        if state.get('login_running') and state.get('window_opened'):
            break

    state = app_session_profile_status(source_type)
    reset_hint = f" A backup of the old profile directory was created at: {state.get('reset_backup_dir')}" if state.get('reset_backup_dir') else ''
    return {
        'ok': True,
        'message': f'Opened the {label} login window. Complete the login in the browser, then come back and click “I Finished Login”.{reset_hint}',
        'profile_dir': str(profile_dir),
        'status': state,
    }


def finish_login_and_save_session(source_type: str) -> Dict[str, Any]:
    label = session_login_label(source_type)
    with APP_SESSION_LOGIN_LOCK:
        stop_event = APP_SESSION_LOGIN_STOP_EVENTS.get(source_type)
        thread = APP_SESSION_LOGIN_THREADS.get(source_type)
        process = APP_SESSION_LOGIN_PROCESSES.get(source_type)
    if stop_event:
        stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout=8)
    state = app_session_profile_status(source_type)
    saved_ok = bool(state.get('has_auth_cookie')) if source_type == 'ctrip' else True
    snapshot_result = {'ok': False, 'cookie_count': 0, 'message': ''}
    if saved_ok and source_type == 'ctrip':
        snapshot_result = export_app_session_cookies_via_cdp(source_type)
    snapshot_hint = f" Synced {snapshot_result.get('cookie_count', 0)} cookie snapshot entries for background use." if snapshot_result.get('ok') else ''
    success_message = (
        f'The {label} session has been saved. Future verification and checks will prefer the background cookie snapshot instead of relying on the foreground login window.'
        f'{snapshot_hint} You can now close the dedicated Ctrip login window. Future “Verify Session”, “Check Now”, and automatic monitoring runs will use the background session.'
        ' If the session expires later, reopen the dedicated window, sign in again, and click “I Finished Login”.'
    )
    return {
        'ok': saved_ok,
        'message': (success_message if saved_ok else 'No valid login cookie was detected in the dedicated Ctrip profile yet. Make sure you really completed sign-in in the opened browser window, then click “I Finished Login” again.'),
        'profile_dir': str(ensure_app_session_profile_dir(source_type)),
        'status': state,
        'snapshot': snapshot_result,
    }




def get_live_app_session_process(source_type: str) -> Optional[subprocess.Popen]:
    with APP_SESSION_LOGIN_LOCK:
        process = APP_SESSION_LOGIN_PROCESSES.get(source_type)
    if process and process.poll() is None:
        return process
    return None


def can_connect_app_session_debug_port(source_type: str) -> bool:
    debug_port = int(APP_SESSION_DEBUG_PORTS.get(source_type) or 0)
    if debug_port <= 0:
        return False
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json/version', timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def try_open_app_session_page_via_cdp(playwright: Any, url: str, source_type: str, headers: Dict[str, str], focus_room: bool) -> Optional[Dict[str, Any]]:
    return None


def app_session_profile_status(source_type: str = 'ctrip') -> Dict[str, Any]:
    profile_dir = APP_SESSION_PROFILE_ROOT / source_type
    with APP_SESSION_LOGIN_LOCK:
        thread = APP_SESSION_LOGIN_THREADS.get(source_type)
        running = bool(thread and thread.is_alive())
        state = dict(APP_SESSION_LOGIN_STATES.get(source_type) or {})
    return {
        'exists': profile_dir.exists(),
        'profile_dir': str(profile_dir),
        'has_auth_cookie': ctrip_profile_has_auth_cookie(profile_dir) if source_type == 'ctrip' else False,
        'has_cookie_snapshot': bool(load_app_session_cookie_snapshot(source_type)),
        'login_running': running,
        'window_opened': bool(state.get('window_opened')) or can_connect_app_session_debug_port(source_type),
        'debug_port': int(APP_SESSION_DEBUG_PORTS.get(source_type) or 0),
        'target_url': state.get('target_url') or '',
        'reset_backup_dir': state.get('reset_backup_dir') or '',
        'last_error': state.get('last_error') or '',
        'last_started_at': state.get('last_started_at'),
        'last_completed_at': state.get('last_completed_at'),
        'source_type': source_type,
        'source_label': session_login_label(source_type),
    }


def recent_target_url(source_type: str) -> str:
    for watcher in list_watchers():
        if watcher.source_type == source_type and watcher.target_url.strip():
            return watcher.target_url.strip()
    return session_default_target_url(source_type)


def startup_session_check(source_type: str = 'ctrip') -> Dict[str, Any]:
    status = app_session_profile_status(source_type)
    if status.get('login_running'):
        return {
            'ok': False,
            'needs_login': True,
            'message': f'The dedicated {session_login_label(source_type)} login window is still open. Finish the login first, then continue.',
            'status': status,
        }
    if not status.get('exists'):
        return {
            'ok': False,
            'needs_login': True,
            'message': f'No dedicated {session_login_label(source_type)} session has been saved yet. Sign in and save the session first.',
            'status': status,
            'target_url': recent_target_url(source_type),
        }
    if source_type == 'ctrip' and not status.get('has_auth_cookie'):
        return {
            'ok': False,
            'needs_login': True,
            'message': 'The dedicated Ctrip session does not contain a valid login cookie yet. Start the login flow again and complete sign-in.',
            'status': status,
            'target_url': recent_target_url(source_type),
        }

    target_url = recent_target_url(source_type)
    headers = source_default_headers(source_type)
    try:
        result = verify_app_session(target_url, headers, source_type)
        return {
            'ok': bool(result.get('ok')),
            'needs_login': not bool(result.get('ok')),
            'message': f'{session_login_label(source_type)} dedicated session verified successfully' if result.get('ok') else f'The dedicated {session_login_label(source_type)} session has expired. Please sign in again.',
            'target_url': target_url,
            'page_debug': result.get('page_debug'),
            'status': status,
        }
    except Exception as exc:
        payload = {
            'ok': False,
            'needs_login': True,
            'message': f'Failed to verify the dedicated {session_login_label(source_type)} session: {exc}',
            'target_url': target_url,
            'status': status,
        }
        debug_payload = getattr(exc, 'debug_payload', None)
        if debug_payload:
            payload['debug'] = debug_payload
        return payload


def startup_all_session_checks() -> Dict[str, Any]:
    result = startup_session_check('ctrip')
    return {
        'ok': bool(result.get('ok')),
        'items': {'ctrip': result},
        'message': 'Ctrip: available' if result.get('ok') else 'Ctrip: login or re-verification required',
        'source_type': 'ctrip',
    }


def verify_app_session(target_url: str, headers: Dict[str, str], source_type: str) -> Dict[str, Any]:
    text = browser_fetch_with_app_session(target_url, headers, source_type, '')
    page_debug = parse_page_debug(text)
    signals = page_debug.get('signals') or {}
    final_url = str(page_debug.get('final_url') or '')
    login_hosts = {
        'ctrip': ['passport.ctrip.com'],
    }
    host_hit = any(token in final_url for token in login_hosts.get(source_type, []))
    ok = not signals.get('login_like') and not host_hit
    label = session_login_label(source_type)
    return {
        'ok': ok,
        'message': 'Dedicated session is available' if ok else f'The dedicated session still falls back to the {label} login page. Sign in again and retry.',
        'page_debug': page_debug,
    }


def _open_app_session_page(url: str, headers: Dict[str, str], source_type: str, room_keyword: str = '', focus_room: bool = True) -> Dict[str, Any]:
    with APP_SESSION_LOGIN_LOCK:
        thread = APP_SESSION_LOGIN_THREADS.get(source_type)
        if thread and thread.is_alive():
            raise RuntimeError(f'The {session_login_label(source_type)} login window is still open. Click “I Finished Login” first to save the session before identifying room content.')
    playwright = sync_playwright().start()
    browser = None
    context = None
    try:
        cookies = load_app_session_cookie_snapshot(source_type)
        if not cookies and can_connect_app_session_debug_port(source_type):
            export_app_session_cookies_via_cdp(source_type)
            cookies = load_app_session_cookie_snapshot(source_type)
        if not cookies:
            raise RuntimeError(f'The background cookie snapshot for {session_login_label(source_type)} is unavailable. Start the login flow, complete sign-in, then click “I Finished Login” again.')
        executable_path = resolve_chromium_executable(playwright, prefer_system=False)
        browser = playwright.chromium.launch(
            executable_path=executable_path,
            headless=True,
        )
        context = browser.new_context(
            locale='zh-CN',
            user_agent=headers.get('User-Agent'),
            extra_http_headers={k: v for k, v in headers.items() if k.lower() not in {'user-agent', 'cookie'}},
            viewport={'width': 1440, 'height': 2200},
        )
        context.add_cookies(cookies)
        page = context.new_page()
        fetch_url = normalize_target_url(url, source_type)
        page.goto(fetch_url, wait_until='domcontentloaded', timeout=45000)
        try:
            page.wait_for_load_state('networkidle', timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(3000)
        currency_debug = {}
        room_focus_debug = {'mode': 'cookie_snapshot', 'cookie_count': len(cookies)}
        if focus_room:
            expand_dynamic_sections(page, source_type)
        return {
            'playwright': playwright,
            'browser': browser,
            'context': context,
            'page': page,
            'profile_dir': ensure_app_session_profile_dir(source_type),
            'temp_profile_dir': None,
            'fetch_url': fetch_url,
            'currency_debug': currency_debug,
            'room_focus_debug': room_focus_debug,
            'live_browser_mode': False,
        }
    except Exception:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        elif browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        playwright.stop()
        raise



def browser_capture_with_app_session(url: str, headers: Dict[str, str], source_type: str, room_keyword: str = '', focus_room: bool = False) -> Dict[str, Any]:
    state = _open_app_session_page(url, headers, source_type, room_keyword, focus_room=focus_room)
    context = state['context']
    playwright = state['playwright']
    page = state['page']
    try:
        safe_source = 'ctrip'
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        out_dir = BASE_DIR / 'debug_screens'
        out_dir.mkdir(parents=True, exist_ok=True)
        top_path = out_dir / f'{safe_source}-app-session-top-{ts}.png'
        full_path = out_dir / f'{safe_source}-app-session-full-{ts}.png'
        page.screenshot(path=str(top_path), full_page=False)
        page.screenshot(path=str(full_path), full_page=True)
        page_title = ''
        try:
            page_title = page.title()
        except Exception:
            page_title = ''
        visible_text = page.locator('body').inner_text(timeout=5000)
        visible_lines = [line.strip() for line in visible_text.splitlines() if line.strip()][:30]
        return {
            'top_path': str(top_path),
            'full_path': str(full_path),
            'title': page_title,
            'final_url': page.url,
            'visible_lines_preview': visible_lines[:20],
            'currency_debug': state.get('currency_debug') or {},
            'room_focus_debug': state.get('room_focus_debug') or {},
            'profile_dir': str(state.get('profile_dir')),
        }
    finally:
        temp_profile_dir = state.get('temp_profile_dir')
        live_browser_mode = bool(state.get('live_browser_mode'))
        browser = state.get('browser')
        try:
            if live_browser_mode:
                try:
                    page.close()
                except Exception:
                    pass
            elif browser is not None:
                browser.close()
            else:
                context.close()
        finally:
            playwright.stop()
            if temp_profile_dir:
                shutil.rmtree(temp_profile_dir, ignore_errors=True)


def browser_fetch_with_app_session(url: str, headers: Dict[str, str], source_type: str, room_keyword: str = '') -> str:
    state = _open_app_session_page(url, headers, source_type, room_keyword, focus_room=True)
    context = state['context']
    playwright = state['playwright']
    page = state['page']
    profile_dir = state['profile_dir']
    fetch_url = state['fetch_url']
    currency_debug = state['currency_debug']
    room_focus_debug = state['room_focus_debug']
    try:
        room_blocks = extract_room_blocks_for_source(page, source_type, room_keyword)
        page_title = ''
        try:
            page_title = page.title()
        except Exception:
            page_title = ''
        visible_text = page.locator('body').inner_text(timeout=5000)
        room_block_text = encode_room_blocks(room_blocks)
        visible_lines = [line.strip() for line in visible_text.splitlines() if line.strip()][:30]
        joined_preview = ' | '.join(visible_lines[:12])
        lower_preview = joined_preview.lower()
        page_debug = {
            'requested_url': fetch_url,
            'final_url': page.url,
            'title': page_title,
            'visible_line_count': len(visible_lines),
            'visible_lines_preview': visible_lines[:20],
            'room_block_count': len(room_blocks),
            'signals': detect_page_signals(source_type, page.url, page_title, lower_preview, len(room_blocks)),
            'app_session_mode': True,
            'profile_dir': str(profile_dir),
            'currency_debug': currency_debug,
            'current_currency': (currency_debug.get('after_currency') or currency_debug.get('before_currency') or ''),
            'room_focus_debug': room_focus_debug,
        }
        page_debug_text = encode_page_debug(page_debug)
        content = page_debug_text + ('\n' if page_debug_text else '') + room_block_text + ('\n' if room_block_text else '') + visible_text + '\n\n<!--RAW_HTML-->\n' + page.content()
        return content
    finally:
        temp_profile_dir = state.get('temp_profile_dir')
        live_browser_mode = bool(state.get('live_browser_mode'))
        browser = state.get('browser')
        try:
            if live_browser_mode:
                try:
                    page.close()
                except Exception:
                    pass
            elif browser is not None:
                browser.close()
            else:
                context.close()
        finally:
            playwright.stop()
            if temp_profile_dir:
                shutil.rmtree(temp_profile_dir, ignore_errors=True)


def discover_chrome_profiles() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    root = DEFAULT_CHROME_USER_DATA_DIR
    if not root.exists():
        return items

    local_state_path = root / 'Local State'
    profile_names: Dict[str, str] = {}
    if local_state_path.exists():
        try:
            local_state = json.loads(local_state_path.read_text(encoding='utf-8'))
            info_cache = local_state.get('profile', {}).get('info_cache', {})
            if isinstance(info_cache, dict):
                for key, value in info_cache.items():
                    if isinstance(value, dict):
                        profile_names[key] = str(value.get('name') or key)
        except Exception:
            pass

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == 'System Profile' or child.name.startswith('Guest'):
            continue
        if child.name == 'Default' or child.name.startswith('Profile '):
            items.append({'dir_name': child.name, 'display_name': profile_names.get(child.name, child.name)})

    if not items and (root / 'Default').exists():
        items.append({'dir_name': 'Default', 'display_name': 'Default'})
    return items


def browser_fetch_with_local_profile(url: str, headers: Dict[str, str], source_type: str, profile_name: str, room_keyword: str = '') -> str:
    temp_root, copied_profile_name = prepare_local_chrome_profile(profile_name)
    try:
        with sync_playwright() as playwright:
            executable_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(temp_root),
                executable_path=executable_path,
                headless=True,
                locale='zh-CN',
                user_agent=headers.get('User-Agent'),
                extra_http_headers={k: v for k, v in headers.items() if k.lower() not in {'user-agent', 'cookie'}},
                args=[f'--profile-directory={copied_profile_name}', '--no-first-run'],
            )
            page = context.new_page()
            fetch_url = normalize_target_url(url, source_type)
            page.goto(fetch_url, wait_until='domcontentloaded', timeout=45000)
            try:
                page.wait_for_load_state('networkidle', timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            currency_debug = {}
            expand_dynamic_sections(page, source_type)
            room_blocks = extract_room_blocks_for_source(page, source_type, room_keyword)
            page_title = ''
            try:
                page_title = page.title()
            except Exception:
                page_title = ''
            visible_text = page.locator('body').inner_text(timeout=5000)
            room_block_text = encode_room_blocks(room_blocks)
            visible_lines = [line.strip() for line in visible_text.splitlines() if line.strip()][:30]
            joined_preview = ' | '.join(visible_lines[:12])
            lower_preview = joined_preview.lower()
            page_debug = {
                'requested_url': fetch_url,
                'final_url': page.url,
                'title': page_title,
                'visible_line_count': len(visible_lines),
                'visible_lines_preview': visible_lines[:20],
                'room_block_count': len(room_blocks),
                'signals': detect_page_signals(source_type, page.url, page_title, lower_preview, len(room_blocks)),
                'local_profile_mode': True,
                'chrome_profile_name': profile_name,
                'currency_debug': currency_debug,
                'current_currency': (currency_debug.get('after_currency') or currency_debug.get('before_currency') or ''),
            }
            page_debug_text = encode_page_debug(page_debug)
            content = page_debug_text + ('\n' if page_debug_text else '') + room_block_text + ('\n' if room_block_text else '') + visible_text + '\n\n<!--RAW_HTML-->\n' + page.content()
            context.close()
            return content
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    if source_type != 'ctrip':
        return

    selectors = [
        'text=全部房型',
        'text=查看全部房型',
        'text=展开全部房型',
        'text=更多房型',
        'text=全部展开',
        '[class*=room] button',
        '[class*=Room] button',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 5)
            for index in range(count):
                item = locator.nth(index)
                if item.is_visible(timeout=800):
                    item.click(timeout=800)
                    page.wait_for_timeout(500)
        except Exception:
            continue

    try:
        for _ in range(4):
            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(700)
    except Exception:
        pass


def browser_fetch(url: str, headers: Dict[str, str], source_type: str = 'ctrip', room_keyword: str = '') -> str:
    with BROWSER_LOCK:
        with sync_playwright() as playwright:
            executable_path = resolve_chromium_executable(playwright)
            browser = playwright.chromium.launch(executable_path=executable_path, headless=True)
            context = browser.new_context(
                user_agent=headers.get('User-Agent'),
                locale='zh-CN',
                extra_http_headers={k: v for k, v in headers.items() if k.lower() not in {'user-agent'}},
            )
            page = context.new_page()
            fetch_url = normalize_target_url(url, source_type)
            page.goto(fetch_url, wait_until='domcontentloaded', timeout=45000)
            try:
                page.wait_for_load_state('networkidle', timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            currency_debug = {}
            expand_dynamic_sections(page, source_type)
            room_blocks = extract_room_blocks_for_source(page, source_type, room_keyword)
            page_title = ''
            try:
                page_title = page.title()
            except Exception:
                page_title = ''
            visible_text = page.locator('body').inner_text(timeout=5000)
            room_block_text = encode_room_blocks(room_blocks)
            visible_lines = [line.strip() for line in visible_text.splitlines() if line.strip()][:30]
            joined_preview = ' | '.join(visible_lines[:12])
            lower_preview = joined_preview.lower()
            page_debug = {
                'requested_url': fetch_url,
                'final_url': page.url,
                'title': page_title,
                'visible_line_count': len(visible_lines),
                'visible_lines_preview': visible_lines[:20],
                'room_block_count': len(room_blocks),
                'signals': detect_page_signals(source_type, page.url, page_title, lower_preview, len(room_blocks)),
                'currency_debug': currency_debug,
                'current_currency': (currency_debug.get('after_currency') or currency_debug.get('before_currency') or ''),
            }
            page_debug_text = encode_page_debug(page_debug)
            content = page_debug_text + ('\n' if page_debug_text else '') + room_block_text + ('\n' if room_block_text else '') + visible_text + '\n\n<!--RAW_HTML-->\n' + page.content()
            context.close()
            browser.close()
            return content


def candidate_patterns(watcher: Watcher) -> List[str]:
    patterns: List[str] = []
    if watcher.price_pattern.strip():
        patterns.append(watcher.price_pattern.strip())
    patterns.extend(DEFAULT_PATTERNS.get('ctrip', []))
    return patterns


def plausible_price_from_text(text: str) -> Optional[float]:
    candidates = re.findall(r'[¥￥]\s*([0-9][0-9,]*(?:\.\d+)?)', text)
    numbers = [float(value.replace(',', '')) for value in candidates if 50 <= float(value.replace(',', '')) <= 50000]
    if not numbers:
        return None
    return min(numbers)


CURRENCY_ALIASES = {
    '¥': 'CNY', '￥': 'CNY', 'CNY': 'CNY', 'RMB': 'CNY',
    'S$': 'SGD', 'SGD': 'SGD',
    '$': 'USD', 'US$': 'USD', 'USD': 'USD',
}

CURRENCY_FALLBACK_RATES = {
    ('SGD', 'CNY'): 5.129,
    ('USD', 'CNY'): 7.20,
}


def extract_currency_price_candidates(text: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    pattern = re.compile(r'(S\$|US\$|SGD|USD|CNY|RMB|[¥￥$])\s*([0-9][0-9,]{2,}(?:\.\d{1,2})?)', re.I)
    for match in pattern.finditer(text):
        raw_currency = match.group(1).upper()
        currency = CURRENCY_ALIASES.get(match.group(1), CURRENCY_ALIASES.get(raw_currency, raw_currency))
        amount = float(match.group(2).replace(',', ''))
        if not (50 <= amount <= 100000):
            continue
        before = text[max(0, match.start() - 12): match.start()]
        after = text[match.end(): min(len(text), match.end() + 8)]
        near = text[max(0, match.start() - 20): min(len(text), match.end() + 20)]
        if '/月' in after or '每月' in after or '月付' in after:
            continue
        if '返现奖励' in before or 'cashback' in before.lower():
            continue
        results.append({'currency': currency, 'display_currency': match.group(1).upper(), 'amount': amount, 'raw': match.group(0), 'context': near, 'pos': match.start()})
    return results


def maybe_convert_price(amount: float, from_currency: str, to_currency: str) -> Optional[float]:
    if from_currency == to_currency:
        return amount
    rate = CURRENCY_FALLBACK_RATES.get((from_currency, to_currency))
    if rate is None:
        return None
    return round(amount * rate, 2)


def extract_price(text: str, patterns: List[str]) -> float:
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if not match:
            continue
        raw = match.group(1) if match.groups() else match.group(0)
        normalized = re.sub(r'[^\d.]', '', raw)
        if normalized:
            value = float(normalized)
            if 20 <= value <= 100000:
                return value
    fallback = plausible_price_from_text(text)
    if fallback is not None:
        return fallback
    raise ValueError('No price could be extracted. The page may require a valid session/cookie, or the page structure may have changed.')


def matched_room_blocks(text: str, watcher: Watcher) -> List[Dict[str, Any]]:
    keyword = watcher.room_type_keyword.strip()
    if not keyword:
        return []
    block_items = parse_room_blocks(text)
    if not block_items:
        return []

    preferred_tags = [item.strip().lower() for item in watcher.meta_tags() if item.strip()]
    matched: List[Dict[str, Any]] = []
    for item in block_items:
        haystack = ' '.join([
            str(item.get('room_name', '')),
            str(item.get('raw_text', '')),
            ' '.join(item.get('tags', [])),
        ])
        if not room_keyword_matches(haystack, keyword):
            continue
        score = 0
        room_name = compact_room_text(str(item.get('room_name', '')))
        raw_text = compact_room_text(str(item.get('raw_text', '')))
        keyword_text = compact_room_text(keyword)
        explicit_parts = explicit_room_keyword_parts(keyword)
        if keyword_text in room_name:
            score += 8
        if keyword_text in raw_text:
            score += 5
        if explicit_parts and len(explicit_parts) >= 2 and all(part in room_name for part in explicit_parts):
            score += 6
        tags = [str(tag).strip().lower() for tag in item.get('tags', []) if str(tag).strip()]
        if preferred_tags:
            for preferred in preferred_tags:
                if preferred in tags or preferred in raw_text:
                    score += 6
        price = float(item.get('price') or 0)
        if bool(item.get('target_match')):
            score += 100
        min_expected = float(watcher.min_expected_price or 0)
        if min_expected and price < min_expected:
            score -= 100
        if price >= 500:
            score += 2
        elif price < 100:
            score -= 8
        enriched = dict(item)
        enriched['match_score'] = score
        matched.append(enriched)
    matched.sort(key=lambda item: (-int(item.get('match_score', 0)), -float(item.get('price') or 0)))
    return matched


def keyword_variants(keyword: str) -> List[str]:
    variants: List[str] = []
    if keyword:
        variants.append(keyword)

    parts = [part for part in re.split(r'[\s/|（）()\-]+', keyword) if len(part) >= 2]
    variants.extend(parts)

    chinese = re.sub(r'[^一-鿿A-Za-z0-9]', '', keyword)
    if len(chinese) >= 4:
        for size in range(min(4, len(chinese)), 1, -1):
            for index in range(0, len(chinese) - size + 1):
                piece = chinese[index:index + size]
                if len(piece) >= 2:
                    variants.append(piece)

    seen = set()
    ordered = []
    for item in variants:
        item = item.strip()
        if len(item) >= 2 and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def compact_room_text(value: str) -> str:
    return re.sub(r'\s+', '', normalize_room_name(value)).lower()


def explicit_room_keyword_parts(keyword: str) -> List[str]:
    parts: List[str] = []
    for part in re.split(r'[\s/|（）()\-]+', keyword or ''):
        compact = compact_room_text(part)
        if len(compact) >= 2:
            parts.append(compact)
    ordered: List[str] = []
    seen = set()
    for item in parts:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def room_keyword_matches(haystack: str, keyword: str) -> bool:
    haystack_text = compact_room_text(haystack)
    keyword_text = compact_room_text(keyword)
    if not keyword_text or not haystack_text:
        return False
    if keyword_text in haystack_text:
        return True
    explicit_parts = explicit_room_keyword_parts(keyword)
    return bool(explicit_parts) and len(explicit_parts) >= 2 and all(part in haystack_text for part in explicit_parts)


def room_scoped_texts(text: str, room_keyword: str, watcher: Optional[Watcher] = None) -> List[str]:
    keyword = room_keyword.strip()
    if not keyword:
        return [text]

    block_items = parse_room_blocks(text)
    if block_items:
        matched_blocks = []
        for item in block_items:
            haystack = ' '.join([item.get('room_name', ''), item.get('raw_text', ''), ' '.join(item.get('tags', []))])
            if room_keyword_matches(haystack, keyword):
                matched_blocks.append(item.get('raw_text', ''))
        if matched_blocks:
            return matched_blocks

    snippets: List[str] = []
    patterns = [re.escape(keyword)] if keyword else []
    search_text = search_text_only(text)

    seen_ranges = set()
    for pattern in patterns:
        for match in re.finditer(pattern, search_text, re.I):
            start = max(0, match.start() - ROOM_SNIPPET_RADIUS)
            end = min(len(search_text), match.end() + ROOM_SNIPPET_RADIUS)
            marker = (start, end)
            if marker in seen_ranges:
                continue
            seen_ranges.add(marker)
            snippets.append(search_text[start:end])
            if len(snippets) >= 12:
                return snippets
    if snippets:
        return snippets

    suggestions = room_candidate_summaries(text, 6)
    variants = keyword_variants(keyword)
    variant_text = ' / '.join(variants[:8])
    page_debug = parse_page_debug(text)
    final_url = str(page_debug.get('final_url') or '')
    signals = page_debug.get('signals') or {}
    if signals.get('login_like') or ('passport.ctrip.com' in final_url and (watcher is None or watcher.source_type == 'ctrip')):
        source_label = 'Ctrip'
        error = ValueError(
            f'The fetched page is not a hotel room page. It is the {source_label} login page instead: {final_url or "(unknown URL)"}.'
            f' Start the dedicated {source_label} login flow, complete sign-in in the browser, click “I Finished Login”, and try again.'
        )
        setattr(error, 'debug_payload', build_room_debug_payload(text, keyword, watcher))
        raise error
    if watcher is not None and watcher.source_type == 'ctrip' and signals.get('booking_like'):
        error = ValueError(
            f'The flow landed on a Ctrip booking page instead of a room page: {final_url or "(unknown URL)"}.'
            ' Try “Check Now” again. If the error still happens, inspect the diagnostics payload.'
        )
        setattr(error, 'debug_payload', build_room_debug_payload(text, keyword, watcher))
        raise error
    if suggestions:
        error = ValueError(
            f"Room keyword not found: {keyword}. Attempted keyword variants: {variant_text}. "
            f"Example room candidates found on the page: {'; '.join(suggestions)}. "
            "Suggestions: 1) confirm whether the room type is sold out or no longer listed; 2) if it is still available, use the full room name from the page and try again."
        )
        setattr(error, 'debug_payload', build_room_debug_payload(text, keyword, watcher))
        raise error
    error = ValueError(
        f"Room keyword not found: {keyword}. Attempted keyword variants: {variant_text}. "
        "No clear room candidates were extracted from the current page. Try scrolling the page, refreshing the session cookie, or using a more specific full room name."
    )
    setattr(error, 'debug_payload', build_room_debug_payload(text, keyword, watcher))
    raise error


def normalize_room_name(name: str) -> str:
    cleaned = re.sub(r'\s+', ' ', name).strip(' -:\n\t')
    cleaned = re.sub(r'[{}<>\[\]#@|]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def visible_text_only(text: str) -> str:
    marker = '\n\n<!--RAW_HTML-->\n'
    return text.split(marker, 1)[0] if marker in text else text


def search_text_only(text: str) -> str:
    visible = visible_text_only(text)
    lines = []
    for line in visible.splitlines():
        if line.startswith('PAGE_DEBUG||') or line.startswith('ROOM_BLOCK||'):
            continue
        lines.append(line)
    return '\n'.join(lines)

def looks_noisy_room_name(name: str) -> bool:
    cleaned = normalize_room_name(name)
    if not cleaned:
        return True
    if len(cleaned) > 80:
        return True
    bad_patterns = [
        r'^ROOM_BLOCK\\b',
        r'^选择房间\\b',
        r'^房间\\b$',
        r'^概览\\b',
        r'^展示额外\\d+个房型价格',
        r'photo gallery',
        r'Go to main content',
        r'房间详情',
        r'房型摘要',
        r'可住人数',
        r'^\\d+张',
        r'^\\d+\\s+\\d+张',
        r'携程旅行网',
        r'热卖',
        r'仅剩\d+间',
        r'酒店',
        r'度假村',
        r'度假酒店',
        r'\(.*\)',
    ]
    return any(re.search(pattern, cleaned, re.I) for pattern in bad_patterns)


def looks_garbled(line: str) -> bool:
    if not line:
        return True
    if len(line) > 80:
        return True
    weird = sum(1 for ch in line if ord(ch) < 32 and ch not in '\t\n\r')
    if weird:
        return True
    symbol_count = sum(1 for ch in line if ch in '{}<>[]|=_#@/\\')
    if symbol_count >= max(4, len(line) // 3):
        return True
    if re.search(r'\b(function|return|const|var|undefined|null|true|false)\b', line, re.I):
        return True
    return False


def extract_room_candidates(text: str) -> List[Dict[str, Any]]:
    block_items = parse_room_blocks(text)
    candidates: List[Dict[str, Any]] = []
    seen = set()
    if block_items:
        room_hint = re.compile(r'(房|床|套房|别墅|Villa|Suite|Twin|King|Deluxe|泳池|水疗|Spa|Pool)', re.I)
        for item in block_items:
            room_name = normalize_room_name(str(item.get('room_name', '')))
            if looks_noisy_room_name(room_name):
                continue
            if not room_hint.search(room_name):
                continue
            price = float(item.get('price') or 0)
            if not (500 <= price <= 100000):
                continue
            tags = [normalize_room_name(str(tag)) for tag in (item.get('tags', []) or []) if normalize_room_name(str(tag))]
            key = (room_name.lower(), round(price, 2), tuple(tags))
            if key in seen:
                continue
            seen.add(key)
            candidates.append({'room_name': room_name, 'price': price, 'tags': tags})
        if candidates:
            candidates.sort(key=lambda item: item['price'])
            return candidates[:ROOM_PREVIEW_LIMIT]

    text = visible_text_only(text)
    text = re.sub(r'(?i)(房型总览|酒店介绍|住客点评|周边信息)', '\n', text)
    lines = [normalize_room_name(line) for line in text.splitlines()]
    lines = [line for line in lines if line and not looks_garbled(line) and not looks_noisy_room_name(line)]
    candidates = []
    room_hint = re.compile(r'(房|床|双早|大床|双床|套房|景|Deluxe|King|Twin|Suite|Room|Breakfast|Villa)', re.I)
    price_hint = re.compile(r'([¥￥]\s*[0-9][0-9,]*(?:\.\d+)?)|(\d{3,6}(?:\.\d{1,2})?)')
    breakfast_hint = re.compile(r'(含早|双早|单早|早餐|Breakfast|breakfast)', re.I)
    cancel_hint = re.compile(r'(免费取消|不可取消|不可退款|免费退|No refund|Free cancellation)', re.I)
    pay_hint = re.compile(r'(到店付|在线付|预付|Pay at property|Prepay)', re.I)
    for index, line in enumerate(lines):
        if not room_hint.search(line):
            continue
        window = lines[max(0, index - 1):index + 6]
        block = ' '.join(window)
        match = price_hint.search(block)
        if not match:
            continue
        value_text = match.group(1) or match.group(2)
        value = float(re.sub(r'[^\d.,]', '', value_text).replace(',', ''))
        if not (500 <= value <= 100000):
            continue
        room_name = line[:80]
        tags = []
        breakfast_match = breakfast_hint.search(block)
        cancel_match = cancel_hint.search(block)
        pay_match = pay_hint.search(block)
        if breakfast_match:
            tags.append(breakfast_match.group(1))
        if cancel_match:
            tags.append(cancel_match.group(1))
        if pay_match:
            tags.append(pay_match.group(1))
        key = (room_name.lower(), round(value, 2), tuple(tags))
        if key in seen:
            continue
        seen.add(key)
        candidates.append({'room_name': room_name, 'price': value, 'tags': tags})
        if len(candidates) >= ROOM_PREVIEW_LIMIT:
            break
    candidates.sort(key=lambda item: item['price'])
    return candidates


def extract_price_for_watcher(text: str, watcher: Watcher) -> float:
    min_expected = float(watcher.min_expected_price or 0)
    page_debug = parse_page_debug(text)
    current_currency = str(page_debug.get('current_currency') or watcher.currency or '').upper()
    matched_blocks = matched_room_blocks(text, watcher)
    filtered_out_prices: List[float] = []
    if matched_blocks:
        for block in matched_blocks:
            price = float(block.get('price') or 0)
            if min_expected and price < min_expected:
                filtered_out_prices.append(price)
                continue
            if 20 <= price <= 100000:
                return price

    snippets = room_scoped_texts(text, watcher.room_type_keyword, watcher)
    patterns = candidate_patterns(watcher)
    last_error: Optional[Exception] = None
    for snippet in snippets:
        try:
            value = extract_price(snippet, patterns)
            if min_expected and value < min_expected:
                filtered_out_prices.append(value)
                raise ValueError(f'The extracted price {value:.2f} is below the configured minimum reasonable price {min_expected:.2f}')
            return value
        except Exception as exc:
            last_error = exc
    if watcher.room_type_keyword.strip():
        if filtered_out_prices:
            samples = ' / '.join(f'{value:.2f}' for value in filtered_out_prices[:6])
            error = ValueError(
                f'The room keyword was matched, but all extracted prices are below the configured minimum reasonable price for: {watcher.room_type_keyword}. '
                f'The minimum reasonable price is {min_expected:.2f}, and the extracted candidate prices were: {samples}. '
                'You can lower the minimum reasonable price or further refine room matching.'
            )
            setattr(error, 'debug_payload', build_room_debug_payload(text, watcher.room_type_keyword, watcher))
            raise error from last_error
        error = ValueError(f'The room keyword was matched, but no corresponding price was extracted: {watcher.room_type_keyword}')
        setattr(error, 'debug_payload', build_room_debug_payload(text, watcher.room_type_keyword, watcher))
        raise error from last_error
    if last_error:
        raise last_error
    raise ValueError('No price was extracted')


def should_notify(watcher: Watcher, current_price: float) -> bool:
    threshold_hit = watcher.threshold_price is not None and current_price <= watcher.threshold_price
    drop_hit = watcher.last_price is not None and current_price < watcher.last_price
    first_hit = watcher.last_price is None and threshold_hit
    already_notified_same_price = watcher.last_notified_price is not None and current_price >= watcher.last_notified_price
    return (threshold_hit or drop_hit or first_hit) and not already_notified_same_price


def send_feishu_webhook(webhook_url: str, content: str) -> None:
    payload = json.dumps({'msg_type': 'text', 'content': {'text': content}}).encode('utf-8')
    request = urllib.request.Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    with http_open(request, timeout=15) as response:
        response.read()


def send_wechat_webhook(webhook_url: str, content: str) -> None:
    payload = json.dumps({'msgtype': 'text', 'text': {'content': content}}).encode('utf-8')
    request = urllib.request.Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    with http_open(request, timeout=15) as response:
        response.read()


def send_notification(watcher: Watcher, current_price: float, is_test: bool = False) -> None:
    lines = [
        'Hotel Price Alert Test' if is_test else 'Hotel Price Alert',
        'Platform: Ctrip',
        f'Watcher: {watcher.name}',
        f'Hotel: {watcher.hotel_name}',
    ]
    if watcher.room_type_keyword.strip():
        lines.append(f'Room: {watcher.room_type_keyword}')
    if watcher.room_type_meta.strip():
        lines.append(f'Room tags: {watcher.room_type_meta}')
    lines.append(f'Current price: {watcher.currency} {current_price:.2f}')
    if watcher.last_price is not None and not is_test:
        lines.append(f'Previous price: {watcher.currency} {watcher.last_price:.2f}')
    if watcher.threshold_price is not None:
        lines.append(f'Target price: {watcher.currency} {watcher.threshold_price:.2f}')
    if watcher.min_expected_price is not None:
        lines.append(f'Minimum reasonable price: {watcher.currency} {watcher.min_expected_price:.2f}')
    lines.append(f'Link: {watcher.target_url}')
    content = '\n'.join(lines)
    if watcher.notify_type == 'wechat':
        send_wechat_webhook(watcher.notify_target, content)
    else:
        send_feishu_webhook(watcher.notify_target, content)
