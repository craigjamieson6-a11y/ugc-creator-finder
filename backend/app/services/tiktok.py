import asyncio
import random
import httpx
from typing import Optional

from app.config import get_settings


# User-Agent rotation pool (modern desktop browsers)
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]

# Search queries in two tiers (no Twitter-style operators — plain text for TikTok)
UGC_SEARCH_QUERIES = [
    # --- Tier 1: Broad UGC discovery ---
    "UGC creator",
    "#ugccreator",
    "#ugccontent",
    "brand partner content creator",
    "dm for collabs",
    "pr friendly creator",
    "honest review creator",
    "brand ambassador creator",
    "UGC content creator",
    "#ugccommunity",
    "product review creator",
    "unboxing creator",
    "sponsored content creator",
    # --- Tier 2: Demo-targeted (female + age signals) ---
    "UGC creator mom",
    "UGC creator over 40",
    "#genxcreator",
    "#midlifecreator",
    "mom content creator UGC",
    "UGC creator woman",
    "#momcreator",
    "content creator mom life",
    "UGC mama",
    "empty nester creator",
    "midlife content creator",
    "UGC creator wife",
    "#ugcmom",
    "brand partner mom",
    "product review mom",
    "over 40 content creator",
    "gen x content creator",
]

# Keywords that signal a UGC creator in their bio
UGC_BIO_KEYWORDS = [
    "ugc", "content creator", "brand partner", "product review",
    "honest review", "unboxing", "creator for brands", "brand ambassador",
    "collab", "sponsored", "pr friendly", "dm for collabs",
    "content creation", "freelance creator", "creator", "influencer",
    "reviewer", "pr", "gifted",
]


