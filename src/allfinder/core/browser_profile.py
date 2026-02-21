"""
browser_profile.py
==================
Módulo responsável por detectar navegadores instalados no sistema e configurar
o Playwright para reutilizar perfis existentes do usuário.

A técnica de reutilização de perfil permite que o allfinder acesse sites que
exigem login (ex: Globoplay, Netflix, etc.) sem precisar automatizar o processo
de autenticação — o navegador já carrega os cookies e sessões salvas.

Navegadores suportados: Chrome, Chromium, Edge (Edgium), Firefox.
"""

import os
import sys
import json
import shutil
import platform
import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Estrutura de dados de um perfil de navegador
# ---------------------------------------------------------------------------

@dataclass
class BrowserProfile:
    """Representa um perfil de navegador detectado no sistema."""
    browser: str          # "chrome" | "edge" | "firefox" | "chromium"
    profile_name: str     # Nome amigável (ex: "Pessoa 1", "Default")
    profile_dir: str      # Diretório do perfil (relativo ao user_data_dir)
    user_data_dir: str    # Diretório raiz de dados do navegador
    executable: Optional[str] = None  # Caminho para o executável do navegador


# ---------------------------------------------------------------------------
# Detecção de executáveis por sistema operacional
# ---------------------------------------------------------------------------

def _get_os() -> str:
    """Retorna 'windows', 'linux' ou 'macos'."""
    s = platform.system().lower()
    if s == "windows":
        return "windows"
    if s == "darwin":
        return "macos"
    return "linux"


def _find_executable(candidates: List[str]) -> Optional[str]:
    """Retorna o primeiro executável encontrado na lista de caminhos candidatos."""
    for path in candidates:
        expanded = os.path.expandvars(os.path.expanduser(path))
        if os.path.isfile(expanded):
            return expanded
    # Tenta via PATH do sistema
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def find_browser_executable(browser: str) -> Optional[str]:
    """
    Localiza o executável de um navegador no sistema operacional atual.

    Parâmetros
    ----------
    browser : str
        Nome do navegador: "chrome", "edge", "firefox" ou "chromium".

    Retorna
    -------
    str ou None
        Caminho absoluto para o executável, ou None se não encontrado.
    """
    os_name = _get_os()

    executables: Dict[str, Dict[str, List[str]]] = {
        "chrome": {
            "windows": [
                r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
                r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
            ],
            "linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ],
            "macos": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ],
        },
        "edge": {
            "windows": [
                r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
                r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
                "msedge",
            ],
            "linux": [
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
                "/usr/bin/microsoft-edge-beta",
            ],
            "macos": [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ],
        },
        "firefox": {
            "windows": [
                r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe",
                r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe",
            ],
            "linux": [
                "/usr/bin/firefox",
                "/usr/bin/firefox-esr",
                "/snap/bin/firefox",
            ],
            "macos": [
                "/Applications/Firefox.app/Contents/MacOS/firefox",
            ],
        },
        "chromium": {
            "windows": [
                r"%LOCALAPPDATA%\Chromium\Application\chrome.exe",
            ],
            "linux": [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ],
            "macos": [
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ],
        },
    }

    candidates = executables.get(browser, {}).get(os_name, [])
    return _find_executable(candidates)


# ---------------------------------------------------------------------------
# Detecção de diretórios de perfil por navegador e SO
# ---------------------------------------------------------------------------

