import asyncio
import logging
import random
import re
from typing import Optional
from urllib.parse import quote

import httpx
from playwright.async_api import async_playwright, Browser, BrowserContext

from app.config import get_settings

logger = logging.getLogger(__name__)

# Search queries in two tiers:
# Tier 1: Broad UGC queries to cast the widest net
# Tier 2: Demo-targeted queries combining UGC + female/age signals
# Tier 3: Niche-specific queries for leakproof underwear
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
    # --- Tier 3: Leakproof underwear niche ---
    '"period underwear" creator -is:retweet',
    '"leak proof underwear" (review OR creator) -is:retweet',
    '"incontinence" (creator OR review OR UGC) -is:retweet',
    '"pelvic floor" (creator OR review OR mom) -is:retweet',
    '"postpartum" (mom OR creator OR UGC OR review) -is:retweet',
    '"women\'s health" (creator OR UGC) -is:retweet',
]

# Plain-text queries for Nitter scraping (no Twitter operators)
NITTER_SEARCH_QUERIES = [
    "UGC creator",
    "ugc creator mom",
    "content creator over 40",
    "content creator mom",
    "ugc creator woman",
    "brand partner mom review",
    "honest review creator",
    "period underwear creator",
    "leak proof underwear review",
    "incontinence creator",
    "pelvic floor review",
    "postpartum mom UGC",
    "women's health creator",
]

# Keywords that signal a UGC creator in their bio
UGC_BIO_KEYWORDS = [
    "ugc", "content creator", "brand partner", "product review",
    "honest review", "unboxing", "creator for brands", "brand ambassador",
    "collab", "sponsored", "pr friendly", "dm for collabs",
    "content creation", "freelance creator", "creator", "influencer",
    "reviewer", "pr", "gifted",
]

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# Known public Nitter instances (may change over time)
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
]