class TikTokService:
    """Search TikTok's web API for UGC creators."""

    def __init__(self):
        settings = get_settings()
        self.enabled = settings.tiktok_enabled
        self.proxy_url = settings.tiktok_proxy_url or None
        self.search_url = "https://www.tiktok.com/api/search/user/full/"

    def _is_configured(self) -> bool:
        return self.enabled

    def _headers(self) -> dict:
        ua = random.choice(_USER_AGENTS)
        return {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.tiktok.com/search",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
        }

    def _cookies(self) -> dict:
        """Minimal cookies to look like a real browser session."""
        web_id = str(random.randint(10**18, 10**19 - 1))
        return {
            "tt_webid": web_id,
            "ttwid": web_id,
            "tt_csrf_token": "".join(random.choices("abcdef0123456789", k=16)),
        }

    async def search_creators(
        self,
        query: Optional[str] = None,
        min_followers: int = 1000,
        niche: Optional[str] = None,
        max_results: int = 20,
        deep_search: bool = False,
    ) -> list[dict]:
        """Search TikTok for UGC creators via their web search API.

        Makes multiple API calls with different UGC queries to maximize
        discovery, then deduplicates by user ID.

        When deep_search=True, paginates deeper per query (8 pages vs 2).
        """
        if not self._is_configured():
            return []

        internal_cap = max_results if not deep_search else 500

        if query:
            queries = [query]
        else:
            queries = list(UGC_SEARCH_QUERIES)
            if niche:
                queries.append(f"{niche} UGC creator")
                queries.append(f"{niche} content creator mom")

        seen_ids: set[str] = set()
        all_creators: list[dict] = []

        for search_query in queries:
            if len(all_creators) >= internal_cap:
                break

            max_pages = 8 if deep_search else 2
            cursor = 0

            for _page in range(max_pages):
                if len(all_creators) >= internal_cap:
                    break

                users, next_cursor, has_more = await self._run_user_search(
                    search_query, cursor=cursor,
                )

                for user_entry in users:
                    user_info = user_entry.get("user_info", {})
                    stats = user_entry.get("stats", {})
                    uid = user_info.get("uid", "")

                    if not uid or uid in seen_ids:
                        continue
                    seen_ids.add(uid)

                    bio = user_info.get("signature", "")
                    followers = stats.get("follower_count", 0)
                    username = user_info.get("unique_id", "")
                    name = user_info.get("nickname", "")

                    # Score how "UGC-like" this user is
                    bio_lower = bio.lower()
                    bio_score = sum(1 for kw in UGC_BIO_KEYWORDS if kw in bio_lower)

                    # Skip obvious non-creators
                    if bio_score == 0 and followers > 500000:
                        continue

                    # Extract avatar URL
                    avatar = ""
                    avatar_obj = user_info.get("avatar_larger", {})
                    if isinstance(avatar_obj, dict):
                        url_list = avatar_obj.get("url_list", [])
                        avatar = url_list[0] if url_list else ""
                    elif isinstance(avatar_obj, str):
                        avatar = avatar_obj

                    all_creators.append({
                        "userId": f"tiktok_{uid}",
                        "profile": {
                            "fullname": name,
                            "username": username,
                            "url": f"https://www.tiktok.com/@{username}",
                            "picture": avatar,
                            "bio": bio,
                            "followers": followers,
                            "following": stats.get("following_count", 0),
                            "engagementRate": self._estimate_engagement_rate(stats),
                            "postCount": stats.get("video_count", 0),
                            "interests": [niche] if niche else self._infer_niches(bio),
                        },
                    })

                if not has_more or next_cursor is None:
                    break
                cursor = next_cursor

                # Anti-bot: random delay between pages
                await asyncio.sleep(random.uniform(1.0, 3.0))

        return all_creators[:internal_cap]

    async def _run_user_search(
        self, search_query: str, cursor: int = 0,
    ) -> tuple[list[dict], Optional[int], bool]:
        """Execute a single TikTok user search.

        Returns (user_list, next_cursor, has_more).
        """
        params = {
            "keyword": search_query,
            "cursor": cursor,
            "search_source": "normal_search",
            "query_type": "",
            "from_page": "search",
        }

        client_kwargs: dict = {"timeout": 30}
        if self.proxy_url:
            client_kwargs["proxy"] = self.proxy_url

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.get(
                        self.search_url,
                        headers=self._headers(),
                        cookies=self._cookies(),
                        params=params,
                    )

                    if resp.status_code in (403, 429):
                        if attempt < max_retries:
                            backoff = random.uniform(5.0, 15.0)
                            await asyncio.sleep(backoff)
                            continue
                        return [], None, False

                    resp.raise_for_status()
                    data = resp.json()
            except (httpx.HTTPError, ValueError):
                # ValueError catches json.JSONDecodeError (TikTok returning HTML)
                if attempt < max_retries:
                    await asyncio.sleep(random.uniform(2.0, 5.0))
                    continue
                return [], None, False

            user_list = data.get("user_list", [])
            has_more = data.get("has_more", False)
            next_cursor = data.get("cursor")
            if next_cursor is not None:
                next_cursor = int(next_cursor)
            return user_list, next_cursor, has_more

        return [], None, False

    @staticmethod
    def _estimate_engagement_rate(stats: dict) -> float:
        """Estimate engagement rate from TikTok stats."""
        followers = stats.get("follower_count", 0)
        hearts = stats.get("heart_count", 0)
        videos = stats.get("video_count", 0)

        if followers == 0 or videos == 0:
            return 0.0

        avg_likes_per_video = hearts / videos
        estimated = (avg_likes_per_video / followers) * 100
        return round(min(20.0, max(0.1, estimated)), 2)

    @staticmethod
    def _infer_niches(bio: str) -> list[str]:
        """Infer niche tags from bio text."""
        bio_lower = bio.lower()
        niche_keywords = {
            "beauty": ["beauty", "skincare", "makeup", "cosmetic"],
            "fitness": ["fitness", "workout", "gym", "training", "exercise"],
            "food": ["food", "recipe", "cook", "chef", "baking"],
            "fashion": ["fashion", "style", "outfit", "clothing"],
            "travel": ["travel", "adventure", "explore", "wanderlust"],
            "health": ["health", "wellness", "nutrition", "supplement"],
            "lifestyle": ["lifestyle", "daily", "life", "mom", "mother"],
            "home": ["home", "decor", "interior", "diy", "garden"],
            "parenting": ["parent", "mom", "dad", "baby", "kids"],
            "education": ["education", "teach", "learn", "book"],
        }
        found = []
        for niche, keywords in niche_keywords.items():
            if any(kw in bio_lower for kw in keywords):
                found.append(niche)
        return found if found else ["ugc"]
