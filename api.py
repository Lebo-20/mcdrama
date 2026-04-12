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
        return detail["episodes"]
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
    """Searches dramas by keyword."""
    all_dramas = []
    
    async with httpx.AsyncClient(timeout=30, headers=API_HEADERS) as client:
        for page in range(1, pages + 1):
            url = f"{BASE_URL}/list"
            params = {
                "lang": "id",
                "code": AUTH_CODE,
                "page": page,
                "limit": 20,
                "keyword": keyword
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

# MicroDrama Unified Trending/Home Logic
async def get_trending_dramas():
    """Fetches trending/home dramas using MicroDrama API Page 1 as default."""
    # Since MicroDrama API is now the primary, we fallback to latest page 1 for trending
    return await get_latest_dramas(pages=1)

async def get_home_dramas():
    """Alias for trending/home dramas using MicroDrama API."""
    return await get_trending_dramas()
