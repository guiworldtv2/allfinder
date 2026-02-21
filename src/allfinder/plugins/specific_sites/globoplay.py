"""
globoplay.py
============
Plugin específico para extração de streams do Globoplay (globoplay.globo.com).

Técnicas aplicadas (aprendidas do script de referência do Globoplay):
- Scroll automático da página para carregar conteúdo via lazy-loading.
- Clique em botões de aviso/assinante que bloqueiam o player.
- Extração de lista de canais ao vivo via JavaScript injetado.
- Esperas inteligentes com WebDriverWait equivalente no Playwright.
- Suporte a reutilização de sessão (via use_profile=True no extractor).
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Page

from allfinder.plugins.generic.base import BasePlugin


class GloboplayPlugin(BasePlugin):
    """
    Plugin para o Globoplay.

    Funcionalidades:
    - Clica no botão de play do player.
    - Fecha modais de aviso e botões de assinante que bloqueiam o conteúdo.
    - Realiza scroll para garantir o carregamento de conteúdo dinâmico.
    - Descobre canais ao vivo na página "Agora na TV".
    """

    @property
    def name(self) -> str:
        return "Globoplay"

    @property
    def domain_pattern(self) -> str:
        return r"globoplay\.globo\.com"

    async def interact(self, page: Page) -> None:
        """
        Sequência de interações para acionar o player do Globoplay.

        1. Aguarda o carregamento inicial da página.
        2. Tenta fechar modais de aviso ou botões de assinante.
        3. Tenta clicar no botão de play.
        4. Aguarda o carregamento do stream.
        """
        # Aguarda o carregamento básico da página
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

        # Tenta fechar modais de aviso (ex: "Você precisa ser assinante")
        await self._dismiss_warning_modals(page)

        # Tenta clicar no botão de play
        await self._click_play_button(page)

        # Aguarda o stream começar a carregar
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            # networkidle pode falhar em páginas com muitas requisições contínuas
            await asyncio.sleep(3)

    async def _dismiss_warning_modals(self, page: Page) -> None:
        """
        Verifica e fecha botões de aviso ou modais que bloqueiam o player.
        Equivalente à função check_and_click_subscriber_button() do script original.
        """
        warning_selectors = [
            "button.warning-block__button",
            "button.paywall-button",
            "[data-testid='paywall-cta']",
            ".modal-close",
            "[aria-label='Fechar']",
            "button[class*='close']",
        ]

        for selector in warning_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip().lower()
                        # Fecha modais genéricos ou clica em botões de assinante
                        # para tentar avançar o fluxo
                        if any(kw in text for kw in ["fechar", "close", "entrar", "assinante", "continuar"]):
                            await el.click()
                            await asyncio.sleep(1)
                            break
            except Exception:
                continue

    async def _click_play_button(self, page: Page) -> None:
        """
        Tenta clicar no botão de play do player do Globoplay.
        Usa múltiplos seletores em ordem de especificidade.
        """
        play_selectors = [
            "button.poster__play-wrapper",          # Globoplay específico
            "[data-testid='play-button']",
            "button[aria-label='Play']",
            "button[aria-label='Reproduzir']",
            ".vjs-big-play-button",
            ".play-button",
            ".jw-display-icon-container",
            ".play-icon",
            "video",
        ]

        for selector in play_selectors:
            try:
                await page.wait_for_selector(selector, state="visible", timeout=5000)
                await page.click(selector)
                await asyncio.sleep(1)
                return
            except Exception:
                continue

    async def scroll_to_load_all(self, page: Page, max_scrolls: int = 5) -> None:
        """
        Realiza scroll progressivo na página para carregar todo o conteúdo
        dinâmico (lazy-loading). Útil na página "Agora na TV".

        Equivalente ao loop de scroll do script original.
        """
        last_height = await page.evaluate("document.body.scrollHeight")
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    async def discover_live_channels(self, page: Page) -> List[Dict[str, Any]]:
        """
        Descobre canais ao vivo na página "Agora na TV" do Globoplay.
        Usa JavaScript injetado para extrair nome, URL e thumbnail de cada canal.

        Equivalente à função extract_channels_from_current_page() do script original.

        Retorna
        -------
        List[Dict[str, Any]]
            Lista de dicionários com chaves "name", "url" e "thumbnail".
        """
        await self.scroll_to_load_all(page)

        try:
            channels = await page.evaluate("""() => {
                const idRegex = /(?:^|\\/|v\\/)([0-9]{6,8})(?:\\/|$)/;
                const links = Array.from(
                    document.querySelectorAll("a[href*='/ao-vivo/'], a[href*='/v/']")
                );
                const seenIds = new Set();
                const result = [];

                for (const link of links) {
                    let href = link.href;
                    if (href.includes('/assine/') || href.includes('/subscribe')) continue;

                    const match = href.match(idRegex);
                    if (!match) continue;

                    const channelId = match[1];
                    if (seenIds.has(channelId)) continue;
                    seenIds.add(channelId);

                    const directUrl = `https://globoplay.globo.com/ao-vivo/${channelId}/`;

                    const nameEl = link.querySelector(
                        '.video-card-title, .program-card__title, .headline__title, [class*="title"]'
                    );
                    let name = nameEl ? nameEl.textContent.trim() : link.getAttribute('aria-label');

                    if (!name) {
                        const parentCard = link.closest('.channel-card, [class*="card"]');
                        if (parentCard) {
                            const parentName = parentCard.querySelector(
                                '[class*="channel-name"], [class*="title"]'
                            );
                            if (parentName) name = parentName.textContent.trim();
                        }
                    }

                    if (!name) name = channelId;

                    const img = link.querySelector('img');
                    const thumbnail = img ? (img.src || img.dataset.src || null) : null;

                    result.push({ name, url: directUrl, thumbnail, id: channelId });
                }

                return result;
            }""")
            return channels or []
        except Exception as e:
            print(f"[!] GloboplayPlugin: erro ao descobrir canais: {e}")
            return []

    async def get_thumbnail_from_page(self, page: Page) -> str:
        """
        Extrai a thumbnail da página via meta tags og:image ou twitter:image.
        Equivalente à função get_thumbnail_from_page() do script original.
        """
        try:
            thumbnail = await page.evaluate("""() => {
                const ogImage = document.querySelector('meta[property="og:image"]');
                if (ogImage) return ogImage.getAttribute('content').split(' ')[0];
                const twitterImage = document.querySelector('meta[name="twitter:image"]');
                if (twitterImage) return twitterImage.getAttribute('content').split(' ')[0];
                return null;
            }""")
            return thumbnail or ""
        except Exception:
            return ""

    @staticmethod
    def clean_channel_name(name: str) -> str:
        """
        Limpa e normaliza o nome de um canal do Globoplay.
        Equivalente à função clean_channel_name() do script original.
        """
        if not name:
            return ""
        if "Globo Internacional" in name:
            return "Globo Internacional"
        name = re.sub(r"^Globoplay\.\s*", "", name, flags=re.IGNORECASE)
        name = re.sub(r"^Canal BBB \d+\s*-\s*", "", name, flags=re.IGNORECASE)
        name = re.sub(r",?\s*Ao vivo.*$", "", name, flags=re.IGNORECASE)
        parts = [p.strip() for p in name.split(",") if p.strip()]
        return parts[0].strip() if parts else name.strip()
