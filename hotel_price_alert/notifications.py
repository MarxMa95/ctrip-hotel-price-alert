import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Literal

from .browser import http_open
from .repository import count_notification_events_today
from .utils import is_now_in_quiet_hours

NotificationReason = Literal['threshold_hit', 'price_drop']


@dataclass
class NotificationDecision:
    notify: bool
    reason: NotificationReason | None
    blocked_by: str | None = None
    price_drop_amount: float | None = None


def _price_drop_amount(watcher, current_price: float) -> float | None:
    if watcher.last_price is None:
        return None
    try:
        return float(watcher.last_price) - float(current_price)
    except Exception:
        return None


def notification_reason(watcher, current_price: float) -> NotificationReason | None:
    return notification_decision(watcher, current_price).reason


def notification_decision(watcher, current_price: float) -> NotificationDecision:
    threshold_hit = watcher.threshold_price is not None and current_price <= watcher.threshold_price
    drop_amount = _price_drop_amount(watcher, current_price)
    drop_hit = drop_amount is not None and drop_amount > 0
    first_hit = watcher.last_price is None and threshold_hit
    already_notified_same_price = watcher.last_notified_price is not None and current_price >= watcher.last_notified_price
    if already_notified_same_price:
        return NotificationDecision(False, None, blocked_by='already_notified_same_or_higher', price_drop_amount=drop_amount)

    if threshold_hit or first_hit:
        reason: NotificationReason | None = 'threshold_hit'
    elif drop_hit:
        reason = 'price_drop'
    else:
        reason = None

    if reason is None:
        return NotificationDecision(False, None, price_drop_amount=drop_amount)

    if bool(getattr(watcher, 'notify_only_target_hit', 0)) and reason != 'threshold_hit':
        return NotificationDecision(False, None, blocked_by='notify_only_target_hit', price_drop_amount=drop_amount)

    min_drop = getattr(watcher, 'min_price_drop_amount', None)
    if reason == 'price_drop' and min_drop is not None and drop_amount is not None and drop_amount < float(min_drop):
        return NotificationDecision(False, None, blocked_by='min_price_drop_amount', price_drop_amount=drop_amount)

    daily_limit = int(getattr(watcher, 'daily_notification_limit', 0) or 0)
    if daily_limit > 0 and count_notification_events_today(int(watcher.id)) >= daily_limit:
        return NotificationDecision(False, None, blocked_by='daily_notification_limit', price_drop_amount=drop_amount)

    if is_now_in_quiet_hours(getattr(watcher, 'quiet_hours_start', ''), getattr(watcher, 'quiet_hours_end', '')):
        return NotificationDecision(False, None, blocked_by='quiet_hours', price_drop_amount=drop_amount)

    return NotificationDecision(True, reason, price_drop_amount=drop_amount)


def should_notify(watcher, current_price: float) -> bool:
    return notification_decision(watcher, current_price).notify


