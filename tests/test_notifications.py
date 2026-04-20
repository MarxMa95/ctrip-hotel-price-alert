import unittest
from unittest.mock import patch

from hotel_price_alert.notifications import (
    build_discord_payload,
    build_feishu_payload,
    build_notification_text,
    build_slack_payload,
    notification_decision,
    notification_reason,
    parse_telegram_target,
    send_notification,
    should_notify,
)
from hotel_price_alert.repository import Watcher


class NotificationTests(unittest.TestCase):
    def _watcher(self, **overrides):
        data = dict(
            id=1,
            name='Watcher',
            hotel_name='Hotel',
            source_type='ctrip',
            target_url='https://example.com',
            room_type_keyword='Deluxe King Room',
            room_type_meta='Breakfast Included | Free Cancellation',
            price_pattern='',
            currency='CNY',
            notify_type='feishu',
            notify_target='https://open.feishu.cn/test',
            threshold_price=2000.0,
            min_expected_price=None,
            quiet_hours_start='',
            quiet_hours_end='',
            daily_notification_limit=0,
            notify_only_target_hit=0,
            min_price_drop_amount=None,
            poll_interval_minutes=5,
            request_headers='{}',
            use_local_chrome_profile=0,
            chrome_profile_name='Default',
            use_app_session_profile=1,
            use_browser=1,
            last_error=None,
            is_active=1,
            last_price=None,
            last_checked_at=None,
            last_notified_price=None,
            last_price_note=None,
            all_time_low_price=None,
            all_time_low_at=None,
            created_at='2025-01-01 00:00:00 UTC',
            updated_at='2025-01-01 00:00:00 UTC',
        )
        data.update(overrides)
        return Watcher(**data)

    def test_notify_on_first_threshold_hit(self):
        watcher = self._watcher(last_price=None, last_notified_price=None)
        self.assertTrue(should_notify(watcher, 1800.0))
        self.assertEqual(notification_reason(watcher, 1800.0), 'threshold_hit')

    def test_skip_same_or_higher_than_last_notified(self):
        watcher = self._watcher(last_price=2100.0, last_notified_price=1800.0)
        self.assertFalse(should_notify(watcher, 1800.0))
        self.assertFalse(should_notify(watcher, 1850.0))
        self.assertIsNone(notification_reason(watcher, 1800.0))

    def test_notify_on_price_drop(self):
        watcher = self._watcher(last_price=2200.0, last_notified_price=None, threshold_price=1800.0)
        self.assertTrue(should_notify(watcher, 2100.0))
        self.assertEqual(notification_reason(watcher, 2100.0), 'price_drop')

    def test_notify_only_target_hit_blocks_normal_drop(self):
        watcher = self._watcher(last_price=2200.0, threshold_price=1800.0, notify_only_target_hit=1)
        decision = notification_decision(watcher, 2100.0)
        self.assertFalse(decision.notify)
        self.assertEqual(decision.blocked_by, 'notify_only_target_hit')

    def test_min_drop_amount_blocks_small_drop(self):
        watcher = self._watcher(last_price=2200.0, threshold_price=1800.0, min_price_drop_amount=150.0)
        decision = notification_decision(watcher, 2105.0)
        self.assertFalse(decision.notify)
        self.assertEqual(decision.blocked_by, 'min_price_drop_amount')

    def test_build_threshold_hit_feishu_card(self):
        watcher = self._watcher(last_price=2500.0)
        payload = build_feishu_payload(watcher, 1800.0, 'threshold_hit')
        self.assertEqual(payload['msg_type'], 'interactive')
        self.assertEqual(payload['card']['header']['template'], 'red')
        self.assertIn('Target Price Reached', payload['card']['header']['title']['content'])

    def test_build_price_drop_feishu_card(self):
        watcher = self._watcher(last_price=2500.0, threshold_price=1800.0)
        payload = build_feishu_payload(watcher, 2100.0, 'price_drop')
        self.assertEqual(payload['card']['header']['template'], 'orange')
        text = build_notification_text(watcher, 2100.0, 'price_drop')
        self.assertIn('Target Not Yet Reached', text)

    def test_build_slack_payload(self):
        watcher = self._watcher(last_price=2500.0, notify_type='slack')
        payload = build_slack_payload(watcher, 1800.0, 'threshold_hit')
        self.assertIn('attachments', payload)
        self.assertEqual(payload['attachments'][0]['color'], '#DC2626')
        self.assertEqual(payload['attachments'][0]['blocks'][0]['type'], 'header')

    def test_build_discord_payload(self):
        watcher = self._watcher(last_price=2500.0, notify_type='discord')
        payload = build_discord_payload(watcher, 2100.0, 'price_drop')
        self.assertIn('embeds', payload)
        self.assertEqual(payload['embeds'][0]['url'], watcher.target_url)

    def test_parse_telegram_target(self):
        token, chat_id = parse_telegram_target('123:abc|-100987')
        self.assertEqual(token, '123:abc')
        self.assertEqual(chat_id, '-100987')

    @patch('hotel_price_alert.notifications.send_feishu_webhook')
    @patch('hotel_price_alert.notifications.send_feishu_at_all')
    def test_threshold_hit_sends_at_all_then_card(self, mock_at_all, mock_webhook):
        watcher = self._watcher(last_price=2500.0)
        send_notification(watcher, 1800.0, reason='threshold_hit')
        mock_at_all.assert_called_once()
        mock_webhook.assert_called_once()

    @patch('hotel_price_alert.notifications.send_feishu_webhook')
    @patch('hotel_price_alert.notifications.send_feishu_at_all')
    def test_price_drop_only_sends_normal_feishu(self, mock_at_all, mock_webhook):
        watcher = self._watcher(last_price=2500.0, threshold_price=1800.0)
        send_notification(watcher, 2100.0, reason='price_drop')
        mock_at_all.assert_not_called()
        mock_webhook.assert_called_once()

    @patch('hotel_price_alert.notifications.send_slack_webhook')
    def test_slack_notification_provider(self, mock_send):
        watcher = self._watcher(last_price=2500.0, notify_type='slack', notify_target='https://hooks.slack.com/services/test')
        send_notification(watcher, 2100.0, reason='price_drop')
        mock_send.assert_called_once()

    @patch('hotel_price_alert.notifications.send_discord_webhook')
    def test_discord_notification_provider(self, mock_send):
        watcher = self._watcher(last_price=2500.0, notify_type='discord', notify_target='https://discord.com/api/webhooks/test')
        send_notification(watcher, 2100.0, reason='price_drop')
        mock_send.assert_called_once()

    @patch('hotel_price_alert.notifications.send_telegram_message')
    def test_telegram_notification_provider(self, mock_send):
        watcher = self._watcher(last_price=2500.0, notify_type='telegram', notify_target='123:abc|-100987')
        send_notification(watcher, 2100.0, reason='price_drop')
        mock_send.assert_called_once()


if __name__ == '__main__':
    unittest.main()
