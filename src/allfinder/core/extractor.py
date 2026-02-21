import asyncio
import re
import sys
import json
import os
import subprocess
import validators
import urllib.parse
from typing import Optional, List, Callable, Dict, Any
from playwright.async_api import async_playwright, Request, Page, Browser

def ensure_playwright_browsers():
    """Garante que os navegadores e dependências do sistema do Playwright estejam instalados."""
    # Verifica se o navegador já está instalado tentando rodar um comando simples
    try:
        result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium", "--dry-run"], capture_output=True, text=True)
        if "browser is already installed" in result.stdout.lower():
            return
    except:
        pass

    print("[*] Instalando navegadores e dependências do sistema (isso pode levar alguns minutos)...")
    
    # Detecta se estamos no Colab ou se temos sudo disponível
    is_colab = 'google.colab' in sys.modules
    has_sudo = subprocess.run(['which', 'sudo'], capture_output=True).returncode == 0
    
    # Configura variáveis de ambiente para instalação não interativa
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    
    cmd_prefix = ['sudo', '-E'] if (is_colab or has_sudo) else []

    try:
        # Tenta instalar o navegador e as dependências de forma silenciosa
        print("[*] Baixando Chromium...")
        subprocess.run(cmd_prefix + [sys.executable, "-m", "playwright", "install", "chromium"], check=True, env=env)
        
        print("[*] Instalando dependências do sistema (apt-get)...")
        # No Colab, o apt-get update ajuda a evitar erros de pacotes não encontrados
        if is_colab or has_sudo:
            subprocess.run(['sudo', '-E', 'apt-get', 'update', '-y'], check=True, env=env, capture_output=True)
            
        subprocess.run(cmd_prefix + [sys.executable, "-m", "playwright", "install-deps", "chromium"], check=True, env=env)
        print("[✓] Navegador e dependências instalados com sucesso!")
    except subprocess.CalledProcessError as e:
        print(f"[!] Erro durante a instalação: {e}")
        print("[*] Tentando uma última abordagem forçada...")
        try:
            subprocess.run(cmd_prefix + [sys.executable, "-m", "playwright", "install-deps", "chromium"], check=True, env=env)
        except:
            print("[!] Falha ao instalar dependências. O navegador pode não funcionar corretamente.")

