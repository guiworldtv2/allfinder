
import asyncio
import json
import os
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Type
import importlib.util

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
        plugin_name: Optional[str] = None,
    ):
        self.headless = headless
        self.timeout = timeout
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self.browser_name = browser.lower()
        self.profile_name = profile_name
        self.use_profile = use_profile
        self.plugin_name = plugin_name
        self.plugin_instance = None

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
        if isinstance(profile, BrowserProfile):
            print(f"[*] Usando perfil {profile.profile_name} do {profile.browser.upper()}.")
            return profile
        else:
            print(
                f"[!] Perfil {self.profile_name} não encontrado para {self.browser_name}. "
                "Usando navegador sem perfil."
            )
            return None

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
        await self._capture.handle_request_async(request)
        self.found_urls = self._capture.get_urls()


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



    async def _create_browser_context(self, playwright_instance) -> BrowserContext:
        """
        Cria e configura um contexto de navegador com base nas opções fornecidas.
        """
        self._profile = self._resolve_profile() # Resolve o perfil aqui

        launch_kwargs = build_playwright_launch_kwargs(self._profile, self.headless)
        browser_type = getattr(playwright_instance, self.browser_name)

        browser_context: BrowserContext
        user_data_dir: Optional[str] = None

        if self.use_profile and self._profile is not None:
            user_data_dir = self._profile.user_data_dir
        elif self.use_profile and self._profile is None:
            print("[!] use_profile é True, mas _profile é None. Criando diretório de dados de usuário temporário.")
            temp_user_data_dir = os.path.join(os.getcwd(), "temp_user_data_allfinder")
            os.makedirs(temp_user_data_dir, exist_ok=True)
            user_data_dir = temp_user_data_dir

        if user_data_dir:
            browser_context = await browser_type.launch_persistent_context(
                user_data_dir,
                **launch_kwargs,
                timeout=self.timeout,
            )
        else:
            browser = await browser_type.launch(**launch_kwargs)
            browser_context = await browser.new_context()

        # Configura cookies
        if self.cookies_from_browser:
            # Importar cookies do navegador (ainda não implementado)
            print(f"[!] Importação de cookies de {self.cookies_from_browser} não implementada.")
        elif self.cookies_file:
            cookies = self._parse_cookies_file()
            if cookies:
                await browser_context.add_cookies(cookies)

        return browser_context

    async def extract(
        self,
        url: str,
    ) -> Dict[str, Any]:
        """
        Extrai URLs de mídia de uma página web.

        Parâmetros
        ----------
        url : str
            A URL da página para extrair.
        plugin : Callable[[Page], Any], opcional
            Uma função assínrona que interage com a página para revelar conteúdo.

        Retorna
        -------
        Dict[str, Any]
            Um dicionário contendo as URLs de mídia encontradas, título e thumbnail.
        """
        if not self.validate_url(url):
            print(f"[!] URL inválida: {url}")
            return {"title": "Erro", "urls": [], "thumbnail": None, "drm_info": None}

        self._capture.reset()
        self.found_urls = []
        self.thumbnail_url = None
        self.page_title = "Stream"

        async with async_playwright() as p:
            browser_context = await self._create_browser_context(p)
            page = await browser_context.new_page()

            # Configura o timeout da página
            page.set_default_timeout(self.timeout)

            # Adiciona o handler de requisições
            page.on("request", self._handle_request)

            # Carrega e instancia o plugin, se houver
            if self.plugin_name:
                try:
                    plugin_path = os.path.join(os.path.dirname(__file__), "..", "plugins", f"{self.plugin_name}.py")
                    spec = importlib.util.spec_from_file_location(self.plugin_name, plugin_path)
                    if spec and spec.loader:
                        plugin_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(plugin_module)
                        # Assumindo que a classe do plugin tem o mesmo nome do arquivo (camel case)
                        plugin_class_name = "".join(word.capitalize() for word in self.plugin_name.split("_")) + "Plugin"

                        plugin_class = getattr(plugin_module, plugin_class_name)
                        self.plugin_instance = plugin_class()
                        print(f"[*] Plugin ", self.plugin_name, " carregado com sucesso.")
                    else:
                        print(f"[!] Não foi possível carregar o plugin: {self.plugin_name}")
                except Exception as e:
                    print(f"[!] Erro ao carregar plugin {self.plugin_name}: {e}")

            try:
                print(f"[*] Navegando para: {url}")
                await page.goto(url, wait_until="domcontentloaded")
                print(f"[*] Navegação concluída para: {url}")

                # Interage com a página se um plugin for fornecido
                if self.plugin_instance:
                    print("[*] Executando plugin de interação...")
                    await self.plugin_instance.interact(page)

                # Interação genérica (clicar em play, aceitar cookies)
                await self._interact_with_page(page)

                # Espera por um curto período para capturar requisições adicionais
                await asyncio.sleep(5) # Ajuste conforme necessário

                # Tenta obter o título da página
                self.page_title = await page.title()

                # Tenta obter a thumbnail (primeira imagem visível ou meta tag)
                try:
                    thumbnail_element = await page.query_selector("img")
                    if thumbnail_element:
                        self.thumbnail_url = await thumbnail_element.get_attribute("src")
                except Exception:
                    pass

                # Loop para esperar por URLs e metadados
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < (self.timeout / 1000):
                    if self.found_urls and self.page_title != "Stream":
                        break
                    await asyncio.sleep(1)

            except Exception as e:
                print(f"[!] Erro durante a extração: {e}")
            finally:
                await browser_context.close()

        # Limpa URLs duplicadas e retorna
        unique_urls = list(set(self.found_urls))
        
        drm_info = self._capture.get_drm_info()
        drm_info_list = []
        if drm_info:
            drm_info_list.append({
                "license_url": drm_info.license_url,
                "pssh": drm_info.pssh,
                "kid": drm_info.kid
            })

        return {
            "title": self.page_title,
            "urls": unique_urls,
            "thumbnail": self.thumbnail_url,
            "drm_info": drm_info_list,
        }


# ---------------------------------------------------------------------------
# Função de entrada para execução assíncrona
# ---------------------------------------------------------------------------

async def run_extractor(
    url: str,
    headless: bool = True,
    timeout: int = 30000,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
    browser: str = "chromium",
    profile_name: Optional[str] = None,
    use_profile: bool = False,
    plugin_name: Optional[str] = None,
) -> Dict[str, Any]:
    extractor = M3U8Extractor(
        headless=headless,
        timeout=timeout,
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
        browser=browser,
        profile_name=profile_name,
        use_profile=use_profile,
        plugin_name=plugin_name,
    )
    return await extractor.extract(url)
