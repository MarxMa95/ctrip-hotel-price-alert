import unittest
from pathlib import Path
from unittest.mock import patch

from hotel_price_alert.legacy_app import _iter_browser_candidates, resolve_chromium_executable


class BrowserResolutionTests(unittest.TestCase):
    @patch('hotel_price_alert.legacy_app.PLAYWRIGHT_CACHE_DIR')
    @patch('hotel_price_alert.legacy_app.SYSTEM_BROWSER_CANDIDATES', [])
    def test_iter_browser_candidates_without_playwright_object(self, mock_cache_dir):
        fake_path = Path('/tmp/fake-chromium')
        mock_cache_dir.glob.return_value = [fake_path]
        with patch.object(Path, 'exists', return_value=True):
            items = _iter_browser_candidates()
        self.assertTrue(items)

    @patch('hotel_price_alert.legacy_app._iter_browser_candidates', return_value=[Path('/tmp/fake-chromium')])
    def test_resolve_chromium_executable_without_playwright_object(self, mock_iter):
        result = resolve_chromium_executable()
        self.assertEqual(result, '/tmp/fake-chromium')


if __name__ == '__main__':
    unittest.main()
