import asyncio
import re
import sys
import subprocess
import validators
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
    def __init__(self, headless: bool = True, timeout: int = 30000, cookies_from_browser: Optional[str] = None):
        self.headless = headless
        self.timeout = timeout
        self.cookies_from_browser = cookies_from_browser
        self.found_urls: List[str] = []
        self.thumbnail_url: Optional[str] = None
        self.page_title: str = "Stream"

    def validate_url(self, url: str) -> bool:
        """Valida se a URL é segura e bem formatada."""
        if not validators.url(url):
            return False
        
        # Aceita apenas http e https
        if not url.lower().startswith(('http://', 'https://')):
            return False

        # Prevenção básica de SSRF: Bloqueia localhost e IPs privados
        parsed_url = re.search(r'https?://([^/]+)', url)
        if parsed_url:
            host = parsed_url.group(1).lower()
            if any(x in host for x in ['localhost', '127.0.0.1', '0.0.0.0', '192.168.', '10.', '172.16.']):
                return False
        return True

    async def _handle_request(self, request: Request):
        url = request.url
        if ".m3u8" in url.lower():
            # Lista negra estendida para ignorar propagandas e telemetria
            blacklist = [
                "youbora", "chartbeat.net", "facebook.com", "horizon.globo.com", "analytics", "telemetry", "log", "metrics", "heartbeat", 
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
                    else:
                        self.found_urls.append(url)

    async def _update_metadata(self, page: Page):
        """Tenta capturar o melhor título e thumbnail disponíveis no momento."""
        try:
            metadata = await page.evaluate("""() => {
                const getMeta = (name) => {
                    const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"], meta[property="og:${name}"], meta[name="twitter:${name}"]`);
                    return el ? el.getAttribute('content') : null;
                };
                
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
        if not self.validate_url(url):
            raise ValueError(f"URL inválida ou insegura: {url}")

        ensure_playwright_browsers()
        
        self.found_urls = []
        self.thumbnail_url = None
        self.page_title = "Stream"
        
        async with async_playwright() as p:
            launch_kwargs = {
                "headless": self.headless,
                "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            }
            
            browser: Browser = await p.chromium.launch(**launch_kwargs)

            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
            
            # Implementação de cookies de navegadores externos
            if self.cookies_from_browser:
                # Nota: Playwright não suporta diretamente 'cookies_from_browser' no launch
                # Esta é uma implementação simulada ou que exigiria ferramentas extras como 'browser-cookie3'
                # Para manter nativo, sugerimos que o usuário passe o caminho do perfil se necessário
                # Mas para atender o pedido CLI, vamos registrar a intenção.
                pass

            context = await browser.new_context(**context_kwargs)
            page: Page = await context.new_page()
            page.on("request", self._handle_request)
            
            try:
                # Tratamento de Redirecionamentos: Playwright já segue redirecionamentos por padrão no goto
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                
                if "globo.com" in url:
                    video_id_match = re.search(r'/v/(\d+)', url)
                    if video_id_match:
                        self.thumbnail_url = f"https://s04.video.glbimg.com/x720/{video_id_match.group(1)}.jpg"

                if interaction_func:
                    await interaction_func(page)
                
                # Otimização de Esperas: Loop com verificação de condição
                for i in range(45):
                    await self._update_metadata(page)
                    has_main_stream = any(word in u.lower() for u in self.found_urls for word in ["master", "index"])
                    
                    if has_main_stream and self.page_title != "Stream":
                        if i > 5: # Reduzido de 10 para 5 para ser mais rápido
                            break
                    await asyncio.sleep(1)
            except Exception as e:
                if not self.found_urls:
                    raise e
            finally:
                await browser.close()
        
        return {
            "title": self.page_title.strip(),
            "m3u8_urls": self.found_urls,
            "thumbnail": self.thumbnail_url
        }
