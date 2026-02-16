import httpx
from typing import Optional

from app.config import get_settings


# Search queries in two tiers:
# Tier 1: Broad UGC queries to cast the widest net
# Tier 2: Demo-targeted queries combining UGC + female/age signals
UGC_SEARCH_QUERIES = [
    # --- Tier 1: Broad UGC discovery (find all UGC creators) ---
    '"UGC creator" -is:retweet',
    '#ugccreator -is:retweet',
    '#ugccontent -is:retweet',
    '"content creator" "brand partner" -is:retweet',
    '"dm for collabs" OR "pr friendly" -is:retweet',
    '"honest review" creator -is:retweet',
    '"brand ambassador" creator -is:retweet',
    # --- Tier 2: Demo-targeted (female + age signals) ---
    '"UGC creator" (mom OR woman OR she/her OR wife) -is:retweet',
    '"UGC creator" (mother OR mama OR queen) -is:retweet',
    '"content creator" ("over 40" OR "over 50" OR midlife OR "gen x") -is:retweet',
    '"content creator" (mom OR woman OR she/her) -is:retweet',
    '#ugccontent (mom OR mother OR "empty nester" OR grandma) -is:retweet',
    '#ugccreator (woman OR she/her OR wife OR mama) -is:retweet',
    '"brand partner" (woman OR mom OR "40s" OR "50s") -is:retweet',
    '"brand ambassador" (mom OR mother OR woman OR wife) -is:retweet',
    '"honest review" (mom OR woman OR "over 40" OR "over 50") -is:retweet',
    '"content creator" ("mom of teens" OR "empty nester" OR "gen x") -is:retweet',
    '("UGC" OR "ugc creator") ("40s" OR "50s" OR midlife OR "middle age") -is:retweet',
    '("product review" OR "unboxing") (mom OR woman OR "over 40") -is:retweet',
    '"mom creator" (UGC OR brand OR review OR collab) -is:retweet',
    '("pr friendly" OR "dm for collabs") (mom OR she/her OR woman) -is:retweet',
]

# Keywords that signal a UGC creator in their bio
UGC_BIO_KEYWORDS = [
    "ugc", "content creator", "brand partner", "product review",
    "honest review", "unboxing", "creator for brands", "brand ambassador",
    "collab", "sponsored", "pr friendly", "dm for collabs",
    "content creation", "freelance creator", "creator", "influencer",
    "reviewer", "pr", "gifted",
]


class TwitterService:
    """Search Twitter/X API v2 for UGC creators."""

    def __init__(self):
        settings = get_settings()
        self.bearer_token = settings.twitter_bearer_token
        self.base_url = "https://api.twitter.com/2"

    def _is_configured(self) -> bool:
        return bool(self.bearer_token)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

    async def search_creators(
        self,
        query: Optional[str] = None,
        min_followers: int = 1000,
        niche: Optional[str] = None,
        max_results: int = 20,
        deep_search: bool = False,
    ) -> list[dict]:
        """Search Twitter for UGC creators via recent tweet search.

        Makes multiple API calls with different UGC queries to maximize
        discovery, then deduplicates by user ID.

        When deep_search=True, paginates through results for each query
        to collect maximum volume (up to 500 users).
        """
        if not self._is_configured():
            return []

        # In deep_search mode, raise the internal cap
        internal_cap = max_results if not deep_search else 500

        # Build list of queries to run
        if query:
            queries = [query]
        else:
            queries = list(UGC_SEARCH_QUERIES)
            if niche:
                queries.append(f'("{niche} creator" OR "{niche} UGC") (mom OR woman OR "over 40") -is:retweet')

        seen_ids = set()
        all_creators = []

        for search_query in queries:
            # Stop once we have enough results
            if len(all_creators) >= internal_cap:
                break

            # Use pagination to get more results per query
            max_pages = 10 if deep_search else 2
            next_token = None

            for _page in range(max_pages):
                if len(all_creators) >= internal_cap:
                    break

                users, next_token = await self._run_search_paginated(
                    search_query, max_results=100, next_token=next_token,
                )

                for user in users:
                    uid = user.get("id", "")
                    if uid in seen_ids:
                        continue
                    seen_ids.add(uid)

                    bio = user.get("description", "")
                    metrics = user.get("public_metrics", {})
                    followers = metrics.get("followers_count", 0)

                    username = user.get("username", "")
                    name = user.get("name", "")

                    # Score how "UGC-like" this user is
                    bio_lower = bio.lower()
                    bio_score = sum(1 for kw in UGC_BIO_KEYWORDS if kw in bio_lower)

                    # Skip obvious non-creators
                    if bio_score == 0 and followers > 500000:
                        continue

                    all_creators.append({
                        "userId": f"twitter_{uid}",
                        "profile": {
                            "fullname": name,
                            "username": username,
                            "url": f"https://twitter.com/{username}",
                            "picture": user.get("profile_image_url", "").replace("_normal", "_400x400"),
                            "bio": bio,
                            "followers": followers,
                            "following": metrics.get("following_count", 0),
                            "engagementRate": self._estimate_engagement_rate(metrics),
                            "postCount": metrics.get("tweet_count", 0),
                            "interests": [niche] if niche else self._infer_niches(bio),
                        },
                    })

                # No more pages available
                if not next_token:
                    break

        return all_creators[:internal_cap]

    async def _run_search_paginated(
        self, search_query: str, max_results: int = 100, next_token: Optional[str] = None,
    ) -> tuple[list[dict], Optional[str]]:
        """Execute a single tweet search and return (user objects, next_token)."""
        params = {
            "query": search_query,
            "max_results": min(max(max_results, 10), 100),  # API min 10, max 100
            "expansions": "author_id",
            "tweet.fields": "created_at,public_metrics",
            "user.fields": "name,username,description,profile_image_url,public_metrics,url",
        }
        if next_token:
            params["next_token"] = next_token

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/tweets/search/recent",
                    headers=self._headers(),
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return [], None

        users = data.get("includes", {}).get("users", [])
        result_next_token = data.get("meta", {}).get("next_token")
        return users, result_next_token

    async def _run_search(self, search_query: str, max_results: int = 20) -> list[dict]:
        """Execute a single tweet search and return the expanded user objects."""
        users, _ = await self._run_search_paginated(search_query, max_results)
        return users

    async def search_users(
        self,
        query: str = "UGC creator",
        max_results: int = 20,
    ) -> list[dict]:
        """Search Twitter users by keyword (uses tweet search as proxy)."""
        return await self.search_creators(query=query, max_results=max_results)

    @staticmethod
    def _estimate_engagement_rate(metrics: dict) -> float:
        """Estimate engagement rate from public metrics."""
        followers = metrics.get("followers_count", 0)
        listed = metrics.get("listed_count", 0)

        if followers == 0:
            return 0.0

        list_ratio = (listed / followers) * 100 if followers > 0 else 0
        estimated = min(10.0, max(0.5, list_ratio * 5 + 1.0))
        return round(estimated, 2)

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
