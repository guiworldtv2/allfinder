
import asyncio
from crawl4ai import AsyncWebCrawler as Crawl4AI
from allfinder.core.network_capture import DRMInfo

async def test_crawl4ai(url):
    print(f"[*] Testando Crawl4AI para a URL: {url}")
    try:
        crawl4ai = Crawl4AI()
        result = await crawl4ai.arun(url=url)

        found_urls = []
        drm_info = None

        if result and result.media:
            for video in result.media.videos:
                if video.src and (".m3u8" in video.src or ".mpd" in video.src):
                    found_urls.append(video.src)
            for audio in result.media.audios:
                if audio.src and (".m3u8" in audio.src or ".mpd" in audio.src):
                    found_urls.append(audio.src)
            if found_urls:
                print(f"[*] Crawl4AI encontrou {len(found_urls)} URLs de mídia.")

        if result and hasattr(result, 'drm_info') and result.drm_info:
            c4ai_drm = result.drm_info
            drm_info = DRMInfo(
                license_url=getattr(c4ai_drm, 'license_url', None),
                pssh=getattr(c4ai_drm, 'pssh', None),
                kid=getattr(c4ai_drm, 'kid', None),
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
