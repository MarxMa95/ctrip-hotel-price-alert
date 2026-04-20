import unittest

from hotel_price_alert.extractors import extract_price_for_watcher, matched_room_blocks
from hotel_price_alert.repository import Watcher


def build_watcher(room_type_keyword: str) -> Watcher:
    return Watcher(
        id=1,
        name='测试监控',
        hotel_name='测试酒店',
        source_type='ctrip',
        target_url='https://example.com',
        room_type_keyword=room_type_keyword,
        room_type_meta='',
        price_pattern='',
        currency='CNY',
        notify_type='feishu',
        notify_target='https://example.com/webhook',
        threshold_price=3000.0,
        min_expected_price=2000.0,
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


class ExtractorTests(unittest.TestCase):
    def test_strict_room_match_does_not_match_other_pool_suite(self):
        watcher = build_watcher('小型泳池套房')
        text = '\n'.join([
            'ROOM_BLOCK||水疗泳池套房私人泳池||3640||早餐 | 不可取消 | 在线付||水疗泳池套房私人泳池 早餐 不可取消 在线付',
            'ROOM_BLOCK||两卧室至尊豪华泳池套房私人泳池||6119||早餐 | 不可取消 | 在线付||两卧室至尊豪华泳池套房私人泳池 早餐 不可取消 在线付',
        ])
        self.assertEqual(matched_room_blocks(text, watcher), [])
        with self.assertRaises(ValueError):
            extract_price_for_watcher(text, watcher)

    def test_strict_room_match_keeps_exact_room_name(self):
        watcher = build_watcher('小型泳池套房')
        text = '\n'.join([
            'ROOM_BLOCK||小型泳池套房||3345||早餐 | 不可取消 | 在线付||小型泳池套房 早餐 不可取消 在线付',
            'ROOM_BLOCK||水疗泳池套房私人泳池||3640||早餐 | 不可取消 | 在线付||水疗泳池套房私人泳池 早餐 不可取消 在线付',
        ])
        matched = matched_room_blocks(text, watcher)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]['room_name'], '小型泳池套房')
        self.assertEqual(extract_price_for_watcher(text, watcher), 3345.0)


if __name__ == '__main__':
    unittest.main()
