import asyncio
import argparse
import os
from allfinder.core.extractor import run_extractor

async def amain():
    parser = argparse.ArgumentParser(description="Allfinder - Extrator de URLs de mídia.")
    parser.add_argument("url", type=str, help="URL da página para extrair.")
    parser.add_argument("--headless", action="store_true", help="Executar navegador em modo headless.")
    parser.add_argument("--timeout", type=int, default=30000, help="Tempo limite em milissegundos.")
    parser.add_argument("--browser", type=str, default="chromium", help="Navegador a ser usado (chromium, firefox, webkit).")
    parser.add_argument("--use-profile", action="store_true", help="Reutilizar perfil existente do navegador.")
    parser.add_argument("--profile-name", type=str, help="Nome do perfil do navegador.")
    parser.add_argument("--plugin", type=str, help="Nome do plugin a ser usado (ex: rdcanais).")

    args = parser.parse_args()

    results = await run_extractor(
        url=args.url,
        headless=args.headless,
        timeout=args.timeout,
        browser=args.browser,
        use_profile=args.use_profile,
        profile_name=args.profile_name,
        plugin_name=args.plugin,
    )

    if results["urls"]:
        print("URLs de stream encontradas:")
        for u in results["urls"]:
            print(u)
    else:
        print("Nenhuma URL de stream encontrada.")
    
    if results["drm_info"]:
        print("Informações de DRM encontradas:")
        for drm in results["drm_info"]:
            print(drm)

def main():
    asyncio.run(amain())

if __name__ == "__main__":
    main()
