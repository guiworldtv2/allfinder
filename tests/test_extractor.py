import pytest
from allfinder.core.extractor import M3U8Extractor

def test_validate_url_valid():
    extractor = M3U8Extractor()
    assert extractor.validate_url("https://google.com") is True
    assert extractor.validate_url("http://exemplo.com/video") is True

def test_validate_url_invalid():
    extractor = M3U8Extractor()
    assert extractor.validate_url("not-a-url") is False
    assert extractor.validate_url("ftp://server.com") is False

def test_validate_url_ssrf_prevention():
    extractor = M3U8Extractor()
    assert extractor.validate_url("http://localhost") is False
    assert extractor.validate_url("http://127.0.0.1") is False
    assert extractor.validate_url("http://192.168.1.1") is False
    assert extractor.validate_url("http://10.0.0.1") is False
    assert extractor.validate_url("http://172.16.0.1") is False

def test_extractor_initialization():
    extractor = M3U8Extractor(headless=False, timeout=5000, cookies_from_browser="chrome")
    assert extractor.headless is False
    assert extractor.timeout == 5000
    assert extractor.cookies_from_browser == "chrome"
    assert extractor.found_urls == []
    assert extractor.page_title == "Stream"
