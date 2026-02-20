from abc import ABC, abstractmethod
from playwright.async_api import Page
import asyncio

class BasePlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome do plugin"""
        pass

    @property
    @abstractmethod
    def domain_pattern(self) -> str:
        """Regex para casar o domínio"""
        pass

    @abstractmethod
    async def interact(self, page: Page) -> None:
        """Ações para extrair o m3u8 (ex: clicar no play)"""
        pass

class GenericPlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "Generic Extractor"

    @property
    def domain_pattern(self) -> str:
        return r".*"

    async def interact(self, page: Page) -> None:
        # Seletores de play baseados no script do usuário e padrões comuns
        play_selectors = [
            'button.poster__play-wrapper', # Globoplay específico
            'button[aria-label="Play"]',
            '.vjs-big-play-button',
            '.play-button',
            'video',
            '#player',
            '.jw-display-icon-container',
            '.play-icon'
        ]
        
        # Tenta clicar no botão de play
        for selector in play_selectors:
            try:
                # Espera curta para ver se o seletor aparece
                if await page.is_visible(selector):
                    print(f"[*] Tentando clicar no seletor de play: {selector}")
                    await page.click(selector)
                    # Espera um pouco após o clique para o stream iniciar
                    await asyncio.sleep(5)
                    break
            except:
                continue
        
        # Espera adicional para carregamento do stream
        print("[*] Aguardando o stream estabilizar...")
        await asyncio.sleep(20)