def build_notification_text(watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> str:
    if is_test:
        title = 'Hotel Price Alert Test'
    elif reason == 'threshold_hit':
        title = '✅ Target Price Reached'
    else:
        title = '📉 Price Drop Alert (Target Not Yet Reached)'

    lines = [
        title,
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
    drop_amount = _price_drop_amount(watcher, current_price)
    if drop_amount and drop_amount > 0:
        lines.append(f'Drop vs previous: {watcher.currency} {drop_amount:.2f}')
    if not is_test:
        if reason == 'threshold_hit':
            lines.append('Alert type: target price reached')
        else:
            lines.append('Alert type: price is lower than before, but the target price is not reached yet')
    lines.append(f'Link: {watcher.target_url}')
    return '\n'.join(lines)


def post_json(url: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with http_open(request, timeout=15) as response:
        response.read()


def build_feishu_payload(watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> dict:
    if is_test:
        return {
            'msg_type': 'text',
            'content': {'text': build_notification_text(watcher, current_price, 'price_drop', is_test=True)},
        }

    if reason == 'threshold_hit':
        header_title = '✅ Target Price Reached'
        header_template = 'red'
        highlight_label = 'Take a look now'
        status_text = 'The current price is at or below your target price'
    else:
        header_title = '📉 Price Drop Alert'
        header_template = 'orange'
        highlight_label = 'Price dropped'
        status_text = 'The current price is lower than before, but it has not reached your target price yet'

    fields = [
        {'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Current Price**\n{watcher.currency} {current_price:.2f}'}},
        {'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Target Price**\n{watcher.currency} {watcher.threshold_price:.2f}' if watcher.threshold_price is not None else '**Target Price**\nNot set'}},
    ]
    if watcher.last_price is not None:
        fields.append({'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Previous Price**\n{watcher.currency} {watcher.last_price:.2f}'}})
    drop_amount = _price_drop_amount(watcher, current_price)
    if drop_amount and drop_amount > 0:
        fields.append({'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Price Drop**\n{watcher.currency} {drop_amount:.2f}'}})
    if watcher.room_type_keyword.strip():
        fields.append({'is_short': True, 'text': {'tag': 'lark_md', 'content': f'**Room Name**\n{watcher.room_type_keyword}'}})

    elements = [
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**{highlight_label}**\n{status_text}'}},
        {'tag': 'div', 'fields': fields},
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**Watcher**\n{watcher.name}\n**Hotel**\n{watcher.hotel_name}'}},
    ]
    if watcher.room_type_meta.strip():
        elements.append({'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**Room Tags**\n{watcher.room_type_meta}'}})
    if watcher.min_expected_price is not None:
        elements.append({'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**Minimum Reasonable Price**\n{watcher.currency} {watcher.min_expected_price:.2f}'}})
    elements.extend([
        {'tag': 'hr'},
        {'tag': 'action', 'actions': [{'tag': 'button', 'text': {'tag': 'plain_text', 'content': 'Open Hotel Page'}, 'type': 'primary', 'url': watcher.target_url}]},
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
    post_json(webhook_url, payload)


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
                f'Link: {watcher.target_url}'
            )
        },
    }
    send_feishu_webhook(webhook_url, payload)


def send_wechat_webhook(webhook_url: str, content: str) -> None:
    post_json(webhook_url, {'msgtype': 'text', 'text': {'content': content}})


