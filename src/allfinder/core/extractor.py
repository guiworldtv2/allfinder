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
import json
import os
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

import validators
from crawl4ai import Crawl4AI
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
from allfinder.core.network_capture import NetworkCapture, DRMInfo


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
        await self._handle_drm_request(request)

    # -----------------------------------------------------------------------
    # Extração de metadados da página
    # -----------------------------------------------------------------------

    async def _interact_with_page(self, page: Page):
        """Simula interação do usuário para carregar conteúdo dinâmico (clicar em play, aceitar cookies)."""
        print("[*] Tentando interagir com a página...")
        try:
            # Tenta aceitar cookies ou fechar popups
            await page.locator("text=Aceitar", has_text="Aceitar").click(timeout=2000)
            print("[*] Clicou em 'Aceitar' cookies.")
        except Exception:
            pass
        try:
            await page.locator("text=Concordar", has_text="Concordar").click(timeout=2000)
            print("[*] Clicou em 'Concordar' cookies.")
        except Exception:
            pass
        try:
            await page.locator("button:has-text('Entendi')").click(timeout=2000)
            print("[*] Clicou em 'Entendi' (popup).")
        except Exception:
            pass

        # Tenta clicar em botões de play genéricos
        play_selectors = [
            "button[aria-label='Play']",
            "button[title='Play']",
            ".vjs-big-play-button",
            ".jw-icon-playback",
            ".play-button",
            ".video-play-button",
            ".flickity-button-icon", # Fox News specific
        ]
        for selector in play_selectors:
            try:
                await page.locator(selector).click(timeout=2000)
                print(f"[*] Clicou no botão de play: {selector}")
                await asyncio.sleep(1) # Pequena pausa para o player iniciar
                break
            except Exception:
                pass

        # Rola a página para garantir que elementos dinâmicos sejam carregados
        # Simula rolagem para baixo e para cima para carregar conteúdo lazy-loaded
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2) # Espera um pouco para o conteúdo carregar
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # Tenta mover o mouse para o centro da tela para ativar elementos (se houver)
        try:
            viewport_size = page.viewport_size
            if viewport_size:
                await page.mouse.move(viewport_size['width'] / 2, viewport_size['height'] / 2)
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # Espera por um curto período para que qualquer token ou stream dinâmico seja capturado
        await asyncio.sleep(3) # Aumenta o tempo de espera para captura de tokens/DRM

        print("[*] Interação com a página concluída.")

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

            if metadata:
                if metadata.get("title"):
                    self.page_title = metadata["title"].strip()
                thumbnail = (
                    metadata.get("og_image")
                    or metadata.get("twitter_image")
                    or metadata.get("poster")
                )
                if thumbnail and validators.url(thumbnail):
                    self.thumbnail_url = thumbnail

        except Exception as e:
            print(f"\n[!] Erro ao extrair metadados: {e}")

    # -----------------------------------------------------------------------
    # Lógica principal de extração
    # -----------------------------------------------------------------------

    async def extract(self, url: str, plugin: Any) -> Dict[str, Any]:
        """
        Executa a extração de mídia para uma única URL.

        Retorna um dicionário com as URLs encontradas, título e thumbnail.
        """
        if not self.validate_url(url):
            return {
                "urls": [],
                "title": "URL Inválida",
                "thumbnail": None,
                "drm_info": None,
            }

        self._profile = self._resolve_profile()

        if self._profile:
            launch_kwargs = build_playwright_launch_kwargs(self._profile, self.headless)
        else:
            launch_kwargs = build_playwright_launch_kwargs(None, self.headless)

        async with async_playwright() as p:
            browser_instance = p[self.browser_name]
            try:
                browser = await browser_instance.launch(**launch_kwargs)
            except Exception as e:
                if "looks like you are trying to access a browser that is not owned by this Playwright instance" in str(e):
                    print("[!] Tentando lançar navegador a partir do executável do perfil...")
                    if self._profile and self._profile.executable_path:
                        launch_kwargs['executable_path'] = self._profile.executable_path
                        browser = await browser_instance.launch(**launch_kwargs)
                    else:
                        raise e
                else:
                    raise e

            context = await self._create_browser_context(browser)
            page = await context.new_page()

            # Mascaramento de automação
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            # Captura de rede
            page.on("request", self._handle_request)

            try:
                print(f"[*] Navegando para: {url}")
                await page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")

                # Interage com a página para carregar conteúdo dinâmico
                await self._interact_with_page(page)


                # Lógica de interação do plugin
                if plugin:
                    await plugin.interact(page)

                # Loop de espera e atualização de metadados
                for _ in range(int(self.timeout / 2000)):
                    await self._update_metadata(page)
                    if self._capture.has_urls():
                        break
                    await asyncio.sleep(2)

            except Exception as e:
                print(f"\n[!] Erro durante a navegação/interação: {e}")

            finally:
                self.found_urls = self._capture.get_urls()
                drm_info = self._capture.get_drm_info()

                await browser.close()

        # Lógica de fallback com Crawl4AI
        if not self.found_urls and not self._capture.get_drm_info():
            crawl4ai_result = await self._run_crawl4ai_fallback(url)
            if crawl4ai_result["urls"]:
                self.found_urls.extend(crawl4ai_result["urls"])
            if crawl4ai_result["drm_info"]:
                self._capture._drm_info = crawl4ai_result["drm_info"]

        return {
            "urls": self.found_urls,
            "title": self.page_title,
            "thumbnail": self.thumbnail_url,
            "drm_info": self._capture.get_drm_info(),
        }

    async def _handle_drm_request(self, request: Request):
        """Processa requisições de DRM para extrair license_url, PSSH e KID."""
        # Widevine
        if "widevine" in request.url and request.method == "POST":
            try:
                post_data = request.post_data_buffer
                if post_data:
                    # Tenta decodificar como JSON (PlayReady)
                    try:
                        data = json.loads(post_data.decode("utf-8"))
                        if "challenge" in data:
                            # Isso é mais comum para PlayReady, mas alguns Widevine podem usar
                            self._capture._drm_info = DRMInfo(license_url=request.url, pssh=data.get("pssh"))
                    except json.JSONDecodeError:
                        # Se não for JSON, pode ser o formato binário do Widevine
                        # O PSSH geralmente é encontrado no corpo da requisição
                        pssh_match = re.search(b"\x08\x01\x12\x10(.{16})", post_data)
                        if pssh_match:
                            pssh_bytes = pssh_match.group(1)
                            # Converte para base64 se necessário, ou mantém como bytes
                            self._capture._drm_info = DRMInfo(license_url=request.url, pssh=pssh_bytes.hex())
            except Exception as e:
                print(f"[!] Erro ao processar requisição Widevine: {e}")

        # PlayReady
        elif "playready" in request.url and request.method == "POST":
            try:
                post_data = request.post_data_buffer
                if post_data:
                    # PlayReady geralmente envia um XML ou JSON
                    try:
                        data = json.loads(post_data.decode("utf-8"))
                        # Lógica para extrair PSSH/KID de JSON PlayReady
                        if "challenge" in data:
                            self._capture._drm_info = DRMInfo(license_url=request.url, pssh=data.get("pssh"))
                    except json.JSONDecodeError:
                        # Tenta como XML
                        if b"<Challenge>" in post_data:
                            # Lógica para extrair PSSH/KID de XML PlayReady
                            pssh_match = re.search(b"<Challenge>(.*?)</Challenge>", post_data)
                            if pssh_match:
                                pssh_base64 = pssh_match.group(1).decode("utf-8")
                                self._capture._drm_info = DRMInfo(license_url=request.url, pssh=pssh_base64)
            except Exception as e:
                print(f"[!] Erro ao processar requisição PlayReady: {e}")

        # Tenta extrair KID de URLs de licença (comum em alguns sistemas)
        kid_match = re.search(r"kid=([0-9a-fA-F]{32})", request.url)
        if kid_match:
            if not self._capture._drm_info:
                self._capture._drm_info = DRMInfo()
            self._capture._drm_info.kid = kid_match.group(1)

    async def _run_crawl4ai_fallback(self, url: str) -> Dict[str, Any]:
        """
        Executa o Crawl4AI como fallback para extrair informações da página
        quando a captura de rede padrão não encontra nada.
        """
        print("[!] Captura de rede não encontrou URLs de mídia ou DRM. Tentando Crawl4AI...")
        try:
            crawl4ai = Crawl4AI()
            result = await crawl4ai.extract(url)

            found_urls = []
            drm_info = None

            if result and result.get("media_urls"):
                for media_url in result["media_urls"]:
                    if ".m3u8" in media_url or ".mpd" in media_url:
                        found_urls.append(media_url)
                if found_urls:
                    print(f"[*] Crawl4AI encontrou {len(found_urls)} URLs de mídia.")

            if result and result.get("drm_info"):
                # Adapta o formato do Crawl4AI para o DRMInfo do allfinder
                c4ai_drm = result["drm_info"]
                drm_info = DRMInfo(
                    license_url=c4ai_drm.get("license_url"),
                    pssh=c4ai_drm.get("pssh"),
                    kid=c4ai_drm.get("kid"),
                )
                if drm_info.license_url or drm_info.pssh or drm_info.kid:
                    print("[*] Crawl4AI encontrou informações de DRM.")

            return {"urls": found_urls, "drm_info": drm_info}

        except Exception as e:
            print(f"[!] Erro ao executar Crawl4AI: {e}")
            return {"urls": [], "drm_info": None}

    async def _create_browser_context(self, browser: Browser) -> BrowserContext:
        """Cria um contexto de navegador com cookies e perfil, se aplicável."""
        context_kwargs = {}
        if self._profile and self._profile.user_data_dir:
            # Lança um contexto persistente se um perfil for usado
            context = await browser.new_context(
                user_agent=(self._profile.user_agent or None),
                viewport=self._profile.viewport or None,
                **context_kwargs
            )
        else:
            # Contexto normal (não persistente)
            context = await browser.new_context(**context_kwargs)

        # Carrega cookies
        cookies = self._parse_cookies_file()
        if self.cookies_from_browser:
            try:
                from browser_cookie3 import load
                domain = urllib.parse.urlparse(self.found_urls[0]).netloc if self.found_urls else ''
                cj = load(self.cookies_from_browser, domain_name=domain)
                for cookie in cj:
                    cookies.append({
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain,
                        "path": cookie.path,
                        "expires": cookie.expires or -1,
                        "httpOnly": cookie.has_nonstandard_attr("HttpOnly"),
                        "secure": cookie.secure,
                    })
            except ImportError:
                print("[!] Para usar --cookies-from-browser, instale 'browser-cookie3'.")
            except Exception as e:
                print(f"[!] Erro ao carregar cookies do navegador: {e}")

        if cookies:
            await context.add_cookies(cookies)

        return context
    async def _create_browser_context(self, browser: Browser) -> BrowserContext:
