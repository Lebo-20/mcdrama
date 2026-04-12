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
    """Downloads with robust 3x retry logic and URL normalization."""
    from api import get_episode_play_url, fix_url
    import random
    
    current_url = fix_url(url)
    
    for attempt in range(1, retries + 1):
        if not current_url:
            # If initial URL is empty, try to fetch from /play immediately
            logger.info(f"🔄 Ep {ep_num}: Initial URL empty, fetching from /play...")
            current_url = await get_episode_play_url(book_id, ep_num)
            
        if not current_url:
            logger.warning(f"⚠️ Ep {ep_num}: No URL available (Attempt {attempt})")
        else:
            try:
                success = await download_single(client, current_url, filepath)
                if success: 
                    logger.info(f"✅ Ep {ep_num}: Download successful.")
                    return True
            except Exception as e:
                logger.warning(f"❌ Ep {ep_num} failed (Attempt {attempt}): {e}")

        if attempt < retries:
            delay = random.uniform(2, 5)
            logger.info(f"⏳ Retrying ep {ep_num} in {delay:.1f}s...")
            await asyncio.sleep(delay)
            # On second/third attempt, always try to refresh URL from API
            current_url = await get_episode_play_url(book_id, ep_num)
            
    logger.error(f"💀 Ep {ep_num}: All {retries} attempts failed.")
    return False

from utils import get_progress_bar

async def download_all_episodes(
    episodes: list, download_dir: str, book_id: str = "0",
    semaphore_count: int = 3, status_msg = None, title: str = "Drama"
) -> bool:
    os.makedirs(download_dir, exist_ok=True)
    semaphore = asyncio.Semaphore(semaphore_count)
    total_downloaded = 0
    
    # We now accept episodes even if they don't have a URL initially
    # We will fetch them during the download process using /play endpoint
    episode_list = []
    for ep in episodes:
        num = ep.get("episode")
        if num:
            url = ep.get("play_url") or ep.get("playUrl") or ep.get("url") or ""
            episode_list.append((int(num), url))

    total_available = len(episode_list)
    if total_available == 0:
        logger.warning(f"⚠️ No valid episode numbers found for {book_id}")
        return False

    async with httpx.AsyncClient(timeout=60, headers=BROWSER_HEADERS, limits=httpx.Limits(max_connections=semaphore_count)) as cdn_client, \
               httpx.AsyncClient(timeout=30) as api_client:

        async def limited_download(ep_num: int, url: str) -> bool:
            nonlocal total_downloaded
            async with semaphore:
                filepath = os.path.join(download_dir, f"episode_{ep_num:03d}.mp4")
                # download_episode_smart already has logic to fetch fresh URL if 'url' is empty or fails
                success = await download_episode_smart(cdn_client, api_client, book_id, ep_num, url, filepath)
                if success:
                    total_downloaded += 1
                    if status_msg:
                        try:
                            bar = get_progress_bar(total_downloaded, total_available)
                            await status_msg.edit(f"🎬 **Download: {title}**\n`{bar}`\n✅ {total_downloaded}/{total_available}")
                        except: pass
                return success

        tasks = [limited_download(n, u) for n, u in sorted(episode_list)]
        results = await asyncio.gather(*tasks)
    
    return sum(results) > 0
