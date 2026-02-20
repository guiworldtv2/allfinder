import asyncio
import argparse
from typing import List, Dict, Any
from allfinder.core.extractor import M3U8Extractor
from allfinder.plugins.manager import PluginManager
from allfinder.plugins.base import GenericPlugin

async def process_url(url: str, extractor: M3U8Extractor, plugin_manager: PluginManager) -> Dict[str, Any]:
    plugin = plugin_manager.get_plugin_for_url(url)
    print(f"\n[*] Processando: {url}")
    
    data = await extractor.extract(url, plugin.interact)
    return {
        "source_url": url,
        "title": data["title"],
        "m3u8_urls": data["m3u8_urls"],
        "thumbnail": data["thumbnail"]
    }

async def main():
    parser = argparse.ArgumentParser(description="allfinder: Extrai URLs .m3u8 com títulos e thumbnails.")
    parser.add_argument("urls", nargs="+", help="Uma ou mais URLs de sites de streaming.")
    parser.add_argument("--headless", action="store_true", default=True, help="Executa o navegador em modo headless.")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Executa o navegador com interface gráfica.")
    parser.add_argument("--timeout", type=int, default=60000, help="Tempo limite em milissegundos.")
    parser.add_argument("--output", "-o", help="Caminho para salvar o arquivo .m3u resultante.")

    args = parser.parse_args()

    extractor = M3U8Extractor(headless=args.headless, timeout=args.timeout)
    plugin_manager = PluginManager()
    plugin_manager.register_plugin(GenericPlugin())

    results = []
    for url in args.urls:
        res = await process_url(url, extractor, plugin_manager)
        results.append(res)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for res in results:
                if res["m3u8_urls"]:
                    # Prioriza playlist.m3u8 se disponível, senão pega a primeira
                    main_url = next((u for u in res["m3u8_urls"] if "playlist.m3u8" in u.lower()), res["m3u8_urls"][0])
                    logo = f' tvg-logo="{res["thumbnail"]}"' if res["thumbnail"] else ""
                    # Usa o título real extraído, se não for o padrão "Stream"
                    display_title = res["title"] if res["title"] != "Stream" else f"Stream de {res['source_url']}"
                    f.write(f'#EXTINF:-1{logo} group-title="ALLFINDER STREAMS", {display_title}\n')
                    f.write(f"{main_url}\n")
        print(f"\n[✓] Arquivo '{args.output}' gerado com sucesso com títulos e logos!")
    else:
        print("\n[+] Resultados da Extração:")
        for res in results:
            print(f"\nTítulo: {res['title']}")
            print(f"Thumbnail: {res['thumbnail'] or 'Não encontrada'}")
            if res["m3u8_urls"]:
                for u in res["m3u8_urls"]:
                    print(f"  - {u}")
            else:
                print("  [-] Nenhum link m3u8 encontrado.")

def main_entry():
    asyncio.run(main())

if __name__ == "__main__":
    main_entry()
