import asyncio
import sys
import os

# Adiciona o diretório raiz do projeto ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from allfinder.core.extractor import M3U8Extractor

async def debug_extraction():
    print("[*] Iniciando depuração da extração da Fox News...")
    
    # Garante que os navegadores do Playwright estejam instalados


    extractor = M3U8Extractor(headless=True, timeout=120000) # Aumentar o timeout para 2 minutos
    fox_news_url = "https://www.foxnews.com/video/5614615980001"

    print(f"[*] Iniciando extração para: {fox_news_url}")
    try:
        result = await extractor.extract(fox_news_url)
        print("[*] Extração concluída. Resultados:")
        print(f"Título: {result.get('title')}")
        print(f"M3U8 URLs: {result.get('m3u8_urls')}")
        print(f"Thumbnail: {result.get('thumbnail')}")
        print(f"DRM Data: {result.get('drm')}")
    except Exception as e:
        print(f"[!!!] Erro durante a extração: {e}")

if __name__ == "__main__":
    asyncio.run(debug_extraction())
