
import asyncio
from playwright.async_api import Page

class RdcanaisPlugin:
    async def interact(self, page: Page):
        print("[PLUGIN] Interagindo com a página rdcanais.com...")
        # Clicar no botão de play
        try:
            await page.locator("div[role=\"button\"]").click(timeout=5000)
            print("[PLUGIN] Clicou no botão de play.")
            await asyncio.sleep(2) # Esperar o player carregar
        except Exception:
            print("[PLUGIN] Botão de play não encontrado ou erro ao clicar.")

        # Tentar encontrar o iframe e navegar para ele
        iframe_src = None
        try:
            iframe_element = await page.query_selector("iframe")
            if iframe_element:
                iframe_src = await iframe_element.get_attribute("src")
                print(f"[PLUGIN] Iframe src encontrado: {iframe_src}")
                if iframe_src:
                    # Navegar para o iframe para que o NetworkCapture possa pegar as requisições
                    await page.goto(iframe_src, wait_until="domcontentloaded")
                    print(f"[PLUGIN] Navegou para o iframe: {iframe_src}")
                    await asyncio.sleep(5) # Esperar as requisições do stream
        except Exception as e:
            print(f"[PLUGIN] Erro ao processar iframe: {e}")

        # Se houver Cloudflare, tentar resolver (exemplo genérico, pode precisar de ajuste)
        if "Attention Required! | Cloudflare" in await page.title():
            print("[PLUGIN] Cloudflare detectado. Tentando resolver...")
            # Aqui pode ser necessário adicionar lógica para resolver o desafio do Cloudflare
            # Por exemplo, esperar por um captcha ou um botão de verificação
            await asyncio.sleep(10) # Esperar um tempo para o Cloudflare resolver automaticamente
            if "Attention Required! | Cloudflare" not in await page.title():
                print("[PLUGIN] Cloudflare aparentemente resolvido.")
            else:
                print("[PLUGIN] Cloudflare não resolvido automaticamente.")


