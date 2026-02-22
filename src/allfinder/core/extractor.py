"""
extractor.py
============
Módulo principal de extração de URLs de mídia (M3U8/MPD) via automação de
navegador com Playwright.

Melhorias em relação à versão anterior:
- Integração com browser_profile.py: suporte a múltiplos navegadores (Chrome,
  Edge, Firefox, Chromium) com reutilização de perfis existentes do usuário.
- Integração com network_capture.py: captura de tráfego de rede mais robusta,
  com blacklist ampliada, normalização e priorização de streams.
- Suporte a contexto persistente do Playwright para reutilização de sessão.
- Mascaramento de automação (--disable-blink-features=AutomationControlled).
- Compatibilidade total com o fluxo anterior (cookies, yt-dlp, plugins).
"""

import asyncio
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

import validators
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Request,
    async_playwright,
)

from allfinder.core.browser_profile import (
    BrowserProfile,
    build_playwright_launch_kwargs,
    detect_available_browsers,
    get_profile,
)
from allfinder.core.network_capture import NetworkCapture


# ---------------------------------------------------------------------------
# Instalação automática dos navegadores do Playwright
# ---------------------------------------------------------------------------

def ensure_playwright_browsers():
    """Garante que os navegadores do Playwright estejam instalados.

    Compatível com Windows, Linux e macOS. No Windows, não tenta usar
    'sudo' nem 'apt-get', pois esses comandos não existem.
    """
    is_windows = sys.platform.startswith("win")
    is_colab = "google.colab" in sys.modules
    env = os.environ.copy()

    # Verifica se o Chromium já está instalado
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--dry-run"],
            capture_output=True, text=True,
        )
        if "browser is already installed" in result.stdout.lower():
            return
    except Exception:
        pass

    print("[*] Instalando o Chromium do Playwright (isso pode levar alguns minutos)...")

    if is_windows:
        # No Windows não existe sudo nem apt-get
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True, env=env,
            )
            print("[✓] Chromium instalado com sucesso!")
        except subprocess.CalledProcessError as e:
            print(f"[!] Erro ao instalar o Chromium: {e}")
            print("[!] Tente manualmente: python -m playwright install chromium")
    else:
        # Linux / macOS — tenta usar sudo se disponível
        has_sudo = subprocess.run(
            ["which", "sudo"], capture_output=True
        ).returncode == 0
        env["DEBIAN_FRONTEND"] = "noninteractive"
        cmd_prefix = ["sudo", "-E"] if (is_colab or has_sudo) else []

        try:
            subprocess.run(
                cmd_prefix + [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True, env=env,
            )
            if is_colab or has_sudo:
                subprocess.run(
                    ["sudo", "-E", "apt-get", "update", "-y"],
                    check=True, env=env, capture_output=True,
                )
            subprocess.run(
                cmd_prefix + [sys.executable, "-m", "playwright", "install-deps", "chromium"],
                check=True, env=env,
            )
            print("[✓] Navegador e dependências instalados com sucesso!")
        except subprocess.CalledProcessError as e:
            print(f"[!] Erro durante a instalação: {e}")
            try:
                subprocess.run(
                    cmd_prefix + [sys.executable, "-m", "playwright", "install-deps", "chromium"],
                    check=True, env=env,
                )
            except Exception:
                print("[!] Falha ao instalar dependências. O navegador pode não funcionar corretamente.")


# ---------------------------------------------------------------------------
# Classe principal: M3U8Extractor
# ---------------------------------------------------------------------------

class M3U8Extractor:
    """
    Extrator de URLs de mídia (M3U8/MPD) via automação de navegador.

    Parâmetros
    ----------
    headless : bool
        Se True (padrão), o navegador roda sem interface gráfica.
    timeout : int
        Tempo limite em milissegundos para operações do navegador.
    cookies_from_browser : str, opcional
        Nome do navegador para importar cookies ("chrome", "edge").
    cookies_file : str, opcional
        Caminho para um arquivo de cookies (.json ou .txt Netscape).
    browser : str, opcional
        Navegador a ser usado: "chrome", "edge", "firefox", "chromium" (padrão).
        Quando combinado com use_profile=True, reutiliza a sessão existente.
    profile_name : str, opcional
        Nome do perfil do navegador a ser reutilizado (ex: "Pessoa 1", "Default").
        Requer use_profile=True.
    use_profile : bool
        Se True, reutiliza um perfil existente do navegador para acessar sites
        que exigem login sem precisar autenticar novamente.
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        cookies_from_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        browser: str = "chromium",
        profile_name: Optional[str] = None,
        use_profile: bool = False,
    ):
        self.headless = headless
        self.timeout = timeout
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self.browser_name = browser.lower()
        self.profile_name = profile_name
        self.use_profile = use_profile

        # Estado interno (mantido para compatibilidade com plugins existentes)
        self.found_urls: List[str] = []
        self.thumbnail_url: Optional[str] = None
        self.page_title: str = "Stream"

        # Captura de rede aprimorada
        self._capture = NetworkCapture(deduplicate=True, normalize=True)

        # Perfil detectado (preenchido em _resolve_profile)
        self._profile: Optional[BrowserProfile] = None

    # -----------------------------------------------------------------------
    # Validação de URL
    # -----------------------------------------------------------------------

    def validate_url(self, url: str) -> bool:
        """Valida se a URL é segura e bem formatada."""
        if not validators.url(url):
            return False
        if not url.lower().startswith(("http://", "https://")):
            return False
        parsed_url = re.search(r"https?://([^/]+)", url)
        if parsed_url:
            host = parsed_url.group(1).lower()
            if any(x in host for x in ["localhost", "127.0.0.1", "0.0.0.0", "192.168.", "10.", "172.16."]):
                return False
        return True

    # -----------------------------------------------------------------------
    # Resolução de perfil de navegador
    # -----------------------------------------------------------------------

    def _resolve_profile(self) -> Optional[BrowserProfile]:
        """
        Detecta e retorna o perfil de navegador a ser usado.
        Retorna None se use_profile=False ou se nenhum perfil for encontrado.
        """
        if not self.use_profile:
            return None

        profile = get_profile(self.browser_name, self.profile_name)
        if profile:
            print(f"[*] Usando perfil '{profile.profile_name}' do {profile.browser.upper()}.")
        else:
            print(
                f"[!] Perfil '{self.profile_name}' não encontrado para {self.browser_name}. "
                "Usando navegador sem perfil."
            )
        return profile

    # -----------------------------------------------------------------------
    # Parsing de cookies
    # -----------------------------------------------------------------------

    def _parse_cookies_file(self) -> List[Dict[str, Any]]:
        """Lê cookies de arquivos .json ou .txt (formato Netscape) e limpa campos inválidos."""
        if not self.cookies_file or not os.path.exists(self.cookies_file):
            return []
        cookies = []
        try:
            if self.cookies_file.endswith(".json"):
                with open(self.cookies_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        cookies = data
                    elif isinstance(data, dict) and "cookies" in data:
                        cookies = data["cookies"]
            else:
                with open(self.cookies_file, "r") as f:
                    for line in f:
                        if line.startswith("#") or not line.strip():
                            continue
                        parts = line.strip().split("\t")
                        if len(parts) >= 7:
                            cookies.append({
                                "name": parts[5],
                                "value": parts[6],
                                "domain": parts[0],
                                "path": parts[2],
                                "expires": int(parts[4]) if parts[4].isdigit() else -1,
                                "httpOnly": parts[1].upper() == "TRUE",
                                "secure": parts[3].upper() == "TRUE",
                            })

            cleaned: List[Dict[str, Any]] = []
            valid_samesite = ["Strict", "Lax", "None"]
            for cookie in cookies:
                if "sameSite" in cookie and cookie["sameSite"] not in valid_samesite:
                    del cookie["sameSite"]
                for bool_field in ["httpOnly", "secure", "session"]:
                    if bool_field in cookie:
                        cookie[bool_field] = str(cookie[bool_field]).lower() == "true"
                cleaned.append(cookie)
            return cleaned

        except Exception as e:
            print(f"[!] Erro ao ler/limpar arquivo de cookies: {e}")
        return []

    # -----------------------------------------------------------------------
    # Limpeza de URLs com redirecionamento embutido (legado)
    # -----------------------------------------------------------------------

    def _clean_url(self, url: str) -> str:
        """Extrai a URL real se estiver embutida em parâmetros de rastreamento."""
        try:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            url_params = ["ep.URL", "url", "link", "target", "redir"]
            for param in url_params:
                if param in params:
                    potential_url = params[param][0]
                    if ".m3u8" in potential_url.lower() and self.validate_url(potential_url):
                        return potential_url
        except Exception:
            pass
        return url

    # -----------------------------------------------------------------------
    # Handler de requisições (mantido para compatibilidade com plugins)
    # -----------------------------------------------------------------------

    async def _handle_request(self, request: Request):
        """Callback legado para o evento 'request'. Delega para o NetworkCapture."""
        self._capture._process_url(request.url)
        self.found_urls = self._capture.get_urls()

    # -----------------------------------------------------------------------
    # Extração de metadados da página
    # -----------------------------------------------------------------------

    async def _update_metadata(self, page: Page):
        """Extrai título e thumbnail da página via JavaScript injetado."""
        try:
            metadata = await page.evaluate("""() => {
                const getMeta = (name) => {
                    const el = document.querySelector(
                        `meta[property="${name}"], meta[name="${name}"],
                         meta[property="og:${name}"], meta[name="twitter:${name}"]`
                    );
                    return el ? el.getAttribute('content') : null;
                };
                const titleSelectors = [
                    'h1.video-title', 'h1.LiveVideo__Title', 'h1.video-info__title',
                    '.VideoInfo__Title', '.video-title-container h1', '.headline', 'h1'
                ];
                let foundTitle = null;
                for (const sel of titleSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 5) {
                        foundTitle = el.innerText.trim();
                        break;
                    }
                }
                const metaTitle = getMeta('title') || getMeta('og:title') || getMeta('twitter:title');
                return {
                    title: foundTitle || metaTitle || document.title,
                    og_image: getMeta('og:image'),
                    twitter_image: getMeta('twitter:image'),
                    poster: document.querySelector('video')
                        ? document.querySelector('video').getAttribute('poster')
                        : null
                };
            }""")

            if metadata.get("title") and len(metadata["title"]) > 5:
                clean_title = re.sub(r"\s*\|\s*.*$", "", metadata["title"])
                clean_title = re.sub(
                    r"\s*-\s*(Fox News|ABC News|Globoplay|NBC News).*$",
                    "", clean_title, flags=re.IGNORECASE,
                )
                self.page_title = clean_title.strip()

            if not self.thumbnail_url or "glbimg.com" not in self.thumbnail_url:
                new_thumb = (
                    metadata.get("og_image")
                    or metadata.get("twitter_image")
                    or metadata.get("poster")
                )
                if new_thumb:
                    self.thumbnail_url = new_thumb

        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Extração via yt-dlp
    # -----------------------------------------------------------------------

    def _extract_with_ytdlp(self, url: str) -> Optional[str]:
        """Tenta extrair o link m3u8 usando yt-dlp (útil para YouTube e outros sites complexos)."""
        try:
            subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
            cmd = ["yt-dlp", "-g", "-f", "best", url]
            if self.cookies_file:
                cmd.extend(["--cookies", self.cookies_file])
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                potential_url = result.stdout.strip()
                if ".m3u8" in potential_url.lower() or "manifest" in potential_url.lower():
                    return potential_url
        except Exception:
            pass
        return None

    # -----------------------------------------------------------------------
    # Construção do contexto Playwright (com ou sem perfil)
    # -----------------------------------------------------------------------

    async def _create_browser_and_context(self, playwright_instance):
        """
        Cria o navegador e o contexto do Playwright.

        Se use_profile=True e um perfil for encontrado, usa um contexto
        persistente que reutiliza cookies e sessões do navegador real.
        Caso contrário, usa o fluxo padrão (contexto efêmero).

        Retorna (browser_ou_none, context, is_persistent).
        """
        profile = self._resolve_profile()
        self._profile = profile

        common_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--mute-audio",
        ]

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        if profile:
            # Modo com perfil: contexto persistente
            kwargs = build_playwright_launch_kwargs(profile)
            browser_type_name = kwargs["browser_type"]
            browser_type = getattr(playwright_instance, browser_type_name)

            launch_kwargs: Dict[str, Any] = {
                "headless": self.headless,
                "args": common_args,
            }
            if kwargs.get("channel"):
                launch_kwargs["channel"] = kwargs["channel"]
            elif kwargs.get("executable_path"):
                launch_kwargs["executable_path"] = kwargs["executable_path"]

            context = await browser_type.launch_persistent_context(
                user_data_dir=kwargs["user_data_dir"],
                **launch_kwargs,
            )
            return None, context, True

        else:
            # Modo padrão: navegador efêmero
            browser_map = {
                "chrome": ("chromium", "chrome"),
                "edge": ("chromium", "msedge"),
                "firefox": ("firefox", None),
                "chromium": ("chromium", None),
            }
            browser_type_name, channel = browser_map.get(
                self.browser_name, ("chromium", None)
            )
            browser_type = getattr(playwright_instance, browser_type_name)

            launch_kwargs = {
                "headless": self.headless,
                "args": common_args,
            }
            if channel:
                launch_kwargs["channel"] = channel

            browser: Browser = await browser_type.launch(**launch_kwargs)
            context = await browser.new_context(user_agent=user_agent)
            return browser, context, False

    # -----------------------------------------------------------------------
    # Método principal de extração
    # -----------------------------------------------------------------------

    async def extract(
        self,
        url: str,
        interaction_func: Optional[Callable[[Page], asyncio.Future]] = None,
    ) -> Dict[str, Any]:
        """
        Extrai URLs de mídia de uma página web.

        No Windows, o Playwright requer o SelectorEventLoop, mas o Jupyter
        e o Python 3.8+ usam ProactorEventLoop por padrão. Para contornar
        isso, a extração é executada em uma thread separada com seu próprio
        SelectorEventLoop quando rodando no Windows.

        Parâmetros
        ----------
        url : str
            URL da página de streaming.
        interaction_func : callable, opcional
            Função assíncrona que recebe a Page e realiza interações (ex: clicar no play).

        Retorna
        -------
        dict com chaves "title", "m3u8_urls" e "thumbnail".
        """
        if not self.validate_url(url):
            raise ValueError(f"URL inválida ou insegura: {url}")

        # No Windows, roda em thread separada com SelectorEventLoop para
        # contornar a incompatibilidade do ProactorEventLoop com o Playwright.
        if sys.platform.startswith("win"):
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = await loop.run_in_executor(
                    pool,
                    lambda: _run_in_selector_loop(self._extract_core, url, interaction_func),
                )
            return result

        # Delega para _extract_core (reutilizado pelo path Windows acima)
        return await self._extract_core(url, interaction_func)

    async def _extract_core(
        self,
        url: str,
        interaction_func: Optional[Callable[[Page], asyncio.Future]] = None,
    ) -> Dict[str, Any]:
        """Núcleo da extração — roda dentro do event loop correto."""

        # Tenta yt-dlp primeiro para YouTube
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            ytdl_url = self._extract_with_ytdlp(url)
            if ytdl_url:
                title = "YouTube Live"
                try:
                    res = subprocess.run(
                        ["yt-dlp", "--get-title", url], capture_output=True, text=True
                    )
                    if res.returncode == 0:
                        title = res.stdout.strip()
                except Exception:
                    pass
                vid_id = url.split("v=")[-1] if "v=" in url else "live"
                return {
                    "title": title,
                    "m3u8_urls": [ytdl_url],
                    "thumbnail": f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg",
                }

        ensure_playwright_browsers()

        # Reinicia o estado
        self._capture.reset()
        self.found_urls = []
        self.thumbnail_url = None
        self.page_title = "Stream"

        async with async_playwright() as p:
            browser, context, is_persistent = await self._create_browser_and_context(p)

            # Carrega cookies de arquivo (apenas em contexto não-persistente)
            if not is_persistent:
                file_cookies = self._parse_cookies_file()
                if file_cookies:
                    await context.add_cookies(file_cookies)
                    print(f"[*] {len(file_cookies)} cookies carregados do arquivo.")

            page: Page = await context.new_page()

            # Mascara a propriedade navigator.webdriver
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # Registra o handler de captura de rede
            page.on("request", lambda req: self._capture._process_url(req.url))

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                # Thumbnail específica do Globo (por ID de vídeo na URL)
                if "globo.com" in url:
                    video_id_match = re.search(r"/v/(\d+)", url)
                    if video_id_match:
                        self.thumbnail_url = (
                            f"https://s04.video.glbimg.com/x720/{video_id_match.group(1)}.jpg"
                        )

                # Executa a função de interação do plugin
                if interaction_func:
                    await interaction_func(page)

                # Aguarda e coleta streams
                for i in range(45):
                    await self._update_metadata(page)
                    self.found_urls = self._capture.get_urls()

                    has_priority = self._capture.has_priority_stream()
                    if has_priority and self.page_title != "Stream" and i > 5:
                        break

                    await asyncio.sleep(1)

                self.found_urls = self._capture.get_urls()

            except Exception as e:
                self.found_urls = self._capture.get_urls()
                if not self.found_urls:
                    raise e

            finally:
                if is_persistent:
                    await context.close()
                else:
                    if browser:
                        await browser.close()

        return {
            "title": self.page_title.strip(),
            "m3u8_urls": self.found_urls,
            "thumbnail": self.thumbnail_url,
        }


# ---------------------------------------------------------------------------
# Função auxiliar para execução em SelectorEventLoop (Windows)
# ---------------------------------------------------------------------------

def _run_in_selector_loop(coro_func, *args, **kwargs):
    """
    Executa uma coroutine em um novo SelectorEventLoop.

    Usada no Windows para contornar a incompatibilidade entre o
    ProactorEventLoop (padrão do Windows/Jupyter) e o Playwright,
    que requer o SelectorEventLoop para criar subprocessos assíncronos.

    Esta função é chamada dentro de uma thread separada via ThreadPoolExecutor,
    garantindo que o loop principal do Jupyter não seja afetado.

    Parâmetros
    ----------
    coro_func : coroutine function
        Função assíncrona a ser executada (ex: extractor._extract_core).
    *args, **kwargs
        Argumentos passados para coro_func.

    Retorna
    -------
    O resultado da coroutine.
    """
    # Cria um SelectorEventLoop explícito nesta thread
    loop = asyncio.SelectorEventLoop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_func(*args, **kwargs))
    finally:
        loop.close()
