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
    # --- Tier 3: Leakproof underwear niche ---
    "period underwear creator",
    "leak proof underwear review",
    "incontinence creator",
    "pelvic floor review",
    "postpartum mom UGC",
    "women's health creator",
    "#periodunderwear review",
    "leakproof underwear try on",
    "bladder leak underwear",
    "postpartum underwear review",
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

# JavaScript to extract creator usernames and video captions from video search results.
# TikTok's Videos tab renders cards with a link to the video and creator info.
_EXTRACT_VIDEO_CREATORS_JS = """() => {
    const results = [];
    const seen = new Set();

    // Video cards contain links to individual videos and creator info
    const cards = document.querySelectorAll('[data-e2e="search_top-item-list"] > div, [data-e2e="search-common-link"]');

    // Fallback: grab all video links on the page
    const videoLinks = cards.length > 0 ? cards : document.querySelectorAll('a[href*="/video/"]');

    for (const el of videoLinks) {
        // Find the creator username from a link like /@username
        const userLink = el.querySelector ? el.querySelector('a[href*="/@"]') : null;
        const videoLink = el.querySelector ? el.querySelector('a[href*="/video/"]') : el;
        if (!userLink && !videoLink) continue;

        let username = "";
        if (userLink) {
            const href = userLink.getAttribute("href") || "";
            const match = href.match(/\\/@([^/?#]+)/);
            if (match) username = match[1];
        }
        if (!username && videoLink) {
            const href = videoLink.getAttribute("href") || "";
            const match = href.match(/\\/@([^/?#/]+)/);
            if (match) username = match[1];
        }

        if (!username || seen.has(username)) continue;
        seen.add(username);

        // Extract video caption/description text
        let caption = "";
        const descEl = el.querySelector ? (
            el.querySelector('[data-e2e="search-card-desc"]') ||
            el.querySelector('[class*="video-card-desc"]') ||
            el.querySelector('[class*="caption"]')
        ) : null;
        if (descEl) {
            caption = (descEl.innerText || "").trim();
        }
        // Fallback: use the full text of the card minus navigation elements
        if (!caption && el.innerText) {
            const lines = el.innerText.split("\\n").map(l => l.trim()).filter(l => l.length > 10);
            caption = lines.slice(0, 3).join(" ");
        }

        results.push({ username, caption });
    }
    return results;
}"""

