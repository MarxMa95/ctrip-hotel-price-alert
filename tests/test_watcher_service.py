import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hotel_price_alert.services import watchers as watcher_service
from hotel_price_alert.utils import watcher_next_run_display


class WatcherServiceTests(unittest.TestCase):
    def test_normalize_watcher_payload(self):
        payload = watcher_service.normalize_watcher_payload({
            'name': 'Watcher',
            'hotel_name': 'Hotel',
            'source_type': 'ctrip',
            'target_url': 'https://example.com',
            'notify_target': 'https://open.feishu.cn/test',
            'threshold_price': '2000',
            'min_expected_price': '',
            'quiet_hours_start': '23:00',
            'quiet_hours_end': '07:00',
            'daily_notification_limit': '2',
            'notify_only_target_hit': 'on',
            'min_price_drop_amount': '100',
            'poll_interval_minutes': '7',
            'request_headers': '{"X-Test":"1"}',
        })
        self.assertEqual(payload['threshold_price'], 2000.0)
        self.assertIsNone(payload['min_expected_price'])
        self.assertEqual(payload['quiet_hours_start'], '23:00')
        self.assertEqual(payload['quiet_hours_end'], '07:00')
        self.assertEqual(payload['daily_notification_limit'], 2)
        self.assertTrue(payload['notify_only_target_hit'])
        self.assertEqual(payload['min_price_drop_amount'], 100.0)
        self.assertEqual(payload['poll_interval_minutes'], 7)
        self.assertTrue(payload['use_app_session_profile'])
        self.assertFalse(payload['use_local_chrome_profile'])

    @patch('hotel_price_alert.services.watchers.check_watcher', return_value={'ok': True, 'price': 1888.0})
    @patch('hotel_price_alert.services.watchers.find_watcher')
    def test_run_check_now(self, mock_find_watcher, mock_check):
        mock_find_watcher.return_value = object()
        payload, status = watcher_service.run_check_now(1)
        self.assertEqual(status, 200)
        self.assertTrue(payload['ok'])

    @patch('hotel_price_alert.services.watchers.find_watcher', return_value=None)
    def test_run_check_now_not_found(self, mock_find_watcher):
        payload, status = watcher_service.run_check_now(999)
        self.assertEqual(status, 404)
        self.assertIn('error', payload)

    def test_watcher_next_run_display_keeps_utc(self):
        watcher = SimpleNamespace(
            poll_interval_minutes=5,
            last_checked_at='2026-04-20 07:27:19 UTC',
        )
        self.assertEqual(
            watcher_next_run_display(watcher),
            '2026-04-20 07:32:19 UTC',
        )

    def test_is_room_missing_error(self):
        self.assertTrue(watcher_service.is_room_missing_error('Room keyword not found (Suggestions: xxx)'))
        self.assertFalse(watcher_service.is_room_missing_error('Other error'))


if __name__ == '__main__':
    unittest.main()
