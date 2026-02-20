import asyncio
import re
import sys
import subprocess
from typing import Optional, List, Callable
from playwright.async_api import async_playwright, Request, Page, Browser

def ensure_playwright_browsers():
    """Garante que os navegadores e dependências do sistema do Playwright estejam instalados."""
    try:
        # Tenta instalar o chromium e as dependências do sistema
        # O install-deps é crucial para ambientes como o Google Colab
        print("[*] Verificando navegadores e dependências do sistema...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True, capture_output=True)
        subprocess.run([sys.executable, "-m", "playwright", "install-deps", "chromium"], check=True, capture_output=True)
    except Exception:
        # Se falhar silenciosamente, tenta de forma visível
        print("[*] Instalando dependências (isso pode levar um momento no Colab)...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install-deps", "chromium"], check=True)

class M3U8Extractor:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.found_urls: List[str] = []

    async def _handle_request(self, request: Request):
        url = request.url
        # Filtro mais inteligente para evitar telemetria e focar em vídeo real
        if ".m3u8" in url.lower():
            # Ignora padrões comuns de telemetria/analytics
            blacklist = ["youbora", "analytics", "telemetry", "log", "metrics", "heartbeat"]
            if not any(word in url.lower() for word in blacklist):
                if url not in self.found_urls:
                    self.found_urls.append(url)
                    # Destaca se for uma playlist principal
                    if "playlist.m3u8" in url.lower() or "chunklist.m3u8" in url.lower():
                        print(f"[!] STREAM DETECTADO: {url}")
                    else:
                        print(f"[+] M3U8 encontrado: {url}")

    async def extract(self, url: str, interaction_func: Optional[Callable[[Page], asyncio.Future]] = None) -> List[str]:
        ensure_playwright_browsers()
        
        self.found_urls = []
        async with async_playwright() as p:
            try:
                # No Colab/Docker, o argumento --no-sandbox é frequentemente necessário
                browser: Browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
            except Exception as e:
                print(f"[!] Erro ao iniciar navegador: {e}. Tentando reinstalar dependências...")
                ensure_playwright_browsers()
                browser: Browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page: Page = await context.new_page()
            page.on("request", self._handle_request)
            
            print(f"[*] Navegando para: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=self.timeout)
                if interaction_func:
                    print("[*] Executando interações customizadas...")
                    await interaction_func(page)
                else:
                    print("[*] Aguardando carregamento automático do stream (15s)...")
                    await asyncio.sleep(15)
            except Exception as e:
                print(f"[!] Erro durante a extração: {e}")
            finally:
                await browser.close()
        
        return self.found_urls
