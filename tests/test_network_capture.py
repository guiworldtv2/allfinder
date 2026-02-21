"""
Testes para o módulo allfinder.core.network_capture.
"""

import pytest
from allfinder.core.network_capture import (
    NetworkCapture,
    CapturedStream,
    normalize_stream_url,
    extract_embedded_url,
    _is_blacklisted,
    _is_media_url,
    _is_priority,
    _detect_format,
)


# ---------------------------------------------------------------------------
# Testes de funções auxiliares
# ---------------------------------------------------------------------------

def test_normalize_stream_url_removes_query():
    url = "https://video.globo.com/stream/playlist.m3u8?token=abc123&ts=1234"
    result = normalize_stream_url(url)
    assert result == "https://video.globo.com/stream/playlist.m3u8"
    assert "token" not in result
    assert "ts" not in result


def test_normalize_stream_url_keeps_path():
    url = "https://cdn.example.com/live/master.m3u8"
    result = normalize_stream_url(url)
    assert result == "https://cdn.example.com/live/master.m3u8"


def test_is_blacklisted_analytics():
    assert _is_blacklisted("https://youbora.nicepeopleatwork.com/track.m3u8") is True
    assert _is_blacklisted("https://analytics.example.com/stream.m3u8") is True
    assert _is_blacklisted("https://doubleclick.net/ad.m3u8") is True


def test_is_blacklisted_valid_stream():
    assert _is_blacklisted("https://video.globo.com/stream/playlist.m3u8") is False
    assert _is_blacklisted("https://cdn.example.com/live/master.m3u8") is False


def test_is_media_url():
    assert _is_media_url("https://cdn.example.com/stream.m3u8") is True
    assert _is_media_url("https://cdn.example.com/manifest.mpd") is True
    assert _is_media_url("https://cdn.example.com/image.jpg") is False
    assert _is_media_url("https://cdn.example.com/page.html") is False


def test_is_priority():
    assert _is_priority("https://cdn.example.com/master.m3u8") is True
    assert _is_priority("https://cdn.example.com/index.m3u8") is True
    assert _is_priority("https://cdn.example.com/playlist.m3u8") is True
    assert _is_priority("https://cdn.example.com/chunklist_b500000.m3u8") is True
    assert _is_priority("https://cdn.example.com/seg001.ts") is False


def test_detect_format_hls():
    assert _detect_format("https://cdn.example.com/stream.m3u8") == "hls"


def test_detect_format_dash():
    assert _detect_format("https://cdn.example.com/manifest.mpd") == "dash"


def test_detect_format_unknown():
    assert _detect_format("https://cdn.example.com/video.mp4") == "unknown"


def test_extract_embedded_url_found():
    url = "https://analytics.example.com/track?ep.URL=https%3A%2F%2Fcdn.example.com%2Fstream.m3u8"
    result = extract_embedded_url(url)
    assert result == "https://cdn.example.com/stream.m3u8"


def test_extract_embedded_url_not_found():
    url = "https://cdn.example.com/stream.m3u8"
    result = extract_embedded_url(url)
    assert result is None


# ---------------------------------------------------------------------------
# Testes da classe NetworkCapture
# ---------------------------------------------------------------------------

def test_network_capture_captures_valid_stream():
    capture = NetworkCapture()
    capture._process_url("https://video.globo.com/stream/playlist.m3u8?token=abc")
    assert capture.has_streams()
    assert len(capture) == 1
    # A URL deve estar normalizada (sem query string)
    assert "token" not in capture.get_urls()[0]


def test_network_capture_ignores_blacklisted():
    capture = NetworkCapture()
    capture._process_url("https://youbora.nicepeopleatwork.com/track.m3u8")
    assert not capture.has_streams()


def test_network_capture_ignores_non_media():
    capture = NetworkCapture()
    capture._process_url("https://cdn.example.com/image.jpg")
    assert not capture.has_streams()


def test_network_capture_deduplication():
    capture = NetworkCapture(deduplicate=True)
    capture._process_url("https://cdn.example.com/master.m3u8?token=1")
    capture._process_url("https://cdn.example.com/master.m3u8?token=2")
    # Após normalização, ambas viram a mesma URL
    assert len(capture) == 1


def test_network_capture_priority_ordering():
    capture = NetworkCapture()
    capture._process_url("https://cdn.example.com/seg001.m3u8")
    capture._process_url("https://cdn.example.com/master.m3u8")
    urls = capture.get_urls()
    # A URL prioritária (master) deve vir primeiro
    assert "master" in urls[0]


def test_network_capture_get_best_url_prefers_playlist():
    capture = NetworkCapture()
    capture._process_url("https://cdn.example.com/master.m3u8")
    capture._process_url("https://cdn.example.com/playlist.m3u8")
    best = capture.get_best_url()
    assert "playlist.m3u8" in best


def test_network_capture_get_best_url_fallback():
    capture = NetworkCapture()
    capture._process_url("https://cdn.example.com/stream.m3u8")
    best = capture.get_best_url()
    assert best == "https://cdn.example.com/stream.m3u8"


def test_network_capture_get_best_url_empty():
    capture = NetworkCapture()
    assert capture.get_best_url() is None


def test_network_capture_reset():
    capture = NetworkCapture()
    capture._process_url("https://cdn.example.com/stream.m3u8")
    assert capture.has_streams()
    capture.reset()
    assert not capture.has_streams()
    assert len(capture) == 0


def test_network_capture_extracts_embedded_url():
    capture = NetworkCapture()
    # URL de analytics com stream embutido no parâmetro
    url = "https://analytics.example.com/track?ep.URL=https%3A%2F%2Fcdn.example.com%2Fstream.m3u8"
    capture._process_url(url)
    assert capture.has_streams()
    assert "cdn.example.com" in capture.get_urls()[0]


def test_network_capture_has_priority_stream():
    capture = NetworkCapture()
    capture._process_url("https://cdn.example.com/master.m3u8")
    assert capture.has_priority_stream()


def test_network_capture_no_priority_stream():
    capture = NetworkCapture()
    capture._process_url("https://cdn.example.com/seg001.m3u8")
    assert not capture.has_priority_stream()