def _get_user_data_dirs(browser: str) -> List[str]:
    """Retorna os caminhos candidatos para o diretório de dados do usuário."""
    os_name = _get_os()
    home = os.path.expanduser("~")

    dirs: Dict[str, Dict[str, List[str]]] = {
        "chrome": {
            "windows": [r"%LOCALAPPDATA%\Google\Chrome\User Data"],
            "linux": [
                os.path.join(home, ".config", "google-chrome"),
                os.path.join(home, ".config", "chromium"),
            ],
            "macos": [
                os.path.join(home, "Library", "Application Support", "Google", "Chrome"),
            ],
        },
        "edge": {
            "windows": [r"%LOCALAPPDATA%\Microsoft\Edge\User Data"],
            "linux": [
                os.path.join(home, ".config", "microsoft-edge"),
                os.path.join(home, ".config", "microsoft-edge-stable"),
            ],
            "macos": [
                os.path.join(home, "Library", "Application Support", "Microsoft Edge"),
            ],
        },
        "firefox": {
            "windows": [r"%APPDATA%\Mozilla\Firefox\Profiles"],
            "linux": [os.path.join(home, ".mozilla", "firefox")],
            "macos": [
                os.path.join(home, "Library", "Application Support", "Firefox", "Profiles"),
            ],
        },
        "chromium": {
            "windows": [r"%LOCALAPPDATA%\Chromium\User Data"],
            "linux": [
                os.path.join(home, ".config", "chromium"),
            ],
            "macos": [
                os.path.join(home, "Library", "Application Support", "Chromium"),
            ],
        },
    }

    raw_dirs = dirs.get(browser, {}).get(os_name, [])
    return [os.path.expandvars(os.path.expanduser(d)) for d in raw_dirs]


# ---------------------------------------------------------------------------
# Enumeração de perfis Chromium-based (Chrome, Edge, Chromium)
# ---------------------------------------------------------------------------

