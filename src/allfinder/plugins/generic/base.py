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
        
        # Tenta clicar no botão de play usando esperas inteligentes
        for selector in play_selectors:
            try:
                # Espera o seletor ficar visível por no máximo 5 segundos
                await page.wait_for_selector(selector, state="visible", timeout=5000)
                await page.click(selector)
                # Espera o estado da rede ficar ocioso após o clique
                await page.wait_for_load_state("networkidle", timeout=5000)
                break
            except:
                continue
        
        # Em vez de sleep fixo de 20s, esperamos o estado da rede ou um tempo menor
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except:
            # Se o networkidle falhar (muitos ads), apenas continua
            pass