def build_slack_payload(watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> dict:
    header_text = 'Hotel Price Alert Test' if is_test else ('Target Price Reached' if reason == 'threshold_hit' else 'Price Drop Alert')
    accent = '#DC2626' if reason == 'threshold_hit' and not is_test else '#F59E0B'
    summary = 'The current price is at or below your target price' if reason == 'threshold_hit' and not is_test else 'The current price is lower than before, but it has not reached your target price yet'
    fields = [
        {'type': 'mrkdwn', 'text': f'*Current Price*\n{watcher.currency} {current_price:.2f}'},
        {'type': 'mrkdwn', 'text': f'*Target Price*\n{watcher.currency} {watcher.threshold_price:.2f}' if watcher.threshold_price is not None else '*Target Price*\nNot set'},
        {'type': 'mrkdwn', 'text': f'*Watcher*\n{watcher.name}'},
        {'type': 'mrkdwn', 'text': f'*Hotel*\n{watcher.hotel_name}'},
    ]
    if watcher.room_type_keyword.strip():
        fields.append({'type': 'mrkdwn', 'text': f'*Room*\n{watcher.room_type_keyword}'})
    if watcher.last_price is not None and not is_test:
        fields.append({'type': 'mrkdwn', 'text': f'*Previous Price*\n{watcher.currency} {watcher.last_price:.2f}'})
    drop_amount = _price_drop_amount(watcher, current_price)
    facts = [summary]
    if drop_amount and drop_amount > 0:
        facts.append(f'Drop vs previous {watcher.currency} {drop_amount:.2f}')
    if watcher.min_expected_price is not None:
        facts.append(f'Minimum reasonable price {watcher.currency} {watcher.min_expected_price:.2f}')
    return {
        'text': build_notification_text(watcher, current_price, reason, is_test=is_test),
        'attachments': [{
            'color': accent,
            'blocks': [
                {'type': 'header', 'text': {'type': 'plain_text', 'text': header_text}},
                {'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(f'• {fact}' for fact in facts)}},
                {'type': 'section', 'fields': fields},
                {
                    'type': 'actions',
                    'elements': [{
                        'type': 'button',
                        'text': {'type': 'plain_text', 'text': 'Open Hotel Page'},
                        'style': 'primary',
                        'url': watcher.target_url,
                    }],
                },
            ],
        }],
        'blocks': [
            {'type': 'section', 'text': {'type': 'mrkdwn', 'text': summary}},
        ],
    }


def send_slack_webhook(webhook_url: str, payload: dict) -> None:
    post_json(webhook_url, payload)


def build_discord_payload(watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> dict:
    title = 'Hotel Price Alert Test' if is_test else ('✅ Target Price Reached' if reason == 'threshold_hit' else '📉 Price Drop Alert')
    color = 15158332 if reason == 'threshold_hit' and not is_test else 16098851
    fields = [
        {'name': 'Current Price', 'value': f'{watcher.currency} {current_price:.2f}', 'inline': True},
        {'name': 'Target Price', 'value': f'{watcher.currency} {watcher.threshold_price:.2f}' if watcher.threshold_price is not None else 'Not set', 'inline': True},
        {'name': 'Watcher', 'value': watcher.name, 'inline': True},
        {'name': 'Hotel', 'value': watcher.hotel_name, 'inline': True},
    ]
    if watcher.room_type_keyword.strip():
        fields.append({'name': 'Room', 'value': watcher.room_type_keyword, 'inline': True})
    if watcher.last_price is not None and not is_test:
        fields.append({'name': 'Previous Price', 'value': f'{watcher.currency} {watcher.last_price:.2f}', 'inline': True})
    return {
        'content': None,
        'embeds': [{
            'title': title,
            'description': 'The current price is at or below the target price.' if reason == 'threshold_hit' and not is_test else 'The current price is lower than before, but it has not reached the target price yet.',
            'color': color,
            'url': watcher.target_url,
            'fields': fields,
        }],
    }


def send_discord_webhook(webhook_url: str, payload: dict) -> None:
    post_json(webhook_url, payload)


def parse_telegram_target(target: str) -> tuple[str, str]:
    raw = str(target or '').strip()
    if '|' not in raw:
        raise ValueError('Telegram target format must be bot_token|chat_id')
    bot_token, chat_id = [part.strip() for part in raw.split('|', 1)]
    if not bot_token or not chat_id:
        raise ValueError('Telegram target format must be bot_token|chat_id')
    return bot_token, chat_id


def send_telegram_message(target: str, content: str) -> None:
    bot_token, chat_id = parse_telegram_target(target)
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = urllib.parse.urlencode({'chat_id': chat_id, 'text': content}).encode('utf-8')
    request = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    with http_open(request, timeout=15) as response:
        response.read()


class NotificationProvider:
    provider_name = 'base'

    def send(self, watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> None:
        raise NotImplementedError


class FeishuNotificationProvider(NotificationProvider):
    provider_name = 'feishu'

    def send(self, watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> None:
        if not is_test and reason == 'threshold_hit':
            send_feishu_at_all(watcher.notify_target, watcher, current_price)
        send_feishu_webhook(watcher.notify_target, build_feishu_payload(watcher, current_price, reason, is_test=is_test))


class WechatNotificationProvider(NotificationProvider):
    provider_name = 'wechat'

    def send(self, watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> None:
        send_wechat_webhook(watcher.notify_target, build_notification_text(watcher, current_price, reason, is_test=is_test))


class SlackNotificationProvider(NotificationProvider):
    provider_name = 'slack'

    def send(self, watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> None:
        send_slack_webhook(watcher.notify_target, build_slack_payload(watcher, current_price, reason, is_test=is_test))


class DiscordNotificationProvider(NotificationProvider):
    provider_name = 'discord'

    def send(self, watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> None:
        send_discord_webhook(watcher.notify_target, build_discord_payload(watcher, current_price, reason, is_test=is_test))


class TelegramNotificationProvider(NotificationProvider):
    provider_name = 'telegram'

    def send(self, watcher, current_price: float, reason: NotificationReason, is_test: bool = False) -> None:
        send_telegram_message(watcher.notify_target, build_notification_text(watcher, current_price, reason, is_test=is_test))


PROVIDERS: dict[str, NotificationProvider] = {
    'feishu': FeishuNotificationProvider(),
    'wechat': WechatNotificationProvider(),
    'slack': SlackNotificationProvider(),
    'discord': DiscordNotificationProvider(),
    'telegram': TelegramNotificationProvider(),
}


def resolve_notification_provider(notify_type: str) -> NotificationProvider:
    return PROVIDERS.get((notify_type or 'feishu').strip() or 'feishu', PROVIDERS['feishu'])


def send_notification(watcher, current_price: float, is_test: bool = False, reason: NotificationReason | None = None) -> None:
    actual_reason = 'price_drop' if is_test else (reason or notification_reason(watcher, current_price) or 'price_drop')
    provider = resolve_notification_provider(getattr(watcher, 'notify_type', 'feishu'))
    provider.send(watcher, current_price, actual_reason, is_test=is_test)
