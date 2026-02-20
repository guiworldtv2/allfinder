import asyncio
import re
import sys
import subprocess
from typing import Optional, List, Callable
from playwright.async_api import async_playwright, Request, Page, Browser

def ensure_playwright_browsers():
    """Garante que os navegadores e dependências do sistema do Playwright estejam instalados."""
    try:
        # Tenta verificar se já está instalado para ser mais rápido
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True, capture_output=True)
    except Exception:
        print("[*] Verificando/Instalando dependências do navegador...")
        # No Colab, precisamos de sudo para install-deps
        is_colab = 'google.colab' in sys.modules or subprocess.run(['which', 'sudo'], capture_output=True).returncode == 0
        cmd_prefix = ['sudo'] if is_colab else []
        
        subprocess.run(cmd_prefix + [sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run(cmd_prefix + [sys.executable, "-m", "playwright", "install-deps", "chromium"], check=True)

class M3U8Extractor:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.found_urls: List[str] = []

    async def _handle_request(self, request: Request):
        url = request.url
        if ".m3u8" in url.lower():
            blacklist = ["youbora", "analytics", "telemetry", "log", "metrics", "heartbeat", "omtrdc"]
            if not any(word in url.lower() for word in blacklist):
                if url not in self.found_urls:
                    self.found_urls.append(url)
                    if "playlist.m3u8" in url.lower() or "chunklist.m3u8" in url.lower():
                        print(f"[!] STREAM DETECTADO: {url[:100]}...")
                    else:
                        print(f"[+] M3U8 encontrado: {url[:100]}...")

    async def extract(self, url: str, interaction_func: Optional[Callable[[Page], asyncio.Future]] = None) -> List[str]:
        ensure_playwright_browsers()
        
        self.found_urls = []
        async with async_playwright() as p:
            try:
                browser: Browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
            except Exception as e:
                print(f"[!] Erro ao iniciar navegador: {e}. Tentando reinstalar...")
                ensure_playwright_browsers()
                browser: Browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page: Page = await context.new_page()
            page.on("request", self._handle_request)
            
            print(f"[*] Navegando para: {url}")
            try:
                # Mudança estratégica: wait_until="domcontentloaded" é muito mais rápido que "networkidle"
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                
                # Executa interações ou espera um pouco
                if interaction_func:
                    print("[*] Executando interações...")
                    await interaction_func(page)
                else:
                    # Espera ativa: verifica a cada segundo se já encontramos algo
                    print("[*] Monitorando rede por até 30s...")
                    for _ in range(30):
                        if any("playlist.m3u8" in u.lower() for u in self.found_urls):
                            print("[*] Link principal encontrado! Finalizando...")
                            break
                        await asyncio.sleep(1)
            except Exception as e:
                # Se houver timeout mas já encontramos links, ignoramos o erro
                if self.found_urls:
                    print(f"[*] Timeout atingido, mas {len(self.found_urls)} links foram capturados.")
                else:
                    print(f"[!] Erro durante a extração: {e}")
            finally:
                await browser.close()
        
        return self.found_urls
