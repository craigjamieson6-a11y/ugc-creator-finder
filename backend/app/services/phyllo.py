import httpx
from typing import Optional

from app.config import get_settings


class PhylloService:
    """Secondary/fallback service for platforms not covered by Modash (Facebook, Pinterest)."""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.phyllo_api_key
        self.base_url = settings.phyllo_base_url
        self.headers = {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
        }

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    async def search_creators(
        self,
        platform: str = "facebook",
        min_followers: int = 1000,
        niche: Optional[str] = None,
        page: int = 0,
        page_size: int = 20,
    ) -> dict:
        if not self._is_configured():
            return self._mock_search(platform, niche, page_size)

        params = {
            "platform": platform,
            "min_followers": min_followers,
            "limit": page_size,
            "offset": page * page_size,
        }
        if niche:
            params["category"] = niche

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/creators/search",
                headers=self.headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_creator_profile(self, platform: str, account_id: str) -> dict:
        if not self._is_configured():
            return self._mock_profile(platform, account_id)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/profiles/{account_id}",
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    def _mock_search(self, platform: str, niche: Optional[str], limit: int) -> dict:
        mock_creators = [
            {
                "id": f"mock_{platform}_fb1",
                "name": "Susan Baker",
                "username": "susanbaker_crafts",
                "platform": platform,
                "profile_url": f"https://{platform}.com/susanbaker_crafts",
                "avatar_url": "https://i.pravatar.cc/150?u=susanbaker",
                "bio": "Crafting queen | Mom life | 48 years young",
                "followers": 22000,
                "engagement_rate": 3.1,
                "category": niche or "lifestyle",
            },
            {
                "id": f"mock_{platform}_fb2",
                "name": "Deborah Hayes",
                "username": "debhayes_pins",
                "platform": platform,
                "profile_url": f"https://{platform}.com/debhayes_pins",
                "avatar_url": "https://i.pravatar.cc/150?u=debhayes",
                "bio": "Pin-spiration for women 40+ | Interior design | Recipes",
                "followers": 35000,
                "engagement_rate": 4.5,
                "category": niche or "home",
            },
        ]
        return {"creators": mock_creators[:limit], "total": len(mock_creators)}

    def _mock_profile(self, platform: str, account_id: str) -> dict:
        return {
            "id": account_id,
            "name": "Susan Baker",
            "username": "susanbaker_crafts",
            "platform": platform,
            "bio": "Crafting queen | Mom life | 48 years young",
            "followers": 22000,
            "following": 800,
            "engagement_rate": 3.1,
            "post_count": 420,
            "category": "lifestyle",
        }
