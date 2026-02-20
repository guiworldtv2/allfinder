import asyncio
import re
import sys
import subprocess
from typing import Optional, List, Callable, Dict, Any
from playwright.async_api import async_playwright, Request, Page, Browser

def ensure_playwright_browsers():
    """Garante que os navegadores e dependências do sistema do Playwright estejam instalados."""
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True, capture_output=True)
    except Exception:
        print("[*] Verificando/Instalando dependências do navegador...")
        is_colab = 'google.colab' in sys.modules or subprocess.run(['which', 'sudo'], capture_output=True).returncode == 0
        cmd_prefix = ['sudo'] if is_colab else []
        subprocess.run(cmd_prefix + [sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run(cmd_prefix + [sys.executable, "-m", "playwright", "install-deps", "chromium"], check=True)

class M3U8Extractor:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.found_urls: List[str] = []
        self.thumbnail_url: Optional[str] = None

    async def _handle_request(self, request: Request):
        url = request.url
        if ".m3u8" in url.lower():
            blacklist = ["youbora", "analytics", "telemetry", "log", "metrics", "heartbeat", "omtrdc", "hotjar", "scorecardresearch"]
            if not any(word in url.lower() for word in blacklist):
                if url not in self.found_urls:
                    self.found_urls.append(url)
                    if "playlist.m3u8" in url.lower() or "chunklist.m3u8" in url.lower():
                        print(f"[!] STREAM DETECTADO: {url[:80]}...")

    async def extract(self, url: str, interaction_func: Optional[Callable[[Page], asyncio.Future]] = None) -> Dict[str, Any]:
        ensure_playwright_browsers()
        
        self.found_urls = []
        self.thumbnail_url = None
        page_title = "Stream"
        
        async with async_playwright() as p:
            try:
                browser: Browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
            except Exception:
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
                # Carrega a página até o DOM estar pronto
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                
                # Lógica de Thumbnail específica para Globo baseada no ID do vídeo
                if "globo.com" in url:
                    video_id_match = re.search(r'/v/(\d+)', url)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        self.thumbnail_url = f"https://s04.video.glbimg.com/x720/{video_id}.jpg"
                        print(f"[*] Thumbnail Globo detectada: {self.thumbnail_url}")

                # Espera curta para garantir que títulos dinâmicos carreguem
                await asyncio.sleep(3)
                
                # Extração de Metadados
                metadata = await page.evaluate("""() => {
                    const getMeta = (name) => {
                        const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"], meta[property="og:${name}"]`);
                        return el ? el.getAttribute('content') : null;
                    };
                    
                    const h1 = document.querySelector('h1.video-title, h1.LiveVideo__Title, h1.title, h1.video-info__title');
                    const metaTitle = getMeta('title') || getMeta('og:title') || getMeta('twitter:title');
                    
                    return {
                        title: h1 ? h1.innerText : (metaTitle || document.title),
                        og_image: getMeta('og:image'),
                        twitter_image: getMeta('twitter:image'),
                        poster: document.querySelector('video') ? document.querySelector('video').getAttribute('poster') : null
                    };
                }""")
                
                page_title = metadata.get('title') or page_title
                if not self.thumbnail_url:
                    self.thumbnail_url = metadata.get('og_image') or metadata.get('twitter_image') or metadata.get('poster')

                if interaction_func:
                    print("[*] Executando interações...")
                    await interaction_func(page)
                else:
                    print("[*] Monitorando rede por streams...")
                    # Espera ativa por até 30 segundos, mas sem fechar imediatamente ao achar
                    # para dar tempo de outras requisições de metadados se necessário
                    for _ in range(30):
                        if any("playlist.m3u8" in u.lower() for u in self.found_urls):
                            # Espera um respiro final
                            await asyncio.sleep(2)
                            break
                        await asyncio.sleep(1)
            except Exception as e:
                if not self.found_urls:
                    print(f"[!] Erro durante a extração: {e}")
            finally:
                await browser.close()
        
        return {
            "title": page_title.strip(),
            "m3u8_urls": self.found_urls,
            "thumbnail": self.thumbnail_url
        }
