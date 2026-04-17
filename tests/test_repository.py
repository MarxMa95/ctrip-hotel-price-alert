import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hotel_price_alert import repository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'test.db'
        self.db_patcher = patch.object(repository, 'DB_PATH', self.db_path)
        self.db_patcher.start()
        repository.init_db()

    def tearDown(self):
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_watcher_crud_and_history(self):
        watcher_id = repository.create_watcher({
            'name': 'Test Task',
            'hotel_name': 'Test Hotel',
            'source_type': 'ctrip',
            'target_url': 'https://example.com/hotel',
            'room_type_keyword': 'Deluxe King Room',
            'room_type_meta': 'Breakfast included | Free cancellation',
            'price_pattern': '',
            'currency': 'CNY',
            'notify_type': 'feishu',
            'notify_target': 'https://open.feishu.cn/test',
            'threshold_price': 2000.0,
            'min_expected_price': 1500.0,
            'poll_interval_minutes': 5,
            'request_headers': '{"X-Test": "1"}',
            'cookie': 'a=1; b=2',
            'use_app_session_profile': True,
            'use_browser': True,
        })

        watcher = repository.find_watcher(watcher_id)
        self.assertIsNotNone(watcher)
        self.assertEqual(watcher.name, 'Test Task')
        self.assertIn('Cookie', watcher.parsed_headers())

        repository.update_watcher(watcher_id, {
            'name': 'Test Task2',
            'hotel_name': 'Test Hotel2',
            'source_type': 'ctrip',
            'target_url': 'https://example.com/hotel-2',
            'room_type_keyword': 'Ocean View Suite',
            'room_type_meta': 'Breakfast for 2',
            'price_pattern': '',
            'currency': 'CNY',
            'notify_type': 'feishu',
            'notify_target': 'https://open.feishu.cn/test2',
            'threshold_price': 1800.0,
            'min_expected_price': 1400.0,
            'poll_interval_minutes': 10,
            'request_headers': '{}',
            'cookie': '',
            'use_app_session_profile': True,
            'use_browser': True,
        })
        updated = repository.find_watcher(watcher_id)
        self.assertEqual(updated.name, 'Test Task2')
        self.assertEqual(updated.poll_interval_minutes, 10)

        repository.set_watcher_active(watcher_id, 0)
        toggled = repository.find_watcher(watcher_id)
        self.assertEqual(toggled.is_active, 0)

        repository.update_check_result(watcher_id, 1688.0, True, None, 'Matched a room block')
        repository.update_check_result(watcher_id, 1888.0, False, None, 'Checked again')
        repository.update_check_result(watcher_id, 1688.0, False, None, 'Matched the historical low again')
        history = repository.list_history(watcher_id)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]['price'], 1688.0)
        self.assertEqual(history[-1]['price'], 1688.0)
        low = repository.find_watcher(watcher_id)
        self.assertEqual(low.all_time_low_price, 1688.0)
        self.assertIsNotNone(low.all_time_low_at)

        repository.delete_watcher(watcher_id)
        self.assertIsNone(repository.find_watcher(watcher_id))


if __name__ == '__main__':
    unittest.main()
