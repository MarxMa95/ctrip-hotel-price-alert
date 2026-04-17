from .legacy_app import (
    _open_app_session_page,
    browser_capture_with_app_session,
    browser_fetch,
    browser_fetch_with_app_session,
    browser_fetch_with_local_profile,
    discover_chrome_profiles,
    fetch_text,
    normalize_headers,
    normalize_target_url,
    prepare_app_session_profile_copy,
    prepare_local_chrome_profile,
    source_default_headers,
)

__all__ = [
    '_open_app_session_page', 'browser_capture_with_app_session', 'browser_fetch',
    'browser_fetch_with_app_session', 'browser_fetch_with_local_profile', 'discover_chrome_profiles',
    'fetch_text', 'normalize_headers', 'normalize_target_url', 'prepare_app_session_profile_copy',
    'prepare_local_chrome_profile', 'source_default_headers',
]