class M3U8Extractor:
    def __init__(self, headless: bool = True, timeout: int = 30000, cookies_from_browser: Optional[str] = None, cookies_file: Optional[str] = None):
        self.headless = headless
        self.timeout = timeout
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self.found_urls: List[str] = []
        self.thumbnail_url: Optional[str] = None
        self.page_title: str = "Stream"

    def validate_url(self, url: str) -> bool:
        """Valida se a URL é segura e bem formatada."""
        if not validators.url(url):
            return False
        
        if not url.lower().startswith(('http://', 'https://')):
            return False

        parsed_url = re.search(r'https?://([^/]+)', url)
        if parsed_url:
            host = parsed_url.group(1).lower()
            if any(x in host for x in ['localhost', '127.0.0.1', '0.0.0.0', '192.168.', '10.', '172.16.']):
                return False
        return True

    def _parse_cookies_file(self) -> List[Dict[str, Any]]:
        """Lê cookies de arquivos .json ou .txt (formato Netscape)."""
        if not self.cookies_file or not os.path.exists(self.cookies_file):
            return []

        cookies = []
        try:
            if self.cookies_file.endswith('.json'):
                with open(self.cookies_file, 'r') as f:
                    data = json.load(f)
                    # Suporta tanto lista de cookies quanto formato exportado por algumas extensões
                    if isinstance(data, list):
                        cookies = data
                    elif isinstance(data, dict) and 'cookies' in data:
                        cookies = data['cookies']
            else:
                # Formato Netscape (.txt)
                with open(self.cookies_file, 'r') as f:
                    for line in f:
                        if line.startswith('#') or not line.strip():
                            continue
                        parts = line.strip().split('\t')
                        if len(parts) >= 7:
                            cookies.append({
                                'name': parts[5],
                                'value': parts[6],
                                'domain': parts[0],
                                'path': parts[2],
                                'expires': int(parts[4]) if parts[4].isdigit() else -1,
                                'httpOnly': parts[1].upper() == 'TRUE',
                                'secure': parts[3].upper() == 'TRUE'
                            })
        except Exception as e:
            print(f"[!] Erro ao ler arquivo de cookies: {e}")
        
        return cookies

    def _clean_url(self, url: str) -> str:
        """Extrai a URL real se estiver embutida em parâmetros de rastreamento (ex: Google Analytics)."""
        try:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            
            # Lista de parâmetros comuns que podem conter a URL real
            url_params = ['ep.URL', 'url', 'link', 'target', 'redir']
            
            for param in url_params:
                if param in params:
                    potential_url = params[param][0]
                    if ".m3u8" in potential_url.lower() and self.validate_url(potential_url):
                        return potential_url
        except:
            pass
        return url

    async def _handle_request(self, request: Request):
        url = request.url
        
        # Tenta limpar a URL antes de verificar se é m3u8
        cleaned_url = self._clean_url(url)
        
        if ".m3u8" in cleaned_url.lower():
            blacklist = [
                "youbora", "chartbeat.net", "facebook.com", "horizon.globo.com", "analytics", "telemetry", "log", "metrics", "heartbeat", 
                "omtrdc", "hotjar", "scorecardresearch", "doubleclick", "ads", 
                "adnxs", "fwmrm.net", "googleads", "amazon-adsystem", "casalemedia",
                "adnxs", "advertising", "segment", "moatads", "krxd"
            ]
            
            # Se a URL limpa ainda contém palavras da blacklist, ignoramos
            if not any(word in cleaned_url.lower() for word in blacklist):
                if cleaned_url not in self.found_urls:
                    is_likely_main = any(word in cleaned_url.lower() for word in ["master", "index", "playlist", "chunklist"])
                    if is_likely_main:
                        self.found_urls.insert(0, cleaned_url)
                    else:
                        self.found_urls.append(cleaned_url)

    async def _update_metadata(self, page: Page):
        try:
            metadata = await page.evaluate("""() => {
                const getMeta = (name) => {
                    const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"], meta[property="og:${name}"], meta[name="twitter:${name}"]`);
                    return el ? el.getAttribute('content') : null;
                };
                
                const titleSelectors = ['h1.video-title', 'h1.LiveVideo__Title', 'h1.video-info__title', '.VideoInfo__Title', '.video-title-container h1', '.headline', 'h1'];
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

    def _extract_with_ytdlp(self, url: str) -> Optional[str]:
        """Tenta extrair o link m3u8 usando yt-dlp (útil para YouTube e outros sites complexos)."""
        try:
            # Verifica se yt-dlp está instalado
            subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
            
            cmd = ["yt-dlp", "-g", "-f", "best", url]
            if self.cookies_file:
                cmd.extend(["--cookies", self.cookies_file])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                potential_url = result.stdout.strip()
                if ".m3u8" in potential_url.lower() or "manifest" in potential_url.lower():
                    return potential_url
        except:
            pass
        return None

    async def extract(self, url: str, interaction_func: Optional[Callable[[Page], asyncio.Future]] = None) -> Dict[str, Any]:
        if not self.validate_url(url):
            raise ValueError(f"URL inválida ou insegura: {url}")

        # Tenta yt-dlp primeiro para sites conhecidos como YouTube
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            ytdl_url = self._extract_with_ytdlp(url)
            if ytdl_url:
                # Tenta pegar o título via yt-dlp também
                title = "YouTube Live"
                try:
                    res = subprocess.run(["yt-dlp", "--get-title", url], capture_output=True, text=True)
                    if res.returncode == 0: title = res.stdout.strip()
                except: pass
                
                return {
                    "title": title,
                    "m3u8_urls": [ytdl_url],
                    "thumbnail": f"https://img.youtube.com/vi/{url.split('v=')[-1] if 'v=' in url else 'live'}/maxresdefault.jpg"
                }

        ensure_playwright_browsers()
        
        self.found_urls = []
        self.thumbnail_url = None
        self.page_title = "Stream"
        
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )

            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
            
            context = await browser.new_context(**context_kwargs)
            
            # Carrega cookies do arquivo se fornecido
            file_cookies = self._parse_cookies_file()
            if file_cookies:
                await context.add_cookies(file_cookies)
                print(f"[*] {len(file_cookies)} cookies carregados do arquivo.")

            page: Page = await context.new_page()
            page.on("request", self._handle_request)
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                
                if "globo.com" in url:
                    video_id_match = re.search(r'/v/(\d+)', url)
                    if video_id_match:
                        self.thumbnail_url = f"https://s04.video.glbimg.com/x720/{video_id_match.group(1)}.jpg"

                if interaction_func:
                    await interaction_func(page)
                
                for i in range(45):
                    await self._update_metadata(page)
                    has_main_stream = any(word in u.lower() for u in self.found_urls for word in ["master", "index"])
                    if has_main_stream and self.page_title != "Stream":
                        if i > 5:
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
