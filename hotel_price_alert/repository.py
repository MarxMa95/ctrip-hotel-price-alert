import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import DB_PATH, DEFAULT_CHROME_PROFILE, DEFAULT_POLL_INTERVAL_MINUTES, FIXED_SOURCE_TYPE, PRICE_HISTORY_LIMIT
from .legacy_app import CREATE_HISTORY_SQL, CREATE_WATCHERS_SQL
from .utils import merge_cookie_into_headers, normalize_headers, utc8_day_range, utc_now

CREATE_NOTIFICATION_EVENTS_SQL = '''
CREATE TABLE IF NOT EXISTS notification_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watcher_id INTEGER NOT NULL,
    price REAL NOT NULL,
    reason TEXT NOT NULL,
    notified_at TEXT NOT NULL
);
'''


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
    quiet_hours_start: str
    quiet_hours_end: str
    daily_notification_limit: int
    notify_only_target_hit: int
    min_price_drop_amount: Optional[float]
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
    all_time_low_price: Optional[float]
    all_time_low_at: Optional[str]
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
        data.setdefault('quiet_hours_start', '')
        data.setdefault('quiet_hours_end', '')
        data.setdefault('daily_notification_limit', 0)
        data.setdefault('notify_only_target_hit', 0)
        data.setdefault('min_price_drop_amount', None)
        data.setdefault('poll_interval_minutes', DEFAULT_POLL_INTERVAL_MINUTES)
        data.setdefault('request_headers', '{}')
        data.setdefault('use_local_chrome_profile', 0)
        data.setdefault('chrome_profile_name', DEFAULT_CHROME_PROFILE)
        data.setdefault('use_app_session_profile', 0)
        data.setdefault('use_browser', 1)
        data.setdefault('last_error', None)
        data.setdefault('last_price_note', None)
        data.setdefault('all_time_low_price', None)
        data.setdefault('all_time_low_at', None)
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
        conn.execute(CREATE_NOTIFICATION_EVENTS_SQL)
        ensure_column(conn, 'room_type_keyword', "room_type_keyword TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'room_type_meta', "room_type_meta TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'price_pattern', "price_pattern TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'currency', "currency TEXT NOT NULL DEFAULT 'CNY'")
        ensure_column(conn, 'notify_type', "notify_type TEXT NOT NULL DEFAULT 'feishu'")
        ensure_column(conn, 'min_expected_price', 'min_expected_price REAL')
        ensure_column(conn, 'quiet_hours_start', "quiet_hours_start TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'quiet_hours_end', "quiet_hours_end TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, 'daily_notification_limit', 'daily_notification_limit INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'notify_only_target_hit', 'notify_only_target_hit INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'min_price_drop_amount', 'min_price_drop_amount REAL')
        ensure_column(conn, 'poll_interval_minutes', 'poll_interval_minutes INTEGER NOT NULL DEFAULT 5')
        ensure_column(conn, 'request_headers', "request_headers TEXT NOT NULL DEFAULT '{}'")
        ensure_column(conn, 'use_local_chrome_profile', 'use_local_chrome_profile INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'chrome_profile_name', "chrome_profile_name TEXT NOT NULL DEFAULT 'Default'")
        ensure_column(conn, 'use_app_session_profile', 'use_app_session_profile INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'use_browser', 'use_browser INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'last_error', 'last_error TEXT')
        ensure_column(conn, 'last_price_note', 'last_price_note TEXT')
        ensure_column(conn, 'all_time_low_price', 'all_time_low_price REAL')
        ensure_column(conn, 'all_time_low_at', 'all_time_low_at TEXT')
        conn.commit()
        backfill_all_time_low_from_current_history()


def list_watchers() -> List[Watcher]:
    with db_connection() as conn:
        rows = conn.execute('SELECT * FROM watchers WHERE source_type = ? ORDER BY id DESC', (FIXED_SOURCE_TYPE,)).fetchall()
    return [Watcher.from_row(row) for row in rows]


def find_watcher(watcher_id: int) -> Optional[Watcher]:
    with db_connection() as conn:
        row = conn.execute('SELECT * FROM watchers WHERE id = ? AND source_type = ?', (watcher_id, FIXED_SOURCE_TYPE)).fetchone()
    return Watcher.from_row(row) if row else None


def list_history(watcher_id: int, limit: Optional[int] = PRICE_HISTORY_LIMIT) -> List[Dict[str, Any]]:
    with db_connection() as conn:
        if limit is None or int(limit) <= 0:
            rows = conn.execute(
                'SELECT price, checked_at FROM price_history WHERE watcher_id = ? ORDER BY id ASC',
                (watcher_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT price, checked_at FROM price_history WHERE watcher_id = ? ORDER BY id DESC LIMIT ?',
                (watcher_id, limit),
            ).fetchall()
            rows = list(reversed(rows))
    return [{'price': row['price'], 'checked_at': row['checked_at']} for row in rows]


def list_notification_events(watcher_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    with db_connection() as conn:
        if limit is None or int(limit) <= 0:
            rows = conn.execute(
                'SELECT price, reason, notified_at FROM notification_events WHERE watcher_id = ? ORDER BY id ASC',
                (watcher_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT price, reason, notified_at FROM notification_events WHERE watcher_id = ? ORDER BY id DESC LIMIT ?',
                (watcher_id, limit),
            ).fetchall()
            rows = list(reversed(rows))
    return [{'price': row['price'], 'reason': row['reason'], 'notified_at': row['notified_at']} for row in rows]


def count_notification_events_today(watcher_id: int) -> int:
    start_at, end_at = utc8_day_range()
    with db_connection() as conn:
        row = conn.execute(
            'SELECT COUNT(1) AS cnt FROM notification_events WHERE watcher_id = ? AND notified_at >= ? AND notified_at < ?',
            (watcher_id, start_at, end_at),
        ).fetchone()
    return int(row['cnt'] if row else 0)


def append_notification_event(watcher_id: int, price: float, reason: str, notified_at: str) -> None:
    with db_connection() as conn:
        conn.execute(
            'INSERT INTO notification_events (watcher_id, price, reason, notified_at) VALUES (?, ?, ?, ?)',
            (watcher_id, price, reason, notified_at),
        )
        conn.commit()


def append_price_history(watcher_id: int, price: float, checked_at: str) -> None:
    with db_connection() as conn:
        conn.execute('INSERT INTO price_history (watcher_id, price, checked_at) VALUES (?, ?, ?)', (watcher_id, price, checked_at))
        conn.commit()


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
                room_type_meta, price_pattern, currency, notify_type, notify_target, threshold_price, min_expected_price, quiet_hours_start,
                quiet_hours_end, daily_notification_limit, notify_only_target_hit, min_price_drop_amount, poll_interval_minutes,
                request_headers, use_local_chrome_profile, chrome_profile_name, use_app_session_profile, use_browser, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                payload['name'].strip(), payload['hotel_name'].strip(), source_type, payload['target_url'].strip(),
                payload.get('room_type_keyword', '').strip(), payload.get('room_type_meta', '').strip(),
                payload.get('price_pattern', '').strip(), payload.get('currency', 'CNY').strip() or 'CNY',
                payload.get('notify_type', 'feishu').strip() or 'feishu', payload['notify_target'].strip(),
                payload.get('threshold_price'), payload.get('min_expected_price'),
                payload.get('quiet_hours_start', '').strip(), payload.get('quiet_hours_end', '').strip(),
                int(payload.get('daily_notification_limit') or 0),
                1 if bool(payload.get('notify_only_target_hit')) else 0,
                payload.get('min_price_drop_amount'),
                int(payload.get('poll_interval_minutes', DEFAULT_POLL_INTERVAL_MINUTES)), request_headers,
                1 if bool(payload.get('use_local_chrome_profile')) else 0,
                str(payload.get('chrome_profile_name') or DEFAULT_CHROME_PROFILE).strip() or DEFAULT_CHROME_PROFILE,
                1 if bool(payload.get('use_app_session_profile')) else 0,
                1 if bool(payload.get('use_browser', True)) else 0,
                now, now,
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
                threshold_price = ?, min_expected_price = ?, quiet_hours_start = ?, quiet_hours_end = ?, daily_notification_limit = ?,
                notify_only_target_hit = ?, min_price_drop_amount = ?, poll_interval_minutes = ?, request_headers = ?,
                use_local_chrome_profile = ?, chrome_profile_name = ?, use_app_session_profile = ?, use_browser = ?, updated_at = ?
            WHERE id = ?
            ''',
            (
                payload['name'].strip(), payload['hotel_name'].strip(), source_type, payload['target_url'].strip(),
                payload.get('room_type_keyword', '').strip(), payload.get('room_type_meta', '').strip(),
                payload.get('price_pattern', '').strip(), payload.get('currency', 'CNY').strip() or 'CNY',
                payload.get('notify_type', 'feishu').strip() or 'feishu', payload['notify_target'].strip(),
                payload.get('threshold_price'), payload.get('min_expected_price'),
                payload.get('quiet_hours_start', '').strip(), payload.get('quiet_hours_end', '').strip(),
                int(payload.get('daily_notification_limit') or 0),
                1 if bool(payload.get('notify_only_target_hit')) else 0,
                payload.get('min_price_drop_amount'),
                int(payload.get('poll_interval_minutes', DEFAULT_POLL_INTERVAL_MINUTES)), request_headers,
                1 if bool(payload.get('use_local_chrome_profile')) else 0,
                str(payload.get('chrome_profile_name') or DEFAULT_CHROME_PROFILE).strip() or DEFAULT_CHROME_PROFILE,
                1 if bool(payload.get('use_app_session_profile')) else 0,
                1 if bool(payload.get('use_browser', True)) else 0,
                now, watcher_id,
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
        conn.execute('DELETE FROM notification_events WHERE watcher_id = ?', (watcher_id,))
        conn.execute('DELETE FROM watchers WHERE id = ?', (watcher_id,))
        conn.commit()


def backfill_all_time_low_from_current_history() -> None:
    with db_connection() as conn:
        watcher_rows = conn.execute('SELECT id, last_price, last_notified_price, all_time_low_price FROM watchers').fetchall()
        for row in watcher_rows:
            if row['all_time_low_price'] is not None:
                continue
            history_row = conn.execute(
                'SELECT price, checked_at FROM price_history WHERE watcher_id = ? ORDER BY price ASC, checked_at DESC LIMIT 1',
                (row['id'],),
            ).fetchone()
            candidates = []
            low_at = None
            if history_row is not None:
                candidates.append(float(history_row['price']))
                low_at = history_row['checked_at']
            if row['last_price'] is not None:
                candidates.append(float(row['last_price']))
            if row['last_notified_price'] is not None:
                candidates.append(float(row['last_notified_price']))
            if not candidates:
                continue
            low_price = min(candidates)
            conn.execute(
                'UPDATE watchers SET all_time_low_price = ?, all_time_low_at = coalesce(all_time_low_at, ?) WHERE id = ?',
                (low_price, low_at, row['id']),
            )
        conn.commit()


def update_check_result(watcher_id: int, price: Optional[float], should_notify: bool, error: Optional[str] = None, price_note: Optional[str] = None) -> None:
    now = utc_now()
    with db_connection() as conn:
        current_row = conn.execute(
            'SELECT all_time_low_price, all_time_low_at FROM watchers WHERE id = ?',
            (watcher_id,),
        ).fetchone()
        next_low_price = current_row['all_time_low_price'] if current_row else None
        next_low_at = current_row['all_time_low_at'] if current_row else None
        if price is not None and error is None:
            if next_low_price is None or float(price) < float(next_low_price):
                next_low_price = float(price)
                next_low_at = now
            elif float(price) == float(next_low_price):
                next_low_at = now

        if should_notify and price is not None:
            conn.execute(
                'UPDATE watchers SET last_price = ?, last_checked_at = ?, last_notified_price = ?, last_error = ?, last_price_note = ?, all_time_low_price = ?, all_time_low_at = ?, updated_at = ? WHERE id = ?',
                (price, now, price, error, price_note, next_low_price, next_low_at, now, watcher_id),
            )
        else:
            conn.execute(
                'UPDATE watchers SET last_price = ?, last_checked_at = ?, last_error = ?, last_price_note = ?, all_time_low_price = ?, all_time_low_at = ?, updated_at = ? WHERE id = ?',
                (price, now, error, price_note, next_low_price, next_low_at, now, watcher_id),
            )
        conn.commit()
    if price is not None and error is None:
        append_price_history(watcher_id, price, now)
