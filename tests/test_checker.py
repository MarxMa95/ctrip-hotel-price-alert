import unittest
from unittest.mock import patch

from hotel_price_alert.repository import Watcher
from hotel_price_alert.services.checker import check_watcher, summarize_runtime_error


class CheckerTests(unittest.TestCase):
    def _watcher(self, **overrides):
        data = dict(
            id=1,
            name='Watcher',
            hotel_name='Hotel',
            source_type='ctrip',
            target_url='https://example.com',
            room_type_keyword='Deluxe King Room',
            room_type_meta='Breakfast Included',
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
    @patch('hotel_price_alert.services.checker.append_notification_event')
    @patch('hotel_price_alert.services.checker.extract_price_for_watcher', return_value=1888.0)
    @patch('hotel_price_alert.services.checker.browser_fetch_with_app_session', return_value='mock-page')
    def test_check_watcher_success(self, mock_fetch, mock_extract, mock_append_event, mock_notify, mock_update):
        watcher = self._watcher()
        result = check_watcher(watcher)
        self.assertTrue(result['ok'])
        self.assertEqual(result['price'], 1888.0)
        mock_notify.assert_called_once()
        mock_append_event.assert_called_once()
        mock_update.assert_called_once()

    @patch('hotel_price_alert.services.checker.update_check_result')
    @patch('hotel_price_alert.services.checker.browser_fetch_with_app_session', side_effect=ValueError('boom'))
    def test_check_watcher_error(self, mock_fetch, mock_update):
        watcher = self._watcher()
        result = check_watcher(watcher)
        self.assertFalse(result['ok'])
        self.assertIn('boom', result['error'])
        mock_update.assert_called_once()

    def test_summarize_room_missing_error(self):
        message = summarize_runtime_error(ValueError(
            'Room keyword not found: Small Pool Suite. Attempted keyword variants: Small Pool Suite / Small Pool. Example room candidates found on the page: Spa Pool Suite.'
        ))
        self.assertEqual(
            message,
            'Room keyword not found (Suggestions: 1. confirm whether this room type is sold out or no longer listed; 2. if it is still available, paste the full room name from the page and try again.)',
        )


if __name__ == '__main__':
    unittest.main()
