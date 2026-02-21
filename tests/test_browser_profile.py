"""
Testes para o módulo allfinder.core.browser_profile.
"""

import pytest
from unittest.mock import patch, MagicMock
from allfinder.core.browser_profile import (
    BrowserProfile,
    detect_available_browsers,
    list_profiles,
    get_profile,
    build_playwright_launch_kwargs,
    _get_os,
)


def test_get_os_returns_valid_value():
    os_name = _get_os()
    assert os_name in ("windows", "linux", "macos")


def test_detect_available_browsers_returns_dict():
    result = detect_available_browsers()
    assert isinstance(result, dict)
    assert set(result.keys()) == {"chrome", "edge", "firefox", "chromium"}
    # Cada valor deve ser uma string (caminho) ou None
    for browser, path in result.items():
        assert path is None or isinstance(path, str)


def test_list_profiles_returns_list():
    """list_profiles deve retornar uma lista (possivelmente vazia) para qualquer navegador."""
    for browser in ["chrome", "edge", "firefox", "chromium"]:
        result = list_profiles(browser)
        assert isinstance(result, list)


def test_get_profile_returns_none_when_no_profiles():
    """get_profile deve retornar None quando não há perfis disponíveis."""
    with patch("allfinder.core.browser_profile.list_profiles", return_value=[]):
        result = get_profile("chrome", "Perfil Inexistente")
        assert result is None


def test_get_profile_returns_first_when_no_name():
    """get_profile sem nome deve retornar o primeiro perfil disponível."""
    mock_profile = BrowserProfile(
        browser="chrome",
        profile_name="Default",
        profile_dir="Default",
        user_data_dir="/fake/path",
    )
    with patch("allfinder.core.browser_profile.list_profiles", return_value=[mock_profile]):
        result = get_profile("chrome")
        assert result == mock_profile


def test_get_profile_by_exact_name():
    """get_profile deve encontrar um perfil pelo nome exato."""
    profiles = [
        BrowserProfile("edge", "Default", "Default", "/fake"),
        BrowserProfile("edge", "Pessoa 1", "Profile 1", "/fake"),
        BrowserProfile("edge", "Pessoa 2", "Profile 2", "/fake"),
    ]
    with patch("allfinder.core.browser_profile.list_profiles", return_value=profiles):
        result = get_profile("edge", "Pessoa 1")
        assert result is not None
        assert result.profile_name == "Pessoa 1"


def test_get_profile_by_partial_name():
    """get_profile deve encontrar um perfil por correspondência parcial."""
    profiles = [
        BrowserProfile("chrome", "Meu Perfil Principal", "Profile 1", "/fake"),
    ]
    with patch("allfinder.core.browser_profile.list_profiles", return_value=profiles):
        result = get_profile("chrome", "Principal")
        assert result is not None
        assert "Principal" in result.profile_name


def test_build_playwright_launch_kwargs_chromium():
    """build_playwright_launch_kwargs deve retornar kwargs corretos para Chromium."""
    profile = BrowserProfile(
        browser="chromium",
        profile_name="Default",
        profile_dir="Default",
        user_data_dir="/home/user/.config/chromium",
    )
    kwargs = build_playwright_launch_kwargs(profile)
    assert kwargs["browser_type"] == "chromium"
    assert kwargs["channel"] is None
    assert kwargs["user_data_dir"] == "/home/user/.config/chromium"
    assert "--disable-blink-features=AutomationControlled" in kwargs["args"]


def test_build_playwright_launch_kwargs_edge():
    """build_playwright_launch_kwargs deve usar channel 'msedge' para Edge."""
    profile = BrowserProfile(
        browser="edge",
        profile_name="Pessoa 1",
        profile_dir="Profile 1",
        user_data_dir="/fake/edge/data",
    )
    kwargs = build_playwright_launch_kwargs(profile)
    assert kwargs["browser_type"] == "chromium"
    assert kwargs["channel"] == "msedge"


def test_build_playwright_launch_kwargs_firefox():
    """build_playwright_launch_kwargs deve usar browser_type 'firefox' para Firefox."""
    profile = BrowserProfile(
        browser="firefox",
        profile_name="default-release",
        profile_dir="/home/user/.mozilla/firefox/abc.default",
        user_data_dir="/home/user/.mozilla/firefox",
    )
    kwargs = build_playwright_launch_kwargs(profile)
    assert kwargs["browser_type"] == "firefox"
    assert kwargs["channel"] is None


def test_build_playwright_launch_kwargs_chrome():
    """build_playwright_launch_kwargs deve usar channel 'chrome' para Chrome."""
    profile = BrowserProfile(
        browser="chrome",
        profile_name="Default",
        profile_dir="Default",
        user_data_dir="/fake/chrome/data",
    )
    kwargs = build_playwright_launch_kwargs(profile)
    assert kwargs["browser_type"] == "chromium"
    assert kwargs["channel"] == "chrome"
