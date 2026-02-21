"""
cli/main.py
===========
Interface de linha de comando do allfinder.

Novos argumentos adicionados:
  --browser       : Escolhe o navegador (chrome, edge, firefox, chromium).
  --profile       : Nome do perfil do navegador a reutilizar.
  --use-profile   : Ativa o modo de reutilização de perfil (sessão logada).
  --list-profiles : Lista todos os perfis detectados no sistema e sai.
"""

import asyncio
import argparse
from typing import List, Dict, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from allfinder.core.extractor import M3U8Extractor
from allfinder.core.browser_profile import detect_available_browsers, list_profiles, print_available_profiles
from allfinder.plugins.manager import PluginManager
from allfinder.plugins.generic.base import GenericPlugin

console = Console()


async def process_url(
    url: str,
    extractor: M3U8Extractor,
    plugin_manager: PluginManager,
    progress: Progress,
) -> Dict[str, Any]:
    plugin = plugin_manager.get_plugin_for_url(url)
    task_id = progress.add_task(f"[cyan]Processando: {url}", total=None)

    try:
        data = await extractor.extract(url, plugin.interact)
        progress.update(task_id, completed=True, description=f"[green]Concluído: {url}")
        return {
            "source_url": url,
            "title": data["title"],
            "m3u8_urls": data["m3u8_urls"],
            "thumbnail": data["thumbnail"],
        }
    except Exception as e:
        progress.update(task_id, completed=True, description=f"[red]Erro: {url}")
        console.print(f"[bold red]Erro ao processar {url}:[/] {e}")
        return {
            "source_url": url,
            "title": "Erro",
            "m3u8_urls": [],
            "thumbnail": None,
        }


async def main():
    parser = argparse.ArgumentParser(
        description="allfinder: Extrai URLs .m3u8 com títulos e thumbnails.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  allfinder https://exemplo.com/video
  allfinder https://globoplay.globo.com/v/12345/ --browser edge --use-profile --profile "Pessoa 1"
  allfinder https://exemplo.com/live --browser chrome --use-profile
  allfinder --list-profiles
        """,
    )

    # Argumentos posicionais
    parser.add_argument(
        "urls",
        nargs="*",
        help="Uma ou mais URLs de sites de streaming.",
    )

    # Opções de navegador
    browser_group = parser.add_argument_group("Opções de Navegador")
    browser_group.add_argument(
        "--browser",
        choices=["chrome", "edge", "firefox", "chromium"],
        default="chromium",
        help="Navegador a ser usado (padrão: chromium).",
    )
    browser_group.add_argument(
        "--use-profile",
        action="store_true",
        default=False,
        help=(
            "Reutiliza um perfil existente do navegador para acessar sites que "
            "exigem login (ex: Globoplay). O navegador deve já estar logado no perfil."
        ),
    )
    browser_group.add_argument(
        "--profile",
        default=None,
        metavar="NOME_DO_PERFIL",
        help=(
            'Nome do perfil do navegador a usar (ex: "Pessoa 1", "Default"). '
            "Use --list-profiles para ver os perfis disponíveis."
        ),
    )
    browser_group.add_argument(
        "--list-profiles",
        action="store_true",
        default=False,
        help="Lista todos os navegadores e perfis detectados no sistema e sai.",
    )

    # Opções de execução
    exec_group = parser.add_argument_group("Opções de Execução")
    exec_group.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Executa o navegador em modo headless (padrão).",
    )
    exec_group.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Executa o navegador com interface gráfica.",
    )
    exec_group.add_argument(
        "--timeout",
        type=int,
        default=60000,
        help="Tempo limite em milissegundos (padrão: 60000).",
    )

    # Opções de cookies
    cookie_group = parser.add_argument_group("Opções de Cookies")
    cookie_group.add_argument(
        "--cookies-from-browser",
        choices=["chrome", "edge"],
        help="Importa cookies do navegador especificado.",
    )
    cookie_group.add_argument(
        "--cookies",
        help="Caminho para um arquivo de cookies (.txt ou .json).",
    )

    # Saída
    output_group = parser.add_argument_group("Saída")
    output_group.add_argument(
        "--output", "-o",
        help="Caminho para salvar o arquivo .m3u resultante.",
    )

    args = parser.parse_args()

    # Comando: listar perfis
    if args.list_profiles:
        print_available_profiles()
        return

    # Valida que há URLs para processar
    if not args.urls:
        parser.print_help()
        console.print("\n[bold red]Erro:[/] Forneça ao menos uma URL ou use --list-profiles.")
        return

    # Exibe aviso se --use-profile for usado sem --no-headless
    if args.use_profile and args.headless:
        console.print(
            "[bold yellow]Aviso:[/] --use-profile funciona melhor com --no-headless "
            "em alguns sistemas. Se houver problemas, adicione --no-headless."
        )

    extractor = M3U8Extractor(
        headless=args.headless,
        timeout=args.timeout,
        cookies_from_browser=args.cookies_from_browser,
        cookies_file=args.cookies,
        browser=args.browser,
        profile_name=args.profile,
        use_profile=args.use_profile,
    )

    plugin_manager = PluginManager()

    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for url in args.urls:
            res = await process_url(url, extractor, plugin_manager, progress)
            results.append(res)

    # Salva arquivo .m3u se solicitado
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for res in results:
                if res["m3u8_urls"]:
                    main_url = next(
                        (u for u in res["m3u8_urls"] if "playlist.m3u8" in u.lower()),
                        res["m3u8_urls"][0],
                    )
                    logo = f' tvg-logo="{res["thumbnail"]}"' if res["thumbnail"] else ""
                    display_title = (
                        res["title"] if res["title"] != "Stream"
                        else f"Stream de {res['source_url']}"
                    )
                    f.write(f'#EXTINF:-1{logo} group-title="ALLFINDER STREAMS", {display_title}\n')
                    f.write(f"{main_url}\n")
        console.print(f"\n[bold green]✓[/] Arquivo '[bold cyan]{args.output}[/]' gerado com sucesso!")

    else:
        console.print("\n[bold cyan]Resultados da Extração:[/]")
        for res in results:
            if res["title"] == "Erro":
                continue
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
