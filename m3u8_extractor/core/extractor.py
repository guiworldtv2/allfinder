import asyncio
import re
from typing import Optional, List, Callable
from playwright.async_api import async_playwright, Request, Page, Browser

class M3U8Extractor:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.found_urls: List[str] = []

    async def _handle_request(self, request: Request):
        url = request.url
        # Padrões comuns para arquivos m3u8 e playlists HLS
        if ".m3u8" in url.lower() or "playlist.m3u8" in url.lower() or "chunklist.m3u8" in url.lower():
            if url not in self.found_urls:
                self.found_urls.append(url)
                print(f"[+] Encontrado M3U8: {url}")

    async def extract(self, url: str, interaction_func: Optional[Callable[[Page], asyncio.Future]] = None) -> List[str]:
        self.found_urls = []
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(headless=self.headless)
            # User agent comum para evitar bloqueios básicos
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page: Page = await context.new_page()
            
            # Registrar o handler de interceptação de rede
            page.on("request", self._handle_request)
            
            print(f"[*] Navegando para: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=self.timeout)
                
                # Se houver uma função de interação (ex: clicar no play), execute-a
                if interaction_func:
                    print("[*] Executando interações customizadas...")
                    await interaction_func(page)
                else:
                    # Espera genérica para dar tempo ao player carregar
                    print("[*] Aguardando carregamento automático do stream...")
                    await asyncio.sleep(10)
                    
            except Exception as e:
                print(f"[!] Erro durante a extração: {e}")
            finally:
                await browser.close()
        
        return self.found_urls
