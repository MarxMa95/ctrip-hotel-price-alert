import unittest
from unittest.mock import patch

from hotel_price_alert.repository import Watcher
from hotel_price_alert.services.checker import check_watcher


class CheckerTests(unittest.TestCase):
    def _watcher(self, **overrides):
        data = dict(
            id=1,
            name='任务',
            hotel_name='酒店',
            source_type='ctrip',
            target_url='https://example.com',
            room_type_keyword='豪华大床房',
            room_type_meta='含早',
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
            last_price=2200.0,
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

    @patch('hotel_price_alert.services.checker.update_check_result')
    @patch('hotel_price_alert.services.checker.send_notification')
    @patch('hotel_price_alert.services.checker.extract_price_for_watcher', return_value=1888.0)
    @patch('hotel_price_alert.services.checker.browser_fetch_with_app_session', return_value='mock-page')
    def test_check_watcher_success(self, mock_fetch, mock_extract, mock_notify, mock_update):
        watcher = self._watcher()
        result = check_watcher(watcher)
        self.assertTrue(result['ok'])
        self.assertEqual(result['price'], 1888.0)
        mock_notify.assert_called_once()
        mock_update.assert_called_once()

    @patch('hotel_price_alert.services.checker.update_check_result')
    @patch('hotel_price_alert.services.checker.browser_fetch_with_app_session', side_effect=ValueError('boom'))
    def test_check_watcher_error(self, mock_fetch, mock_update):
        watcher = self._watcher()
        result = check_watcher(watcher)
        self.assertFalse(result['ok'])
        self.assertIn('boom', result['error'])
        mock_update.assert_called_once()


if __name__ == '__main__':
    unittest.main()