# JavaScript to extract profile data from a TikTok user profile page.
_EXTRACT_PROFILE_JS = """() => {
    const result = { bio: "", followers: 0, videoCount: 0, displayName: "", avatar: "" };

    // Bio
    const bioEl = document.querySelector('[data-e2e="user-bio"]');
    if (bioEl) result.bio = (bioEl.innerText || "").trim();

    // Display name
    const nameEl = document.querySelector('[data-e2e="user-title"]') ||
                   document.querySelector('[data-e2e="user-subtitle"]') ||
                   document.querySelector('h1');
    if (nameEl) result.displayName = (nameEl.innerText || "").trim();

    // Follower count
    const followerEl = document.querySelector('[data-e2e="followers-count"]');
    if (followerEl) result.followers = (followerEl.innerText || "").trim();

    // Video count
    const videoEl = document.querySelector('[data-e2e="video-count"]');
    if (videoEl) result.videoCount = (videoEl.innerText || "").trim();

    // Avatar
    const avatarEl = document.querySelector('[data-e2e="user-avatar"] img') ||
                     document.querySelector('img[class*="avatar"]');
    if (avatarEl) result.avatar = avatarEl.src || "";

    return result;
}"""


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

        When a keyword query is provided, uses video search to find creators
        who actually post about the topic, then enriches their profiles.
        Otherwise, falls back to user search for broad UGC discovery.
        """
        if not self._is_configured():
            return []

        # When keywords are provided, use video search for niche relevance
        if query:
            return await self._search_via_videos(query, niche, min_followers, max_results, deep_search)

        # No keywords — use traditional user search for broad UGC discovery
        return await self._search_via_users(niche, min_followers, max_results, deep_search)

    async def _search_via_videos(
        self,
        query: str,
        niche: Optional[str],
        min_followers: int,
        max_results: int,
        deep_search: bool,
    ) -> list[dict]:
        """Search TikTok videos tab and extract creators from results."""
        # Probe to ensure browser context is warm
        if not await self._ensure_context_warm():
            return []

        terms = [t.strip() for t in query.split(",") if t.strip()][:3]
        video_queries = []
        for term in terms:
            video_queries.append(f"{term} review")
            video_queries.append(term)
        if niche:
            video_queries.append(f"{niche} {terms[0]}")

        seen_usernames: set[str] = set()
        # Map username -> list of captions that surfaced them
        creator_captions: dict[str, list[str]] = {}

        batch_size = 2
        for i in range(0, len(video_queries), batch_size):
            if len(seen_usernames) >= max_results:
                break
            batch = video_queries[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[self._run_video_search(q) for q in batch],
                return_exceptions=True,
            )
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.warning("TikTok video search failed: %s", result)
                    continue
                for entry in result:
                    username = entry.get("username", "")
                    caption = entry.get("caption", "")
                    if username and username not in seen_usernames:
                        seen_usernames.add(username)
                        creator_captions[username] = [caption] if caption else []
                    elif username and caption:
                        creator_captions.setdefault(username, []).append(caption)

        if not seen_usernames:
            # Fallback to user search if video search yields nothing
            return await self._search_via_users(niche, min_followers, max_results, deep_search)

        # Enrich top creators with profile data (cap at 20, 3 concurrent)
        usernames_to_enrich = list(seen_usernames)[:20]
        enriched = await self.enrich_profiles_batch(usernames_to_enrich)

        # Build creator dicts from enriched profiles
        all_creators: list[dict] = []
        for username in usernames_to_enrich:
            profile_data = enriched.get(username, {})
            bio = profile_data.get("bio", "")
            followers_text = profile_data.get("followers", "0")
            followers = self._parse_follower_count(str(followers_text))
            display_name = profile_data.get("displayName", username)
            avatar = profile_data.get("avatar", "")
            video_count_text = profile_data.get("videoCount", "0")
            video_count = self._parse_follower_count(str(video_count_text))

            captions = creator_captions.get(username, [])
            matched_content = " | ".join(captions[:3])

            stats = {
                "follower_count": followers,
                "following_count": 0,
                "heart_count": 0,
                "video_count": video_count,
            }

            all_creators.append({
                "userId": f"tiktok_{username}",
                "profile": {
                    "fullname": display_name,
                    "username": username,
                    "url": f"https://www.tiktok.com/@{username}",
                    "picture": avatar,
                    "bio": bio,
                    "followers": followers,
                    "following": 0,
                    "engagementRate": self._estimate_engagement_rate(stats),
                    "postCount": video_count,
                    "interests": [niche] if niche else self._infer_niches(bio),
                    "matchedContent": matched_content,
                },
            })

        return all_creators[:max_results]

    async def _search_via_users(
        self,
        niche: Optional[str],
        min_followers: int,
        max_results: int,
        deep_search: bool,
    ) -> list[dict]:
        """Original user search logic for broad UGC discovery."""
        # Probe TikTok with a single quick request first.
        probe_users, _, _ = await self._run_user_search("UGC creator", cursor=0)
        if not probe_users:
            logger.info("TikTok probe failed, resetting browser context and retrying")
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None
            probe_users, _, _ = await self._run_user_search("UGC creator", cursor=0)
            if not probe_users:
                return []

        internal_cap = max_results if not deep_search else 500

        queries = list(UGC_SEARCH_QUERIES)
        if niche:
            queries.append(f"{niche} UGC creator")
            queries.append(f"{niche} content creator mom")

        if not deep_search:
            queries = queries[:5]

        seen_ids: set[str] = set()
        all_creators: list[dict] = []

        # Process probe results
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

        batch_size = 3 if not deep_search else 2

        async def _run_query(search_query: str) -> list[dict]:
            results = []
            max_pages = 8 if deep_search else 1
            cursor = 0

            for _page in range(max_pages):
                users, next_cursor, has_more = await self._run_user_search(
                    search_query, cursor=cursor,
                )

                for user_entry in users:
                    user_info = user_entry.get("user_info", {})
                    stats = user_entry.get("stats", {})
                    uid = user_info.get("uid", "")

                    if not uid:
                        continue

                    bio = user_info.get("signature", "")
                    followers = stats.get("follower_count", 0)
                    username = user_info.get("unique_id", "")
                    name = user_info.get("nickname", "")

                    bio_lower = bio.lower()
                    bio_score = sum(1 for kw in UGC_BIO_KEYWORDS if kw in bio_lower)

                    if bio_score == 0 and followers > 500000:
                        continue

                    avatar = ""
                    avatar_obj = user_info.get("avatar_larger", {})
                    if isinstance(avatar_obj, dict):
                        url_list = avatar_obj.get("url_list", [])
                        avatar = url_list[0] if url_list else ""
                    elif isinstance(avatar_obj, str):
                        avatar = avatar_obj

                    results.append({
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
                await asyncio.sleep(random.uniform(0.5, 1.5))

            return results

        for i in range(0, len(queries), batch_size):
            if len(all_creators) >= internal_cap:
                break

            batch = queries[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[_run_query(q) for q in batch],
                return_exceptions=True,
            )

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.warning("TikTok query failed: %s", result)
                    continue
                for creator in result:
                    uid = creator["userId"]
                    if uid not in seen_ids:
                        seen_ids.add(uid)
                        all_creators.append(creator)

        return all_creators[:internal_cap]

    async def _ensure_context_warm(self) -> bool:
        """Make sure browser context is warm, return True if ready."""
        try:
            context = await self._get_context()
            return context is not None
        except Exception as e:
            logger.warning("Failed to warm context: %s", e)
            return False

    async def _run_video_search(self, search_query: str) -> list[dict]:
        """Navigate to TikTok video search tab and extract creator usernames + captions."""
        try:
            context = await self._get_context()
        except Exception as e:
            logger.warning("Could not get browser context for video search: %s", e)
            return []

        page = None
        try:
            page = await context.new_page()
            await page.add_init_script(_STEALTH_JS)

            url = f"https://www.tiktok.com/search?q={quote(search_query)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)

            # Wait for video results to appear
            try:
                await page.wait_for_selector('a[href*="/video/"], a[href*="/@"]', timeout=10000)
            except Exception:
                logger.info("No video results found for query: %s", search_query)
                return []

            await asyncio.sleep(1.5)

            # Scroll to load more results
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)

            raw_results = await page.evaluate(_EXTRACT_VIDEO_CREATORS_JS)
            logger.info("Video search '%s': found %d creators", search_query, len(raw_results))
            return raw_results

        except Exception as e:
            logger.warning("TikTok video search failed for '%s': %s", search_query, e)
            return []
        finally:
            if page:
                await page.close()

    async def enrich_profile(self, username: str) -> dict:
        """Visit a TikTok profile page and scrape bio, follower count, etc."""
        try:
            context = await self._get_context()
        except Exception as e:
            logger.warning("Could not get browser context for profile enrichment: %s", e)
            return {}

        page = None
        try:
            page = await context.new_page()
            await page.add_init_script(_STEALTH_JS)

            url = f"https://www.tiktok.com/@{quote(username)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            try:
                await page.wait_for_selector('[data-e2e="user-bio"], h1, [data-e2e="user-title"]', timeout=8000)
            except Exception:
                pass

            await asyncio.sleep(1.0)

            profile_data = await page.evaluate(_EXTRACT_PROFILE_JS)
            return profile_data

        except Exception as e:
            logger.warning("Profile enrichment failed for @%s: %s", username, e)
            return {}
        finally:
            if page:
                await page.close()

    async def enrich_profiles_batch(self, usernames: list[str], max_concurrent: int = 3) -> dict[str, dict]:
        """Enrich multiple profiles with controlled concurrency.

        Returns a dict mapping username -> profile data.
        Caps at 20 profiles, ~15s total budget.
        """
        usernames = usernames[:20]
        results: dict[str, dict] = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _enrich_one(uname: str):
            async with semaphore:
                data = await self.enrich_profile(uname)
                results[uname] = data

        await asyncio.wait_for(
            asyncio.gather(*[_enrich_one(u) for u in usernames], return_exceptions=True),
            timeout=15.0,
        )
        return results

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
            await asyncio.sleep(1.0)

            # Scroll down to load more results
            scroll_count = min(2 + cursor, 4)
            for _ in range(scroll_count):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)

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
