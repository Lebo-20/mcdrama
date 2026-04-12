import httpx
import logging

logger = logging.getLogger(__name__)

# MicroDramas API Configuration
BASE_URL = "https://drakula.dramabos.my.id/api/microdrama"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"

# Headers for API calls
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

async def get_drama_detail(book_id: str):
    url = f"{BASE_URL}/drama/{book_id}"
    params = {
        "lang": "id",
        "code": AUTH_CODE
    }
    
    async with httpx.AsyncClient(timeout=30, headers=API_HEADERS) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data and isinstance(data, dict):
                if data.get("success") and "data" in data:
                    return data["data"]
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching drama detail for {book_id}: {e}")
            return None

async def get_all_episodes(book_id: str, detail: dict = None):
    # If detail is provided, use it, otherwise fetch
    if not detail:
        detail = await get_drama_detail(book_id)
        
    if detail and "episodes" in detail:
        eps = detail["episodes"]
        if eps:
            logger.info(f"✅ Found {len(eps)} episodes for {book_id}")
            return eps
    
    logger.warning(f"⚠️ No episodes found in API response for {book_id}. Response Keys: {list(detail.keys()) if detail else 'None'}")
    return []

async def get_latest_dramas(pages=1):
    """Fetches latest dramas from MicroDramas API."""
    all_dramas = []
    
    async with httpx.AsyncClient(timeout=30, headers=API_HEADERS) as client:
        for page in range(1, pages + 1):
            url = f"{BASE_URL}/list"
            params = {
                "lang": "id",
                "code": AUTH_CODE,
                "page": page,
                "limit": 20
            }
                
            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and "data" in data:
                        items_data = data["data"]
                        items = items_data.get("data", [])
                        if not items:
                            break
                        all_dramas.extend(items)
                    else:
                        break
                else:
                    break
            except Exception as e:
                logger.error(f"Error fetching list page {page}: {e}")
                break
    
    return all_dramas

async def search_dramas(keyword: str, pages=1):
    """Searches dramas by keyword using /search endpoint with 'q' parameter."""
    all_dramas = []
    
    async with httpx.AsyncClient(timeout=30, headers=API_HEADERS) as client:
        for page in range(1, pages + 1):
            url = f"{BASE_URL}/search"
            params = {
                "q": keyword, # Official param is 'q'
                "lang": "id",
                "code": AUTH_CODE,
                "page": page,
                "limit": 20
            }
                
            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and "data" in data:
                        items_data = data["data"]
                        items = items_data.get("data", [])
                        if not items:
                            break
                        all_dramas.extend(items)
                    else:
                        break
                else:
                    break
            except Exception as e:
                logger.error(f"Error searching page {page}: {e}")
                break
    
    return all_dramas

def fix_url(url: str):
    """Normalizes URL by adding missing protocol or domain."""
    if not url:
        return None
        
    BASE_DOMAIN = "https://drakula.dramabos.my.id"

    # Fix relative paths like //cdn.com
    if url.startswith("//"):
        return "https:" + url

    # Fix relative paths like /api/v1/...
    if url.startswith("/"):
        return BASE_DOMAIN + url

    # Fix missing protocol entirely
    if not url.startswith("http"):
        return "https://" + url

    return url

async def get_episode_play_url(drama_id: str, episode_no: int):
    """Fetches playback URL with robust extraction and URL fixing."""
    url = f"{BASE_URL}/play/{drama_id}/{episode_no}"
    params = {"lang": "id", "code": AUTH_CODE}
    
    logger.info(f"🔍 Fetching Play URL for Drama: {drama_id}, Ep: {episode_no}")
    
    async with httpx.AsyncClient(timeout=20, headers=API_HEADERS) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(f"⚠️ API Return {response.status_code} for ep {episode_no}")
                return None
                
            data = response.json()
            if not data.get("success") or "data" not in data:
                logger.warning(f"⚠️ API Response Success=False for ep {episode_no}")
                return None
                
            item = data["data"]
            # Look for video URL in multiple possible fields
            raw_url = item.get("play_url") or item.get("url") or item.get("playUrl") or item.get("video_url")
            
            if not raw_url:
                logger.warning(f"⚠️ No video URL found in JSON for ep {episode_no}")
                return None
                
            fixed_url = fix_url(raw_url)
            logger.info(f"✅ URL Fixed: {raw_url[:30]}... -> {fixed_url[:60]}...")
            
            return fixed_url
        except Exception as e:
            logger.error(f"❌ Error fetching play URL for {drama_id} ep {episode_no}: {e}")
            return None

# MicroDrama Unified Trending/Home Logic
async def get_trending_dramas():
    """Fetches trending/home dramas using MicroDrama API Page 1 as default."""
    # Since MicroDrama API is now the primary, we fallback to latest page 1 for trending
    return await get_latest_dramas(pages=1)

async def get_home_dramas():
    """Alias for trending/home dramas using MicroDrama API."""
    return await get_trending_dramas()
