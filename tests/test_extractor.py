import pytest
import json
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

def test_parse_cookies_json(tmp_path):
    d = tmp_path / "cookies.json"
    cookies_data = [{"name": "test", "value": "val", "domain": "example.com", "path": "/"}]
    d.write_text(json.dumps(cookies_data))
    
    extractor = M3U8Extractor(cookies_file=str(d))
    parsed = extractor._parse_cookies_file()
    assert len(parsed) == 1
    assert parsed[0]['name'] == "test"

def test_parse_cookies_txt(tmp_path):
    d = tmp_path / "cookies.txt"
    # Formato Netscape: domain, flag, path, secure, expiration, name, value
    d.write_text("example.com\tTRUE\t/\tFALSE\t1700000000\tname\tvalue\n")
    
    extractor = M3U8Extractor(cookies_file=str(d))
    parsed = extractor._parse_cookies_file()
    assert len(parsed) == 1
    assert parsed[0]['name'] == "name"
    assert parsed[0]['value'] == "value"
