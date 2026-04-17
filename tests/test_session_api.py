import unittest
from unittest.mock import patch

from hotel_price_alert.services import session_api


class SessionApiTests(unittest.TestCase):
    @patch('hotel_price_alert.services.session_api.launch_login_and_save_session', return_value={'ok': True})
    def test_start_session_login_uses_default_url(self, mock_launch):
        with patch('hotel_price_alert.services.session_api.session_default_target_url', return_value='https://hotels.ctrip.com/'):
            result = session_api.start_session_login({'source_type': 'ctrip'})
        self.assertTrue(result['ok'])
        mock_launch.assert_called_once()

    @patch('hotel_price_alert.services.session_api.finish_login_and_save_session', return_value={'ok': True})
    def test_finish_session_login(self, mock_finish):
        result = session_api.finish_session_login({'source_type': 'ctrip'})
        self.assertTrue(result['ok'])
        mock_finish.assert_called_once_with('ctrip')

    def test_verify_session_requires_target_url(self):
        payload, status = session_api.verify_session_payload({'source_type': 'ctrip'})
        self.assertEqual(status, 400)
        self.assertIn('error', payload)

    @patch('hotel_price_alert.services.session_api.verify_app_session', return_value={'ok': True})
    def test_verify_session_success(self, mock_verify):
        payload, status = session_api.verify_session_payload({
            'source_type': 'ctrip',
            'target_url': 'https://example.com',
            'request_headers': '{}',
            'cookie': 'a=1',
        })
        self.assertEqual(status, 200)
        self.assertTrue(payload['ok'])
        mock_verify.assert_called_once()

    @patch('hotel_price_alert.services.session_api.browser_capture_with_app_session', return_value={'shot': 'ok'})
    def test_debug_session_screenshot_payload(self, mock_capture):
        payload = session_api.debug_session_screenshot_payload({
            'source_type': 'ctrip',
            'target_url': 'https://example.com',
            'request_headers': '{}',
            'cookie': '',
            'room_type_keyword': 'Suite',
            'focus_room': True,
        })
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['shot'], 'ok')
        mock_capture.assert_called_once()


if __name__ == '__main__':
    unittest.main()
