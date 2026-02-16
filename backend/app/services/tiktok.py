import asyncio
import logging
import random
import re
from typing import Optional
from urllib.parse import quote

from playwright.async_api import async_playwright, Browser, BrowserContext

from app.config import get_settings

logger = logging.getLogger(__name__)

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

# JavaScript to extract user data from TikTok search results DOM.
# Each profile <a href="/@username"> link IS the user card — it contains
# display name, username, follower/like counts, and a Follow button.
# The link's innerText lines look like:
#   "Display Name" / "username" / "138.2K" / "Followers" / "·" / "1.5M" / "Likes" / "Follow"
# Bio text (if shown) may be in a sibling element outside the link.
_EXTRACT_USERS_JS = """() => {
    const results = [];
    const seen = new Set();
    const links = document.querySelectorAll('a[href*="/@"]');

    for (const link of links) {
        const href = link.getAttribute("href") || "";
        const match = href.match(/\\/@([^/?#]+)/);
        if (!match) continue;
        const username = match[1];
        if (seen.has(username) || username === "tiktok" || !username) continue;
        seen.add(username);

        // Extract data from the link element itself (not parent — parent
        // is a shared container holding ALL user cards).
        const text = link.innerText || "";
        const lines = text.split("\\n").map(l => l.trim()).filter(l => l.length > 0);

        let displayName = "";
        let followerText = "";

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const nextLine = (lines[i + 1] || "").toLowerCase();

            // "138.2K" followed by "Followers" on next line
            if (/^[\\d.,]+[KMB]?$/i.test(line) && nextLine === "followers") {
                followerText = line + " Followers";
                i++;
                continue;
            }
            // Combined "138.2K Followers" on one line
            if (/\\d/.test(line) && /follower/i.test(line)) {
                followerText = line;
                continue;
            }
            // Skip meta lines
            if (line === username || line === "@" + username) continue;
            if (/^follow$/i.test(line)) continue;
            if (/^[\\d.,]+[KMB]?$/i.test(line) && /likes?/i.test(nextLine)) { i++; continue; }
            if (/\\d/.test(line) && /(likes?|videos?)/i.test(line)) continue;
            if (line === "\u00b7" || line === "Followers" || line === "Likes") continue;

            if (!displayName) {
                displayName = line;
            }
        }

        // Look for bio in sibling elements (TikTok sometimes renders
        // the bio as a separate <p> or <span> outside the <a> link).
        let bio = "";
        let sibling = link.nextElementSibling;
        for (let i = 0; i < 3 && sibling; i++) {
            const sibText = (sibling.innerText || "").trim();
            if (sibText && sibText.length > 5
                && !/^follow$/i.test(sibText)
                && !/follower/i.test(sibText)) {
                bio = sibText;
                break;
            }
            sibling = sibling.nextElementSibling;
        }

        // Extract avatar from an <img> inside the link
        let avatar = "";
        const img = link.querySelector("img");
        if (img) avatar = img.src || "";

        results.push({
            username,
            displayName: displayName || username,
            bio,
            avatar,
            followerText,
        });
    }
    return results;
}"""


