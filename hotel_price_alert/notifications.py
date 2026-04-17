import json
import urllib.request
from typing import Literal

from .browser import http_open

NotificationReason = Literal['threshold_hit', 'price_drop']


def notification_reason(watcher, current_price: float) -> NotificationReason | None:
    threshold_hit = watcher.threshold_price is not None and current_price <= watcher.threshold_price
    drop_hit = watcher.last_price is not None and current_price < watcher.last_price
    first_hit = watcher.last_price is None and threshold_hit
    already_notified_same_price = watcher.last_notified_price is not None and current_price >= watcher.last_notified_price
    if already_notified_same_price:
        return None
    if threshold_hit or first_hit:
        return 'threshold_hit'
    if drop_hit:
        return 'price_drop'
    return None


def should_notify(watcher, current_price: float) -> bool:
    return notification_reason(watcher, current_price) is not None


def build_notification_text(watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> str:
    if is_test:
        title = 'Hotel Price Alert Test'
    elif reason == 'threshold_hit':
        title = '✅ Target price reached'
    else:
        title = '📉 Price drop alert (target not reached yet)'

    lines = [
        title,
        'Platform: Ctrip',
        f'Watcher: {watcher.name}',
        f'Hotel: {watcher.hotel_name}',
    ]
    if watcher.room_type_keyword.strip():
        lines.append(f'Room: {watcher.room_type_keyword}')
    if watcher.room_type_meta.strip():
        lines.append(f'Room notes: {watcher.room_type_meta}')
    lines.append(f'Current price: {watcher.currency} {current_price:.2f}')
    if watcher.last_price is not None and not is_test:
        lines.append(f'Last price: {watcher.currency} {watcher.last_price:.2f}')
    if watcher.threshold_price is not None:
        lines.append(f'Target price: {watcher.currency} {watcher.threshold_price:.2f}')
    if watcher.min_expected_price is not None:
        lines.append(f'Minimum reasonable price: {watcher.currency} {watcher.min_expected_price:.2f}')
    if not is_test:
        if reason == 'threshold_hit':
            lines.append('Notification type: target price reached. Please review it promptly.')
        else:
            lines.append('Notification type: price dropped below the previous check, but the target price has not been reached yet.')
    lines.append(f'URL: {watcher.target_url}')
    return '\n'.join(lines)


def build_feishu_payload(watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> dict:
    if is_test:
        return {
            'msg_type': 'text',
            'content': {'text': build_notification_text(watcher, current_price, 'price_drop', is_test=True)},
        }

    if reason == 'threshold_hit':
        header_title = '✅ Target price reached'
        header_template = 'red'
        highlight_label = 'Worth immediate attention'
        status_text = 'The current price is at or below your target price'
    else:
        header_title = '📉 Price drop alert'
        header_template = 'orange'
        highlight_label = 'Price dropped'
        status_text = 'The current price is lower than the previous one, but it has not reached the target price yet'

    fields = [
        {'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Current Price**\n{watcher.currency} {current_price:.2f}'}},
        {'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Target Price**\n{watcher.currency} {watcher.threshold_price:.2f}' if watcher.threshold_price is not None else '**Target Price**\nNot set'}},
    ]
    if watcher.last_price is not None:
        fields.append({'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Last Price**\n{watcher.currency} {watcher.last_price:.2f}'}})
    if watcher.room_type_keyword.strip():
        fields.append({'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Room Keyword**\n{watcher.room_type_keyword}'}})

    elements = [
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**{highlight_label}**\n{status_text}'}},
        {'tag': 'div', 'fields': fields},
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**Watcher**\n{watcher.name}\n**Hotel**\n{watcher.hotel_name}'}},
    ]
    if watcher.room_type_meta.strip():
        elements.append({'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**Room Notes**\n{watcher.room_type_meta}'}})
    if watcher.min_expected_price is not None:
        elements.append({'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**Minimum Reasonable Price**\n{watcher.currency} {watcher.min_expected_price:.2f}'}})
    elements.extend([
        {'tag': 'hr'},
        {'tag': 'action', 'actions': [{'tag': 'button', 'text': {'tag': 'plain_text', 'content': 'Open hotel URL'}, 'type': 'primary', 'url': watcher.target_url}]},
    ])

    return {
        'msg_type': 'interactive',
        'card': {
            'header': {
                'template': header_template,
                'title': {'tag': 'plain_text', 'content': header_title},
            },
            'elements': elements,
        },
    }


def send_feishu_webhook(webhook_url: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(webhook_url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with http_open(request, timeout=15) as response:
        response.read()


def send_feishu_at_all(webhook_url: str, watcher, current_price: float) -> None:
    threshold_text = f"{watcher.currency} {watcher.threshold_price:.2f}" if watcher.threshold_price is not None else 'Not set'
    payload = {
        'msg_type': 'text',
        'content': {
            'text': (
                '<at user_id="all">all</at> Target price reached!\n'
                f'Watcher: {watcher.name}\n'
                f'Current price: {watcher.currency} {current_price:.2f}\n'
                f'Target price: {threshold_text}\n'
                f'URL: {watcher.target_url}'
            )
        },
    }
    send_feishu_webhook(webhook_url, payload)


def send_wechat_webhook(webhook_url: str, content: str) -> None:
    payload = json.dumps({'msgtype': 'text', 'text': {'content': content}}).encode('utf-8')
    request = urllib.request.Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    with http_open(request, timeout=15) as response:
        response.read()


def send_notification(watcher, current_price: float, is_test: bool = False, reason: NotificationReason | None = None) -> None:
    actual_reason = 'price_drop' if is_test else (reason or notification_reason(watcher, current_price) or 'price_drop')
    if watcher.notify_type == 'wechat':
        send_wechat_webhook(watcher.notify_target, build_notification_text(watcher, current_price, actual_reason, is_test=is_test))
    else:
        if not is_test and actual_reason == 'threshold_hit':
            send_feishu_at_all(watcher.notify_target, watcher, current_price)
        send_feishu_webhook(watcher.notify_target, build_feishu_payload(watcher, current_price, actual_reason, is_test=is_test))
