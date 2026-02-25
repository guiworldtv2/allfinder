import asyncio
import argparse
import sys
import os
from typing import List, Dict, Any
from allfinder.core.extractor import M3U8Extractor
from allfinder.plugins.manager import PluginManager
from allfinder.plugins.base import GenericPlugin

def normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url

async def process_url(url: str, extractor: M3U8Extractor, plugin_manager: PluginManager, silent: bool = False) -> Dict[str, Any]:
    url = normalize_url(url)
    plugin = plugin_manager.get_plugin_for_url(url)
    if not silent:
        print(f"\n[*] Processando: {url}")
    data = await extractor.extract(url, plugin.interact)
    return {
        "source_url": url,
        "title": data["title"],
        "m3u8_urls": data["m3u8_urls"],
        "thumbnail": data["thumbnail"],
        "drm": data.get("drm", {})
    }

async def main():
    parser = argparse.ArgumentParser(description="allfinder: Extrai URLs .m3u8 com suporte a perfis, cookies, metadados e DRM.")
    
    parser.add_argument("pos_urls", nargs="*", help="Uma ou mais URLs de sites de streaming.")
    parser.add_argument("--url", dest="opt_urls", action="append", help="Uma URL para extrair streams.")
    
    # Opções de Navegador e Perfil
    group_browser = parser.add_argument_group("Opções de Navegador")
    group_browser.add_argument("--browser", choices=["chrome", "edge", "firefox", "chromium"], default="chromium", help="Navegador a ser usado.")
    group_browser.add_argument("--use-profile", action="store_true", help="Usa um perfil existente do navegador.")
    group_browser.add_argument("--profile", dest="profile_name", help="Nome do perfil do navegador.")
    group_browser.add_argument("--list-profiles", action="store_true", help="Lista perfis detectados e sai.")
    
    # Opções de Execução
    group_exec = parser.add_argument_group("Opções de Execução")
    group_exec.add_argument("--headless", action="store_true", default=True, help="Modo headless (padrão).")
    group_exec.add_argument("--no-headless", action="store_false", dest="headless", help="Modo com interface gráfica.")
    group_exec.add_argument("--timeout", type=int, default=60000, help="Tempo limite em ms.")
    group_exec.add_argument("--cookies", help="Caminho para arquivo de cookies (.txt ou .json).")
    group_exec.add_argument("--cookies-from-browser", choices=["chrome", "edge"], help="Importa cookies do navegador.")
    
    # Saída e Extração Individual
    group_output = parser.add_argument_group("Opções de Saída")
    group_output.add_argument("--output", "-o", help="Salva em arquivo .m3u.")
    group_output.add_argument("--stream-url", action="store_true", help="Exibe apenas a URL do stream.")
    group_output.add_argument("--stream-title", action="store_true", help="Exibe apenas o título.")
    group_output.add_argument("--stream-logo", action="store_true", help="Exibe apenas a URL da logo.")
    group_output.add_argument("--drm-only", action="store_true", help="Exibe APENAS dados de DRM capturados, se houver.")
    
    args = parser.parse_args()

    if args.list_profiles:
        print("[*] Listagem de perfis não implementada neste ambiente (requer acesso ao sistema local).")
        return

    all_urls = (args.pos_urls or []) + (args.opt_urls or [])
    if not all_urls:
        parser.print_help()
        return

    # Determina se o modo de saída é individual (excluindo --drm-only para o comportamento padrão)
    is_individual_output_mode = args.stream_url or args.stream_title or args.stream_logo or args.drm_only
    
    extractor = M3U8Extractor(
        headless=args.headless, 
        timeout=args.timeout, 
        cookie_file=args.cookies,
        browser_type=args.browser,
        use_profile=args.use_profile,
        profile_name=args.profile_name
    )
    
    plugin_manager = PluginManager()
    plugin_manager.register_plugin(GenericPlugin())

    results = []
    for url in all_urls:
        # Passa silent=True apenas se alguma das flags de saída individual estiver ativa
        res = await process_url(url, extractor, plugin_manager, silent=is_individual_output_mode)
        results.append(res)

    # Se a flag --drm-only foi usada, exibe apenas o DRM
    if args.drm_only:
        for res in results:
            print("DRM: " + str(res["drm"]) if res["drm"] else "Sem DRM detectado")
        return

    # Se alguma flag de saída individual (exceto --drm-only) foi usada, exibe apenas o solicitado
    if is_individual_output_mode:
        for res in results:
            if args.stream_url: print(res["m3u8_urls"][0] if res["m3u8_urls"] else "Não encontrado")
            if args.stream_title: print(res["title"])
            if args.stream_logo: print(res["thumbnail"] if res["thumbnail"] else "Não encontrado")
        return

    # Modo de saída padrão (sem flags individuais)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for res in results:
                if res["m3u8_urls"]:
                    logo = " tvg-logo=\"" + str(res["thumbnail"]) + "\"" if res["thumbnail"] else ""
                    title = str(res["title"]) if res["title"] != "Stream" else "Stream de " + str(res["source_url"])
                    
                    drm_tags = ""
                    if res["drm"].get("license_url"):
                        drm_tags += "#KODIPROP:inputstream.adaptive.license_type=widevine\n"
                        drm_tags += "#KODIPROP:inputstream.adaptive.license_key=" + str(res["drm"]["license_url"]) + "\n"
                        if res["drm"].get("pssh"):
                            drm_tags += "#KODIPROP:inputstream.adaptive.manifest_type=mpd\n"
                            drm_tags += "#KODIPROP:inputstream.adaptive.license_data=" + str(res["drm"]["pssh"]) + "\n"
                        if res["drm"].get("kid"):
                            drm_tags += "#KODIPROP:inputstream.adaptive.content_id=" + str(res["drm"]["kid"]) + "\n"
                    
                    f.write(f"#EXTINF:-1{logo} group-title=\"ALLFINDER\",{title}\n{drm_tags}{res["m3u8_urls"][0]}\n")
        print(f"\n[✓] Arquivo \'{args.output}\' gerado com sucesso!")
    else:
        for res in results:
            print("\nTítulo: " + str(res["title"]))
            print("M3U8: " + str(res["m3u8_urls"][0] if res["m3u8_urls"] else "Não encontrado"))
            if res["drm"] and res["drm"].get("license_url"):
                print("DRM Detectado: " + str(res["drm"]))
            if res["thumbnail"]:
                print("Logo: " + str(res["thumbnail"]))

def main_entry():
    asyncio.run(main())

if __name__ == "__main__":
    main_entry()
