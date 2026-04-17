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
        title = '酒店价格提醒测试'
    elif reason == 'threshold_hit':
        title = '✅ 已达到目标价格'
    else:
        title = '📉 价格下降提醒（未达目标价）'

    lines = [
        title,
        '平台: 携程',
        f'监控任务: {watcher.name}',
        f'酒店: {watcher.hotel_name}',
    ]
    if watcher.room_type_keyword.strip():
        lines.append(f'房型: {watcher.room_type_keyword}')
    if watcher.room_type_meta.strip():
        lines.append(f'房型标签: {watcher.room_type_meta}')
    lines.append(f'当前价格: {watcher.currency} {current_price:.2f}')
    if watcher.last_price is not None and not is_test:
        lines.append(f'上次价格: {watcher.currency} {watcher.last_price:.2f}')
    if watcher.threshold_price is not None:
        lines.append(f'目标价格: {watcher.currency} {watcher.threshold_price:.2f}')
    if watcher.min_expected_price is not None:
        lines.append(f'最低合理价格: {watcher.currency} {watcher.min_expected_price:.2f}')
    if not is_test:
        if reason == 'threshold_hit':
            lines.append('通知类型: 已达到你的预期价格，请优先关注')
        else:
            lines.append('通知类型: 价格比上次更低，但还未达到你的预期价格')
    lines.append(f'链接: {watcher.target_url}')
    return '\n'.join(lines)


def build_feishu_payload(watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> dict:
    if is_test:
        return {
            'msg_type': 'text',
            'content': {'text': build_notification_text(watcher, current_price, 'price_drop', is_test=True)},
        }

    if reason == 'threshold_hit':
        header_title = '✅ 已达到目标价格'
        header_template = 'red'
        highlight_label = '建议立即关注'
        status_text = '当前价格已达到或低于你的目标价'
    else:
        header_title = '📉 价格下降提醒'
        header_template = 'orange'
        highlight_label = '价格有下降'
        status_text = '当前价格比上次更低，但尚未达到目标价'

    fields = [
        {'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**当前价格**\n{watcher.currency} {current_price:.2f}'}},
        {'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**目标价格**\n{watcher.currency} {watcher.threshold_price:.2f}' if watcher.threshold_price is not None else '**目标价格**\n未设置'}},
    ]
    if watcher.last_price is not None:
        fields.append({'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**上次价格**\n{watcher.currency} {watcher.last_price:.2f}'}})
    if watcher.room_type_keyword.strip():
        fields.append({'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**房型关键词**\n{watcher.room_type_keyword}'}})

    elements = [
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**{highlight_label}**\n{status_text}'}},
        {'tag': 'div', 'fields': fields},
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**监控任务**\n{watcher.name}\n**酒店**\n{watcher.hotel_name}'}},
    ]
    if watcher.room_type_meta.strip():
        elements.append({'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**房型标签**\n{watcher.room_type_meta}'}})
    if watcher.min_expected_price is not None:
        elements.append({'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**最低合理价格**\n{watcher.currency} {watcher.min_expected_price:.2f}'}})
    elements.extend([
        {'tag': 'hr'},
        {'tag': 'action', 'actions': [{'tag': 'button', 'text': {'tag': 'plain_text', 'content': '打开酒店链接'}, 'type': 'primary', 'url': watcher.target_url}]},
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
    threshold_text = f"{watcher.currency} {watcher.threshold_price:.2f}" if watcher.threshold_price is not None else '未设置'
    payload = {
        'msg_type': 'text',
        'content': {
            'text': (
                '<at user_id="all">所有人</at> 已达到目标价格！\n'
                f'监控任务: {watcher.name}\n'
                f'当前价格: {watcher.currency} {current_price:.2f}\n'
                f'目标价格: {threshold_text}\n'
                f'链接: {watcher.target_url}'
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
