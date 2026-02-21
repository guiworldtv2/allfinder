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
        self.page_title: str = "Stream"

    async def _handle_request(self, request: Request):
        url = request.url
        if ".m3u8" in url.lower():
            # Lista negra estendida para ignorar propagandas e telemetria
            blacklist = [
                "youbora", "analytics", "telemetry", "log", "metrics", "heartbeat", 
                "omtrdc", "hotjar", "scorecardresearch", "doubleclick", "ads", 
                "adnxs", "fwmrm.net", "googleads", "amazon-adsystem", "casalemedia",
                "adnxs", "advertising", "segment", "moatads", "krxd"
            ]
            
            if not any(word in url.lower() for word in blacklist):
                if url not in self.found_urls:
                    # Prioriza links que parecem ser o conteúdo real (master, index, playlists longas)
                    is_likely_main = any(word in url.lower() for word in ["master", "index", "playlist", "chunklist"])
                    
                    if is_likely_main:
                        # Coloca no início da lista se for provável que seja o principal
                        self.found_urls.insert(0, url)
                        print(f"[!] STREAM PRINCIPAL DETECTADO: {url[:80]}...")
                    else:
                        self.found_urls.append(url)
                        print(f"[+] M3U8 encontrado: {url[:80]}...")

    async def _update_metadata(self, page: Page):
        """Tenta capturar o melhor título e thumbnail disponíveis no momento."""
        try:
            metadata = await page.evaluate("""() => {
                const getMeta = (name) => {
                    const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"], meta[property="og:${name}"], meta[name="twitter:${name}"]`);
                    return el ? el.getAttribute('content') : null;
                };
                
                // Seletores específicos para sites de notícias e globoplay
                const titleSelectors = [
                    'h1.video-title', 
                    'h1.LiveVideo__Title', 
                    'h1.video-info__title', 
                    '.VideoInfo__Title', 
                    '.video-title-container h1',
                    '.headline',
                    'h1'
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
                    poster: document.querySelector('video') ? document.querySelector('video').getAttribute('poster') : null
                };
            }""")
            
            if metadata.get('title') and len(metadata['title']) > 5:
                # Remove sufixos comuns de sites (ex: " - Fox News")
                clean_title = re.sub(r'\s*\|\s*.*$', '', metadata['title'])
                clean_title = re.sub(r'\s*-\s*(Fox News|ABC News|Globoplay|NBC News).*$', '', clean_title, flags=re.IGNORECASE)
                self.page_title = clean_title.strip()
            
            if not self.thumbnail_url or "glbimg.com" not in self.thumbnail_url:
                new_thumb = metadata.get('og_image') or metadata.get('twitter_image') or metadata.get('poster')
                if new_thumb:
                    self.thumbnail_url = new_thumb
        except:
            pass

    async def extract(self, url: str, interaction_func: Optional[Callable[[Page], asyncio.Future]] = None) -> Dict[str, Any]:
        ensure_playwright_browsers()
        
        self.found_urls = []
        self.thumbnail_url = None
        self.page_title = "Stream"
        
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
                # Carrega a página
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                
                # Lógica de Thumbnail específica para Globo
                if "globo.com" in url:
                    video_id_match = re.search(r'/v/(\d+)', url)
                    if video_id_match:
                        self.thumbnail_url = f"https://s04.video.glbimg.com/x720/{video_id_match.group(1)}.jpg"

                if interaction_func:
                    await interaction_func(page)
                
                # Monitoramento Contínuo: Metadados + Rede
                print("[*] Extraindo metadados e monitorando rede (aguardando stream real)...")
                for i in range(45): # Aumentado para 45s para passar por propagandas longas
                    await self._update_metadata(page)
                    
                    # Verifica se temos um link que parece ser o principal (master/index)
                    has_main_stream = any(word in u.lower() for u in self.found_urls for word in ["master", "index"])
                    
                    if has_main_stream and self.page_title != "Stream":
                        if i > 10: # Garante pelo menos 10s para estabilizar e pular ads iniciais
                            print("[*] Stream principal e metadados capturados!")
                            break
                    await asyncio.sleep(1)
            except Exception as e:
                if not self.found_urls:
                    print(f"[!] Erro durante a extração: {e}")
            finally:
                await browser.close()
        
        return {
            "title": self.page_title.strip(),
            "m3u8_urls": self.found_urls,
            "thumbnail": self.thumbnail_url
        }
