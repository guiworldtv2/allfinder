import asyncio
import argparse
import sys
from urllib.parse import urlparse

# Adiciona o diretório raiz do projeto ao sys.path para importações relativas
sys.path.append('/home/ubuntu/m3u8-extractor/src')

from core.extractor import M3U8Extractor
from plugins.manager import PluginManager
from plugins.base import GenericPlugin # Importar GenericPlugin para registro

async def main():
    parser = argparse.ArgumentParser(description="Extrai URLs .m3u8 de sites de streaming.")
    parser.add_argument("url", help="A URL do site de streaming para extrair o m3u8.")
    parser.add_argument("--headless", action="store_true", help="Executa o navegador em modo headless (sem interface gráfica).")
    parser.add_argument("--timeout", type=int, default=30000, help="Tempo limite em milissegundos para operações do navegador.")

    args = parser.parse_args()

    extractor = M3U8Extractor(headless=args.headless, timeout=args.timeout)
    plugin_manager = PluginManager()
    
    # Registrar plugins aqui. Por enquanto, apenas o genérico.
    plugin_manager.register_plugin(GenericPlugin())

    parsed_url = urlparse(args.url)
    plugin = plugin_manager.get_plugin_for_url(args.url)

    print(f"[*] Usando plugin: {plugin.name}")

    m3u8_urls = await extractor.extract(args.url, plugin.interact)

    if m3u8_urls:
        print("\n[+] URLs M3U8 encontradas:")
        for url in m3u8_urls:
            print(f"    - {url}")
    else:
        print("\n[-] Nenhuma URL M3U8 encontrada.")

if __name__ == "__main__":
    asyncio.run(main())
