import os
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)

# ─── Browser-like Headers ───────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://farsunpteltd.com/",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ─── API config ─────────────────────────────────────────────────────
API_BASE = "https://drakula.dramabos.my.id/api/microdrama"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"

# ────────────────────────────────────────────────────────────────────
#  FRESH URL FETCHER (MicroDramas version)
# ────────────────────────────────────────────────────────────────────
async def fetch_fresh_urls(book_id: str, api_client: httpx.AsyncClient) -> dict:
    """
    Calls /drama/id to get fresh episode URLs for MicroDramas.
    Returns dict: {episode_number: play_url}
    """
    url = f"{API_BASE}/drama/{book_id}"
    params = {"lang": "id", "code": AUTH_CODE}

    try:
        resp = await api_client.get(url, params=params, timeout=30)
        resp.raise_for_status()
        json_data = resp.json()
        data = json_data.get("data", {}) if isinstance(json_data, dict) else {}
        
        episodes = data.get("episodes", [])
        url_map = {}
        for ep in episodes:
            ep_num = ep.get("episode")
            play_url = ep.get("play_url") or ep.get("playUrl") or ep.get("url")
            if ep_num and play_url:
                url_map[int(ep_num)] = play_url

        return url_map
    except Exception as e:
        logger.error(f"❌ Failed to fetch fresh URLs for {book_id}: {e}")
        return {}

# ────────────────────────────────────────────────────────────────────
#  SINGLE FILE DOWNLOADER
# ────────────────────────────────────────────────────────────────────
async def download_single(client: httpx.AsyncClient, url: str, path: str) -> bool:
    """Downloads a single video file."""
    is_hls = ".m3u8" in url.split("?")[0].lower()

    if is_hls:
        headers_str = "".join(f"{k}: {v}\r\n" for k, v in BROWSER_HEADERS.items())
        cmd = [
            "ffmpeg", "-y",
            "-user_agent", BROWSER_HEADERS["User-Agent"],
            "-headers", headers_str,
            "-i", url,
            "-c", "copy", "-bsf:a", "aac_adtstoasc",
            path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            return True
        logger.warning(f"FFmpeg failed: {stderr.decode()[:200]}")
        return False
    else:
        async with client.stream("GET", url, timeout=60) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
        return True

async def download_episode_smart(
    client: httpx.AsyncClient, api_client: httpx.AsyncClient,
    book_id: str, ep_num: int, url: str, filepath: str, retries: int = 3
) -> bool:
    """Downloads with retry logic."""
    current_url = url
    for attempt in range(1, retries + 1):
        try:
            success = await download_single(client, current_url, filepath)
            if success: return True
        except Exception as e:
            logger.warning(f"Download error ep {ep_num} (Attempt {attempt}): {e}")
            if attempt < retries:
                # On 403 or error, try to refresh URLs
                fresh_map = await fetch_fresh_urls(book_id, api_client)
                if ep_num in fresh_map: current_url = fresh_map[ep_num]
        await asyncio.sleep(2)
    return False

from utils import get_progress_bar

async def download_all_episodes(
    episodes: list, download_dir: str, book_id: str = "0",
    semaphore_count: int = 3, status_msg = None, title: str = "Drama"
) -> bool:
    os.makedirs(download_dir, exist_ok=True)
    semaphore = asyncio.Semaphore(semaphore_count)
    total_downloaded = 0
    total_lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=60, headers=BROWSER_HEADERS) as cdn_client, \
               httpx.AsyncClient(timeout=30) as api_client:

        # Use episodes provided, or fetch fresh if 403 occurs
        url_map = {}
        for ep in episodes:
            num = ep.get("episode")
            url = ep.get("play_url") or ep.get("playUrl") or ep.get("url")
            if num and url: url_map[int(num)] = url

        total_available = len(url_map)
        if total_available == 0: return False

        async def limited_download(ep_num: int, url: str) -> bool:
            nonlocal total_downloaded
            async with semaphore:
                filepath = os.path.join(download_dir, f"episode_{ep_num:03d}.mp4")
                success = await download_episode_smart(cdn_client, api_client, book_id, ep_num, url, filepath)
                if success:
                    async with total_lock:
                        total_downloaded += 1
                        if status_msg:
                            try:
                                bar = get_progress_bar(total_downloaded, total_available)
                                await status_msg.edit(f"🎬 **Download: {title}**\n`{bar}`\n✅ {total_downloaded}/{total_available}")
                            except: pass
                return success

        tasks = [limited_download(n, u) for n, u in sorted(url_map.items())]
        results = await asyncio.gather(*tasks)
    return sum(results) > 0
