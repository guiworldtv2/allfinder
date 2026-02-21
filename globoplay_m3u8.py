"""
globoplay_m3u8.py
=================
Script simples para extrair e exibir o link M3U8 do Globoplay
diretamente no terminal do VS Code.

Pré-requisitos:
  pip install https://github.com/guiworldtv2/allfinder/releases/download/v0.2.0/allfinder-0.2.0-py3-none-any.whl

Como usar:
  1. Feche o Edge completamente.
  2. Ajuste as variáveis BROWSER, PROFILE_NAME e URL abaixo.
  3. Rode: python globoplay_m3u8.py
"""

import asyncio
from allfinder.core.extractor import M3U8Extractor
from allfinder.plugins.manager import PluginManager

# ============================================================
# CONFIGURAÇÕES — ajuste conforme necessário
# ============================================================

# Navegador onde você está logado no Globoplay
BROWSER = "edge"  # "edge", "chrome", "firefox" ou "chromium"

# Nome do perfil (rode `allfinder --list-profiles` para descobrir o seu)
PROFILE_NAME = "Pessoa 1"

# URL do canal que deseja extrair
# TV Globo ao vivo: https://globoplay.globo.com/v/7832875/
URL = "https://globoplay.globo.com/v/7832875/"

# ============================================================


async def main():
    print(f"\n🔍 Extraindo M3U8 de: {URL}")
    print(f"   Navegador : {BROWSER}")
    print(f"   Perfil    : {PROFILE_NAME}\n")

    extractor = M3U8Extractor(
        browser=BROWSER,
        profile_name=PROFILE_NAME,
        use_profile=True,
        headless=False,   # abre o navegador visível para carregar o perfil
        timeout=60000,
    )

    plugin_manager = PluginManager()
    plugin = plugin_manager.get_plugin_for_url(URL)

    try:
        result = await extractor.extract(URL, plugin.interact)

        print(f"✅ Título    : {result['title']}")
        print(f"🖼  Thumbnail : {result['thumbnail'] or 'não encontrada'}")
        print()

        if result["m3u8_urls"]:
            print(f"📺 Link(s) M3U8 encontrado(s):\n")
            for url in result["m3u8_urls"]:
                print(f"   {url}")
        else:
            print("❌ Nenhum link M3U8 encontrado.")
            print("   Verifique se o Edge está fechado e se o perfil está correto.")

    except Exception as e:
        print(f"❌ Erro: {e}")


if __name__ == "__main__":
    asyncio.run(main())
