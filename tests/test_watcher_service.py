import unittest
from unittest.mock import patch

from hotel_price_alert.services import watchers as watcher_service


class WatcherServiceTests(unittest.TestCase):
    def test_normalize_watcher_payload(self):
        payload = watcher_service.normalize_watcher_payload({
            'name': '任务',
            'hotel_name': '酒店',
            'source_type': 'ctrip',
            'target_url': 'https://example.com',
            'notify_target': 'https://open.feishu.cn/test',
            'threshold_price': '2000',
            'min_expected_price': '',
            'poll_interval_minutes': '7',
            'request_headers': '{"X-Test":"1"}',
        })
        self.assertEqual(payload['threshold_price'], 2000.0)
        self.assertIsNone(payload['min_expected_price'])
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


if __name__ == '__main__':
    unittest.main()
