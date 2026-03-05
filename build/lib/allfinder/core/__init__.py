"""
allfinder.core
==============
Módulos principais do allfinder.

- extractor: Extração de URLs de mídia via Playwright.
- browser_profile: Detecção e reutilização de perfis de navegador.
- network_capture: Captura e filtragem de tráfego de rede.
"""

from allfinder.core.extractor import M3U8Extractor, ensure_playwright_browsers
from allfinder.core.browser_profile import (
    BrowserProfile,
    detect_available_browsers,
    list_profiles,
    get_profile,
    print_available_profiles,
)
from allfinder.core.network_capture import NetworkCapture, CapturedStream

__all__ = [
    "M3U8Extractor",
    "ensure_playwright_browsers",
    "BrowserProfile",
    "detect_available_browsers",
    "list_profiles",
    "get_profile",
    "print_available_profiles",
    "NetworkCapture",
    "CapturedStream",
]
