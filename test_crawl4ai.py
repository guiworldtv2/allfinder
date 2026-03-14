
import asyncio
import json
from crawl4ai import AsyncWebCrawler as Crawl4AI
from allfinder.core.network_capture import DRMInfo

async def test_crawl4ai(url):
    print(f"[*] Testando Crawl4AI para a URL: {url}")
    try:
        crawl4ai = Crawl4AI()
        result = await crawl4ai.arun(url=url)

        found_urls = []
        drm_info = None

        print("\n--- Objeto CrawlResult completo ---")
        print(result.model_dump_json(indent=2) if hasattr(result, 'model_dump_json') else result)
        print("-----------------------------------")

        if result and result.get("media"):
            for video in result["media"].get("videos", []):
                if video.get("src") and (".m3u8" in video.get("src") or ".mpd" in video.get("src")):
                    found_urls.append(video.get("src"))
            for audio in result["media"].get("audios", []):
                if audio.get("src") and (".m3u8" in audio.get("src") or ".mpd" in audio.get("src")):
                    found_urls.append(audio.get("src"))
            if found_urls:
                print(f"[*] Crawl4AI encontrou {len(found_urls)} URLs de mídia.")

        if result and result.get("drm_info"):
            c4ai_drm = result.get("drm_info")
            drm_info = DRMInfo(
                license_url=c4ai_drm.get("license_url"),
                pssh=c4ai_drm.get("pssh"),
                kid=c4ai_drm.get("kid"),
            )
            if drm_info.license_url or drm_info.pssh or drm_info.kid:
                print("[*] Crawl4AI encontrou informações de DRM.")

        print("\n--- Resultados do Crawl4AI ---")
        print(f"URLs de Mídia: {found_urls}")
        print(f"Informações de DRM: {drm_info}")
        print("-----------------------------")

    except Exception as e:
        print(f"[!] Erro ao executar Crawl4AI: {e}")

if __name__ == "__main__":
    test_url = "https://www.foxnews.com/video/5614615980001"
    asyncio.run(test_crawl4ai(test_url))