class TwitterService:
    """Search Twitter/X API v2 for UGC creators, with Nitter scraping fallback."""

    def __init__(self):
        settings = get_settings()
        self.bearer_token = settings.twitter_bearer_token
        self.base_url = "https://api.twitter.com/2"
        self._nitter_playwright = None
        self._nitter_browser: Optional[Browser] = None
        self._nitter_context: Optional[BrowserContext] = None
        self._cached_nitter_instance: Optional[str] = None
        self._nitter_cache_checked: bool = False

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
        """Search Twitter for UGC creators.

        Tries the official API first; falls back to Nitter scraping
        if the API token is missing or stops working.
        """
        # Try the official API first
        if self._is_configured():
            results = await self._search_via_api(query, min_followers, niche, max_results, deep_search)
            if results:
                return results
            logger.info("Twitter API returned no results, trying Nitter fallback")

        # Fallback: Nitter scraping
        return await self._search_via_nitter(query, min_followers, niche, max_results, deep_search)

    async def _search_via_api(
        self,
        query: Optional[str],
        min_followers: int,
        niche: Optional[str],
        max_results: int,
        deep_search: bool,
    ) -> list[dict]:
        """Search using the official Twitter API v2."""
        internal_cap = max_results if not deep_search else 500

        if query:
            # Generate targeted queries — limit to first 2 keyword terms
            terms = [t.strip() for t in query.split(",") if t.strip()][:2]
            queries = []
            for term in terms:
                queries.append(f'"{term}" (creator OR UGC OR "brand partner") -is:retweet')
            # Add one standard UGC query
            queries.append(UGC_SEARCH_QUERIES[0])
        else:
            queries = list(UGC_SEARCH_QUERIES)
            if niche:
                queries.append(f'("{niche} creator" OR "{niche} UGC") (mom OR woman OR "over 40") -is:retweet')

            # For normal search, limit to first 5 queries (Tier 1 broad)
            # Deep search uses all queries for maximum coverage
            if not deep_search:
                queries = queries[:5]

        seen_ids = set()
        all_creators = []

        for search_query in queries:
            if len(all_creators) >= internal_cap:
                break

            max_pages = 10 if deep_search else 1
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

                    bio_lower = bio.lower()
                    bio_score = sum(1 for kw in UGC_BIO_KEYWORDS if kw in bio_lower)

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

                if not next_token:
                    break

        return all_creators[:internal_cap]

    async def _search_via_nitter(
        self,
        query: Optional[str],
        min_followers: int,
        niche: Optional[str],
        max_results: int,
        deep_search: bool,
    ) -> list[dict]:
        """Fallback: scrape Nitter (Twitter frontend mirror) using Playwright."""
        internal_cap = max_results if not deep_search else 200

        if query:
            # Generate targeted queries — limit to first 2 keyword terms
            terms = [t.strip() for t in query.split(",") if t.strip()][:2]
            queries = []
            for term in terms:
                queries.append(f"{term} UGC creator")
        else:
            queries = list(NITTER_SEARCH_QUERIES)
            if niche:
                queries.append(f"{niche} creator")
                queries.append(f"{niche} UGC review")

            # For normal search, limit queries
            if not deep_search:
                queries = queries[:6]

        seen_usernames: set[str] = set()
        all_creators: list[dict] = []

        # Find a working Nitter instance
        nitter_base = await self._find_working_nitter()
        if not nitter_base:
            logger.warning("No working Nitter instance found")
            return []

        for search_query in queries:
            if len(all_creators) >= internal_cap:
                break

            users = await self._scrape_nitter_search(nitter_base, search_query)

            for user in users:
                username = user.get("username", "")
                if not username or username in seen_usernames:
                    continue
                seen_usernames.add(username)

                bio = user.get("bio", "")
                bio_lower = bio.lower()
                bio_score = sum(1 for kw in UGC_BIO_KEYWORDS if kw in bio_lower)

                # Skip obvious non-creators
                if bio_score == 0 and not any(kw in bio_lower for kw in ["mom", "creator", "review", "ugc"]):
                    continue

                all_creators.append({
                    "userId": f"twitter_{username}",
                    "profile": {
                        "fullname": user.get("name", username),
                        "username": username,
                        "url": f"https://twitter.com/{username}",
                        "picture": user.get("avatar", ""),
                        "bio": bio,
                        "followers": user.get("followers", 0),
                        "following": user.get("following", 0),
                        "engagementRate": 1.5,  # Default estimate for Nitter
                        "postCount": user.get("tweets", 0),
                        "interests": [niche] if niche else self._infer_niches(bio),
                    },
                })

            await asyncio.sleep(random.uniform(1.0, 2.5))

        return all_creators[:internal_cap]

    async def _get_nitter_context(self) -> BrowserContext:
        """Get or create a Playwright browser context for Nitter scraping."""
        if self._nitter_context is not None:
            try:
                await self._nitter_context.cookies()
                return self._nitter_context
            except Exception:
                self._nitter_context = None

        if self._nitter_browser is None or not self._nitter_browser.is_connected():
            self._nitter_playwright = await async_playwright().start()
            self._nitter_browser = await self._nitter_playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox"],
            )

        self._nitter_context = await self._nitter_browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
        )
        return self._nitter_context

    async def _find_working_nitter(self) -> Optional[str]:
        """Check known Nitter instances concurrently and return the first that responds.

        Caches the result so subsequent calls don't re-check.
        """
        if self._nitter_cache_checked:
            return self._cached_nitter_instance

        async def _check(instance: str) -> Optional[str]:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(instance, timeout=5, follow_redirects=True)
                    if resp.status_code < 400:
                        return instance
            except Exception:
                return None

        results = await asyncio.gather(*[_check(inst) for inst in NITTER_INSTANCES])
        working = [r for r in results if r is not None]

        self._nitter_cache_checked = True
        self._cached_nitter_instance = working[0] if working else None
        return self._cached_nitter_instance

    async def _scrape_nitter_search(self, nitter_base: str, search_query: str) -> list[dict]:
        """Scrape a Nitter search page for user profiles."""
        try:
            context = await self._get_nitter_context()
            page = await context.new_page()

            url = f"{nitter_base}/search?f=users&q={quote(search_query)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            users = await page.evaluate("""() => {
                const results = [];
                // Nitter user cards are in .timeline-item or .user-card elements
                const cards = document.querySelectorAll(
                    '.timeline-item, .user-card, .search-result, [class*="user"]'
                );

                for (const card of cards) {
                    const nameEl = card.querySelector('.fullname, .display-name a, [class*="name"]');
                    const usernameEl = card.querySelector('.username, [class*="username"]');
                    const bioEl = card.querySelector('.bio, .tweet-content, [class*="bio"]');
                    const avatarEl = card.querySelector('img.avatar, img[class*="avatar"]');

                    const name = nameEl ? nameEl.innerText.trim() : '';
                    let username = usernameEl ? usernameEl.innerText.trim() : '';
                    username = username.replace('@', '');
                    const bio = bioEl ? bioEl.innerText.trim() : '';
                    const avatar = avatarEl ? avatarEl.src : '';

                    // Try to extract stats
                    const statsEls = card.querySelectorAll('.stat, [class*="stat"]');
                    let followers = 0;
                    let following = 0;
                    let tweets = 0;
                    for (const stat of statsEls) {
                        const text = (stat.innerText || '').toLowerCase();
                        const numMatch = text.match(/([\\d,.]+[kmb]?)/i);
                        if (numMatch) {
                            const num = numMatch[1];
                            if (text.includes('follower')) followers = num;
                            if (text.includes('following')) following = num;
                            if (text.includes('tweet') || text.includes('post')) tweets = num;
                        }
                    }

                    if (name || username) {
                        results.push({ name, username, bio, avatar, followers, following, tweets });
                    }
                }
                return results;
            }""")

            await page.close()

            # Parse follower counts from text
            for user in users:
                user["followers"] = self._parse_count(str(user.get("followers", "0")))
                user["following"] = self._parse_count(str(user.get("following", "0")))
                user["tweets"] = self._parse_count(str(user.get("tweets", "0")))

            return users

        except Exception as e:
            logger.warning("Nitter search failed for '%s': %s", search_query, e)
            return []

    @staticmethod
    def _parse_count(text: str) -> int:
        """Parse a count like '1.2K' or '500' into an integer."""
        if not text:
            return 0
        text = text.strip().upper().replace(",", "")
        match = re.search(r"([\d.]+)\s*([KMB])?", text)
        if not match:
            return 0
        num = float(match.group(1))
        suffix = match.group(2)
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        return int(num * multipliers.get(suffix, 1))

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

    async def close(self):
        """Shut down Nitter browser resources."""
        if self._nitter_context:
            await self._nitter_context.close()
            self._nitter_context = None
        if self._nitter_browser:
            await self._nitter_browser.close()
            self._nitter_browser = None
        if self._nitter_playwright:
            await self._nitter_playwright.stop()
            self._nitter_playwright = None

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
            "health": ["health", "wellness", "nutrition", "supplement", "pelvic", "postpartum", "menopause"],
            "lifestyle": ["lifestyle", "daily", "life", "mom", "mother"],
            "home": ["home", "decor", "interior", "diy", "garden"],
            "parenting": ["parent", "mom", "dad", "baby", "kids"],
            "education": ["education", "teach", "learn", "book"],
            "intimate apparel": ["underwear", "leakproof", "period", "incontinence", "intimate"],
        }
        found = []
        for niche, keywords in niche_keywords.items():
            if any(kw in bio_lower for kw in keywords):
                found.append(niche)
        return found if found else ["ugc"]
