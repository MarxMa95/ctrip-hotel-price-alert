import unittest
from unittest.mock import patch

from hotel_price_alert.notifications import (
    build_feishu_payload,
    build_notification_text,
    notification_reason,
    send_notification,
    should_notify,
)
from hotel_price_alert.repository import Watcher


class NotificationTests(unittest.TestCase):
    def _watcher(self, **overrides):
        data = dict(
            id=1,
            name='任务',
            hotel_name='酒店',
            source_type='ctrip',
            target_url='https://example.com',
            room_type_keyword='豪华大床房',
            room_type_meta='含早 | 免费取消',
            price_pattern='',
            currency='CNY',
            notify_type='feishu',
            notify_target='https://open.feishu.cn/test',
            threshold_price=2000.0,
            min_expected_price=None,
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

    def test_build_threshold_hit_feishu_card(self):
        watcher = self._watcher(last_price=2500.0)
        payload = build_feishu_payload(watcher, 1800.0, 'threshold_hit')
        self.assertEqual(payload['msg_type'], 'interactive')
        self.assertEqual(payload['card']['header']['template'], 'red')
        self.assertIn('已达到目标价格', payload['card']['header']['title']['content'])

    def test_build_price_drop_feishu_card(self):
        watcher = self._watcher(last_price=2500.0, threshold_price=1800.0)
        payload = build_feishu_payload(watcher, 2100.0, 'price_drop')
        self.assertEqual(payload['card']['header']['template'], 'orange')
        text = build_notification_text(watcher, 2100.0, 'price_drop')
        self.assertIn('未达目标价', text)

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


if __name__ == '__main__':
    unittest.main()
