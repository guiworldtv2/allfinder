import asyncio
import re
import sys
import json
import os
import base64
from typing import Optional, List, Callable, Dict, Any
from playwright.async_api import async_playwright, Request, Page, Browser, BrowserContext

class M3U8Extractor:
    def __init__(self, headless: bool = True, timeout: int = 120000, cookie_file: Optional[str] = None, browser_type: str = "chromium", use_profile: bool = False, profile_name: Optional[str] = None):

        self.headless = headless
        self.timeout = timeout
        self.cookie_file = cookie_file
        self.browser_type = browser_type
        self.use_profile = use_profile
        self.profile_name = profile_name
        self.found_urls: List[str] = []
        self.thumbnail_url: Optional[str] = None
        self.page_title: str = "Stream"
        self.drm_data: Dict[str, Any] = {}

    def _load_cookies(self) -> List[Dict[str, Any]]:
        if not self.cookie_file or not os.path.exists(self.cookie_file):
            return []
        cookies = []
        try:
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if self.cookie_file.endswith('.json'):
                    cookies = json.loads(content)
                else:
                    for line in content.splitlines():
                        if not line.startswith('#') and line.strip():
                            parts = line.split('\t')
                            if len(parts) >= 7:
                                cookies.append({
                                    'name': parts[5], 'value': parts[6], 'domain': parts[0],
                                    'path': parts[2], 'expires': int(parts[4]) if parts[4].isdigit() else -1,
                                    'httpOnly': parts[3] == 'TRUE', 'secure': parts[1] == 'TRUE', 'sameSite': 'Lax'
                                })
        except Exception as e:
            print(f"[!] Erro ao carregar cookies: {e}")
        return cookies

    async def _handle_request(self, request: Request):
        url = request.url
        
        # Captura URLs de Licença DRM (Widevine/PlayReady)
        if any(w in url.lower() for w in ["widevine", "playready", "license", "licenser", "getlicense"]):
            if request.method == "POST":
                self.drm_data["license_url"] = url
                # Tenta capturar o challenge se possível
                try:
                    post_data = request.post_data
                    if post_data:
                        self.drm_data["pssh_challenge"] = base64.b64encode(post_data).decode() if isinstance(post_data, bytes) else post_data
                except: pass

        # Captura manifestos
        if any(ext in url.lower() for ext in [".m3u8", ".mpd"]):
            blacklist = ["ping", "chartbeat", "analytics", "ads", "telemetry", "log", "metrics"]
            if not any(word in url.lower() for word in blacklist):
                is_master = any(w in url.lower() for w in ["master", "index", "playlist", "manifest", "skyfire"])
                has_token = "?" in url and any(t in url.lower() for t in ["token", "auth", "hdnea", "exp=", "hmac", "sig="])
                
                if url not in self.found_urls:
                    if ".mpd" in url.lower():
                        self.drm_data["manifest_url"] = url
                    
                    if is_master and has_token:
                        self.found_urls.insert(0, url)
                    elif is_master:
                        self.found_urls.insert(min(1, len(self.found_urls)), url)
                    else:
                        self.found_urls.append(url)

    async def _update_metadata(self, page: Page):
        try:
            metadata = await page.evaluate("""() => {
                const getMeta = (n) => {
                    const el = document.querySelector(`meta[property="${n}"], meta[name="${n}"], meta[property="og:${n}"]`);
                    return el ? el.getAttribute('content') : null;
                };
                const selectors = ['h1.video-title', 'h1.LiveVideo__Title', '.VideoInfo__Title', 'h2[data-a-target="stream-title"]', 'h1', 'title'];
                let t = null;
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el && el.innerText.trim().length > 2) { t = el.innerText.trim(); break; }
                }
                
                // Busca PSSH e KID em scripts e objetos de configuração
                let pssh = null;
                let kid = null;
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.innerText;
                    // Procura PSSH em base64 (geralmente começa com AAA)
                    const psshMatch = text.match(/AAAA[a-zA-Z0-9+/]{30,}/);
                    if (psshMatch) pssh = psshMatch[0];
                    
                    // Procura KID (UUID format)
                    const kidMatch = text.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
                    if (kidMatch) kid = kidMatch[0];
                }
                
                return { 
                    title: t || getMeta('og:title') || document.title, 
                    og_image: getMeta('og:image'), 
                    poster: document.querySelector('video') ? document.querySelector('video').getAttribute('poster') : null,
                    pssh: pssh,
                    kid: kid
                };
            }""")
            if metadata.get('title'): self.page_title = re.sub(r'\s*\|\s*.*$', '', metadata['title']).strip()
            if not self.thumbnail_url: self.thumbnail_url = metadata.get('og_image') or metadata.get('poster')
            if metadata.get('pssh') and "pssh" not in self.drm_data: self.drm_data["pssh"] = metadata['pssh']
            if metadata.get('kid') and "kid" not in self.drm_data: self.drm_data["kid"] = metadata['kid']
        except: pass

    async def extract(self, url: str, interaction_func: Optional[Callable[[Page], asyncio.Future]] = None) -> Dict[str, Any]:
        self.found_urls = []
        self.thumbnail_url = None
        self.page_title = "Stream"
        self.drm_data = {}
        
        async with async_playwright() as p:
            browser_launcher = getattr(p, self.browser_type)
            launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
            if self.headless: launch_args.append("--headless=new")
            
            if self.use_profile:
                user_data_dir = os.path.join(os.path.expanduser("~"), ".config", self.browser_type, self.profile_name or "Default")
                context = await browser_launcher.launch_persistent_context(user_data_dir, headless=self.headless, args=launch_args)
                browser = None
            else:
                browser = await browser_launcher.launch(headless=self.headless, args=launch_args)
                context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            
            page = await context.new_page()
            page.on("request", self._handle_request)
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                await asyncio.sleep(10)
                
                # Aceitar cookies, se houver
                try:
                    await page.click("text=Accept all", timeout=5000)
                except: pass

                # Interação para disparar o player (genérico)
                await page.mouse.click(640, 360)
                await page.evaluate("window.scrollBy(0, 200)")

                # Lógica específica para a página de demonstração da Bitmovin
                if "bitmovin.com/demos/drm" in url:
                    try:
                        # Selecionar Widevine no dropdown de DRM
                        await page.select_option("#available-drm-systems", "widevine")
                        # Clicar no botão 'Load'
                        await page.click("#load-btn")
                        await asyncio.sleep(5) # Esperar o vídeo carregar
                    except Exception as e:
                        print(f"[!] Erro na interação com a página da Bitmovin: {e}")
                
                if interaction_func: await interaction_func(page)
                
                # Monitoramento por 30-45 segundos
                for _ in range(60):
                    await self._update_metadata(page)
                    # Se encontrou M3U8 e dados de DRM, já pode parar
                    if any(".m3u8" in u.lower() for u in self.found_urls) and self.drm_data.get("license_url"):
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"[!] Erro durante a extração: {e}")
            finally:
                if browser: await browser.close()
                else: await context.close()
        
        # Filtro final: Prioriza M3U8 (HLS)
        hls_urls = [u for u in self.found_urls if ".m3u8" in u.lower()]
        
        return {
            "title": self.page_title, 
            "m3u8_urls": hls_urls if hls_urls else self.found_urls, 
            "thumbnail": self.thumbnail_url,
            "drm": self.drm_data
        }
