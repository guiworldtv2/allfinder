import asyncio
import argparse
from typing import List, Dict, Any
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from allfinder.core.extractor import M3U8Extractor
from allfinder.plugins.manager import PluginManager
from allfinder.plugins.generic.base import GenericPlugin

console = Console()

async def process_url(url: str, extractor: M3U8Extractor, plugin_manager: PluginManager, progress: Progress) -> Dict[str, Any]:
    plugin = plugin_manager.get_plugin_for_url(url)
    task_id = progress.add_task(f"[cyan]Processando: {url}", total=None)
    
    try:
        data = await extractor.extract(url, plugin.interact)
        progress.update(task_id, completed=True, description=f"[green]Concluído: {url}")
        return {
            "source_url": url,
            "title": data["title"],
            "m3u8_urls": data["m3u8_urls"],
            "thumbnail": data["thumbnail"]
        }
    except Exception as e:
        progress.update(task_id, completed=True, description=f"[red]Erro: {url}")
        console.print(f"[bold red]Erro ao processar {url}:[/] {e}")
        return {
            "source_url": url,
            "title": "Erro",
            "m3u8_urls": [],
            "thumbnail": None
        }

async def main():
    parser = argparse.ArgumentParser(description="allfinder: Extrai URLs .m3u8 com títulos e thumbnails.")
    parser.add_argument("urls", nargs="+", help="Uma ou mais URLs de sites de streaming.")
    parser.add_argument("--headless", action="store_true", default=True, help="Executa o navegador em modo headless.")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Executa o navegador com interface gráfica.")
    parser.add_argument("--timeout", type=int, default=60000, help="Tempo limite em milissegundos.")
    parser.add_argument("--output", "-o", help="Caminho para salvar o arquivo .m3u resultante.")
    parser.add_argument("--cookies-from-browser", choices=["chrome", "edge"], help="Importa cookies do navegador especificado.")

    args = parser.parse_args()

    extractor = M3U8Extractor(headless=args.headless, timeout=args.timeout, cookies_from_browser=args.cookies_from_browser)
    plugin_manager = PluginManager()
    plugin_manager.register_plugin(GenericPlugin())

    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        for url in args.urls:
            res = await process_url(url, extractor, plugin_manager, progress)
            results.append(res)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for res in results:
                if res["m3u8_urls"]:
                    main_url = next((u for u in res["m3u8_urls"] if "playlist.m3u8" in u.lower()), res["m3u8_urls"][0])
                    logo = f' tvg-logo="{res["thumbnail"]}"' if res["thumbnail"] else ""
                    display_title = res["title"] if res["title"] != "Stream" else f"Stream de {res['source_url']}"
                    f.write(f'#EXTINF:-1{logo} group-title="ALLFINDER STREAMS", {display_title}\n')
                    f.write(f"{main_url}\n")
        console.print(f"\n[bold green]✓[/] Arquivo '[bold cyan]{args.output}[/]' gerado com sucesso!")
    else:
        console.print("\n[bold cyan]Resultados da Extração:[/]")
        for res in results:
            if res["title"] == "Erro": continue
            console.print(f"\n[bold]Título:[/] {res['title']}")
            console.print(f"[bold]Thumbnail:[/] {res['thumbnail'] or 'Não encontrada'}")
            if res["m3u8_urls"]:
                for u in res["m3u8_urls"]:
                    console.print(f"  [green]- {u}[/]")
            else:
                console.print("  [red][-] Nenhum link m3u8 encontrado.[/]")

def main_entry():
    asyncio.run(main())

if __name__ == "__main__":
    main_entry()