_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
"""


class TikTokService:
    """Search TikTok for UGC creators using Playwright headless browser."""

    def __init__(self):
        settings = get_settings()
        self.enabled = settings.tiktok_enabled
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def _is_configured(self) -> bool:
        return self.enabled

    async def _get_context(self) -> BrowserContext:
        """Return a warm browser context, creating one if needed.

        TikTok requires an established session to serve search results.
        On first call we: launch browser → create context → visit homepage →
        do a throwaway search navigation (the first search always fails).
        After that, subsequent searches in this context work reliably.
        """
        if self._context is not None:
            try:
                # Verify the context is still alive
                await self._context.cookies()
                return self._context
            except Exception:
                self._context = None

        # Launch browser if needed
        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )

        # Create a persistent context and warm it up
        self._context = await self._browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        await self._warm_context(self._context)
        return self._context

    async def _warm_context(self, context: BrowserContext) -> None:
        """Visit TikTok homepage + throwaway search to establish session tokens.

        The first search in a fresh context always returns "Something went
        wrong". After that initial failure, subsequent searches succeed.
        """
        page = await context.new_page()
        await page.add_init_script(_STEALTH_JS)
        try:
            # Step 1: Visit homepage to get session cookies
            await page.goto(
                "https://www.tiktok.com/",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2)
            # Accept cookie consent if present
            for sel in [
                'button:has-text("Accept all")',
                'button:has-text("Accept")',
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click(timeout=2000)
                        break
                except Exception:
                    continue

            # Step 2: Throwaway search to establish search tokens
            await page.goto(
                "https://www.tiktok.com/search/user?q=creator",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(3)

            cookies = await context.cookies()
            logger.info("TikTok context warmed, %d cookies established", len(cookies))
        except Exception as e:
            logger.warning("Failed to warm TikTok context: %s", e)
        finally:
            await page.close()

    async def close(self):
        """Shut down the shared browser instance."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def search_creators(
        self,
        query: Optional[str] = None,
        min_followers: int = 1000,
        niche: Optional[str] = None,
        max_results: int = 20,
        deep_search: bool = False,
    ) -> list[dict]:
        """Search TikTok for UGC creators via Playwright headless browser.

        Makes multiple searches with different UGC queries to maximize
        discovery, then deduplicates by user ID.

        When deep_search=True, paginates deeper per query (8 pages vs 2).
        """
        if not self._is_configured():
            return []

        # Probe TikTok with a single quick request first.
        # If it fails (page won't load, CAPTCHA, etc.), bail out immediately
        # so the route can fall back to Modash without a multi-minute wait.
        probe_users, _, _ = await self._run_user_search("UGC creator", cursor=0)
        if not probe_users:
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

        # Process probe results so we don't waste them
        for user_entry in probe_users:
            user_info = user_entry.get("user_info", {})
            stats = user_entry.get("stats", {})
            uid = user_info.get("uid", "")
            if uid:
                seen_ids.add(uid)
                bio = user_info.get("signature", "")
                followers = stats.get("follower_count", 0)
                username = user_info.get("unique_id", "")
                name = user_info.get("nickname", "")
                bio_lower = bio.lower()
                bio_score = sum(1 for kw in UGC_BIO_KEYWORDS if kw in bio_lower)
                if not (bio_score == 0 and followers > 500000):
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
        """Navigate to TikTok user search page and extract results from the DOM.

        Uses Playwright to render the page (executes JS, passes anti-bot checks),
        scrolls to load more results, then extracts user data from rendered HTML.

        Returns (user_list, next_cursor, has_more) matching the old API interface.
        Each user_list entry has 'user_info' and 'stats' dicts for compatibility.
        """
        try:
            context = await self._get_context()
        except Exception as e:
            logger.warning("Could not get browser context: %s", e)
            return [], None, False

        page = None
        try:
            page = await context.new_page()
            await page.add_init_script(_STEALTH_JS)

            url = f"https://www.tiktok.com/search/user?q={quote(search_query)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)

            # Wait for user profile links to appear in search results
            try:
                await page.wait_for_selector('a[href*="/@"]', timeout=10000)
            except Exception:
                logger.info("No user results found for query: %s", search_query)
                return [], None, False

            # Let the page settle after initial render
            await asyncio.sleep(2.0)

            # Scroll down to load more results.
            # More scrolls for higher cursor values (pagination simulation).
            scroll_count = min(2 + cursor * 2, 8)
            for _ in range(scroll_count):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(1.0)

            # Extract user data from rendered DOM
            raw_users = await page.evaluate(_EXTRACT_USERS_JS)

            # Convert DOM-extracted data to the user_info/stats format
            # expected by search_creators()
            user_list = []
            for u in raw_users:
                followers = self._parse_follower_count(u.get("followerText", ""))
                username = u.get("username", "")
                user_list.append({
                    "user_info": {
                        "uid": username,
                        "unique_id": username,
                        "nickname": u.get("displayName", username),
                        "signature": u.get("bio", ""),
                        "avatar_larger": u.get("avatar", ""),
                    },
                    "stats": {
                        "follower_count": followers,
                        "following_count": 0,
                        "heart_count": 0,
                        "video_count": 0,
                    },
                })

            # Signal pagination: more results likely if we found several users
            # and haven't scrolled too deep yet
            has_more = len(raw_users) >= 3 and cursor < 3
            next_cursor = (cursor + 1) if has_more else None
            return user_list, next_cursor, has_more

        except Exception as e:
            logger.warning("TikTok Playwright search failed for '%s': %s", search_query, e)
            return [], None, False
        finally:
            if page:
                await page.close()

    @staticmethod
    def _parse_follower_count(text: str) -> int:
        """Parse follower count text like '1.2M Followers' or '10.5K'."""
        if not text:
            return 0
        text = text.strip().upper()
        match = re.search(r"([\d.]+)\s*([KMB])?", text)
        if not match:
            return 0
        num = float(match.group(1))
        suffix = match.group(2)
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        return int(num * multipliers.get(suffix, 1))

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
