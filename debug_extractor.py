import asyncio
import sys
import os

# Adicionar o diretório raiz do allfinder ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'allfinder')))

from core.extractor import M3U8Extractor

async def debug_extraction(url: str):
    print(f"[*] Iniciando depuração para: {url}")
    extractor = M3U8Extractor(headless=True, timeout=300000) # Aumentar o timeout para depuração
    try:
        result = await extractor.extract(url)
        print("[*] Extração concluída.")
        print(f"Título: {result.get('title', 'N/A')}")
        print(f"M3U8 URLs: {result.get('m3u8_urls', 'N/A')}")
        print(f"Thumbnail: {result.get('thumbnail', 'N/A')}")
        print(f"DRM Data: {result.get('drm', 'N/A')}")
    except Exception as e:
        print(f"[!!!] Erro durante a depuração: {e}")

if __name__ == "__main__":
    test_url = "https://cdn.bitmovin.com/content/assets/art-of-motion_drm/mpds/11331.mpd"
    asyncio.run(debug_extraction(test_url))