def _list_chromium_profiles(user_data_dir: str) -> List[Tuple[str, str]]:
    """
    Varre o diretório de dados do Chromium/Chrome/Edge e retorna uma lista de
    (nome_amigável, nome_do_diretório) para cada perfil encontrado.
    """
    profiles: List[Tuple[str, str]] = []
    if not os.path.isdir(user_data_dir):
        return profiles

    for item in os.listdir(user_data_dir):
        item_path = os.path.join(user_data_dir, item)
        prefs_path = os.path.join(item_path, "Preferences")
        if os.path.isdir(item_path) and os.path.isfile(prefs_path):
            try:
                with open(prefs_path, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    name = data.get("profile", {}).get("name", item)
                    profiles.append((name, item))
            except Exception:
                profiles.append((item, item))

    return profiles


# ---------------------------------------------------------------------------
# Enumeração de perfis Firefox
# ---------------------------------------------------------------------------

def _list_firefox_profiles(profiles_dir: str) -> List[Tuple[str, str]]:
    """
    Lê o arquivo profiles.ini do Firefox e retorna (nome, caminho_absoluto).
    """
    profiles: List[Tuple[str, str]] = []
    ini_path = os.path.join(os.path.dirname(profiles_dir), "profiles.ini")
    if not os.path.isfile(ini_path):
        # Tenta encontrar o profiles.ini um nível acima
        ini_path = os.path.join(profiles_dir, "..", "profiles.ini")

    if os.path.isfile(ini_path):
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(ini_path, encoding="utf-8")
            for section in config.sections():
                if section.startswith("Profile"):
                    name = config.get(section, "Name", fallback=section)
                    path = config.get(section, "Path", fallback=None)
                    is_relative = config.getint(section, "IsRelative", fallback=1)
                    if path:
                        if is_relative:
                            abs_path = os.path.join(os.path.dirname(ini_path), path)
                        else:
                            abs_path = path
                        profiles.append((name, os.path.normpath(abs_path)))
        except Exception:
            pass

    # Fallback: lista subdiretórios
    if not profiles and os.path.isdir(profiles_dir):
        for item in os.listdir(profiles_dir):
            full = os.path.join(profiles_dir, item)
            if os.path.isdir(full):
                profiles.append((item, full))

    return profiles


# ---------------------------------------------------------------------------
# API pública: listar e obter perfis
# ---------------------------------------------------------------------------

def list_profiles(browser: str) -> List[BrowserProfile]:
    """
    Lista todos os perfis disponíveis para o navegador especificado.

    Parâmetros
    ----------
    browser : str
        "chrome", "edge", "firefox" ou "chromium".

    Retorna
    -------
    List[BrowserProfile]
        Lista de perfis encontrados no sistema.
    """
    browser = browser.lower()
    executable = find_browser_executable(browser)
    result: List[BrowserProfile] = []

    for user_data_dir in _get_user_data_dirs(browser):
        if not os.path.isdir(user_data_dir):
            continue

        if browser == "firefox":
            for name, abs_path in _list_firefox_profiles(user_data_dir):
                result.append(BrowserProfile(
                    browser=browser,
                    profile_name=name,
                    profile_dir=abs_path,
                    user_data_dir=user_data_dir,
                    executable=executable,
                ))
        else:
            for name, dir_name in _list_chromium_profiles(user_data_dir):
                result.append(BrowserProfile(
                    browser=browser,
                    profile_name=name,
                    profile_dir=dir_name,
                    user_data_dir=user_data_dir,
                    executable=executable,
                ))

    return result


def get_profile(browser: str, profile_name: Optional[str] = None) -> Optional[BrowserProfile]:
    """
    Retorna um perfil específico ou o perfil padrão do navegador.

    Parâmetros
    ----------
    browser : str
        "chrome", "edge", "firefox" ou "chromium".
    profile_name : str, opcional
        Nome do perfil desejado (ex: "Pessoa 1", "Default"). Se None, retorna
        o primeiro perfil encontrado (geralmente o padrão).

    Retorna
    -------
    BrowserProfile ou None
    """
    profiles = list_profiles(browser)
    if not profiles:
        return None

    if profile_name is None:
        # Prefere o perfil "Default" ou o primeiro disponível
        for p in profiles:
            if p.profile_dir.lower() in ("default", "default user"):
                return p
        return profiles[0]

    # Busca por nome exato (case-insensitive)
    for p in profiles:
        if p.profile_name.lower() == profile_name.lower():
            return p

    # Busca parcial
    for p in profiles:
        if profile_name.lower() in p.profile_name.lower():
            return p

    return None


def detect_available_browsers() -> Dict[str, Optional[str]]:
    """
    Detecta quais navegadores estão instalados no sistema.

    Retorna
    -------
    Dict[str, Optional[str]]
        Dicionário {nome_navegador: caminho_executável_ou_None}.
    """
    browsers = ["chrome", "edge", "firefox", "chromium"]
    return {b: find_browser_executable(b) for b in browsers}


# ---------------------------------------------------------------------------
# Integração com Playwright: construção dos kwargs de contexto/lançamento
# ---------------------------------------------------------------------------

def build_playwright_launch_kwargs(profile: BrowserProfile) -> Dict:
    """
    Constrói os argumentos necessários para lançar o Playwright com um perfil
    existente do navegador, reutilizando cookies e sessões salvas.

    Parâmetros
    ----------
    profile : BrowserProfile
        Perfil detectado pelo módulo.

    Retorna
    -------
    dict com chaves:
        - "channel": canal do Playwright (ex: "chrome", "msedge")
        - "executable_path": caminho do executável (se necessário)
        - "args": argumentos de linha de comando
        - "user_data_dir": diretório de dados (para persistent_context)
        - "browser_type": "chromium" | "firefox"
    """
    browser = profile.browser.lower()

    # Mapeamento para os canais suportados pelo Playwright
    channel_map = {
        "chrome": "chrome",
        "edge": "msedge",
        "chromium": None,   # Usa o Chromium embutido do Playwright
        "firefox": None,    # Firefox nativo
    }

    channel = channel_map.get(browser)
    browser_type = "firefox" if browser == "firefox" else "chromium"

    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--mute-audio",
    ]

    result = {
        "browser_type": browser_type,
        "channel": channel,
        "executable_path": profile.executable if not channel else None,
        "args": args,
        "user_data_dir": profile.user_data_dir,
        "profile_directory": profile.profile_dir,
    }

    return result


def print_available_profiles():
    """Imprime no terminal todos os perfis detectados no sistema (útil para debug)."""
    available = detect_available_browsers()
    print("\n=== Navegadores e Perfis Detectados ===")
    for browser, exe in available.items():
        status = exe if exe else "NÃO ENCONTRADO"
        print(f"\n[{browser.upper()}] {status}")
        profiles = list_profiles(browser)
        if profiles:
            for p in profiles:
                print(f"  - Perfil: '{p.profile_name}' | Dir: {p.profile_dir}")
        else:
            print("  (nenhum perfil encontrado)")
    print()
