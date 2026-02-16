import asyncio
import logging
import random
import re
from typing import Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Browser, BrowserContext

from app.config import get_settings

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Keywords that signal a content creator on Backstage
CONTENT_CREATOR_KEYWORDS = [
    "content creator", "ugc", "influencer", "social media",
    "brand", "review", "creator", "youtube", "tiktok", "instagram",
]


class BackstageService:
    """Scrape Backstage.com talent database for content creators using Playwright."""

    def __init__(self):
        settings = get_settings()
        self.enabled = settings.backstage_enabled
        self.email = settings.backstage_email
        self.password = settings.backstage_password
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._logged_in = False

    def _is_configured(self) -> bool:
        return self.enabled and bool(self.email) and bool(self.password)

    async def _get_context(self) -> BrowserContext:
        """Return a browser context, creating one and logging in if needed."""
        if self._context is not None:
            try:
                await self._context.cookies()
                return self._context
            except Exception:
                self._context = None
                self._logged_in = False

        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )

        self._context = await self._browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        return self._context

    async def _ensure_logged_in(self, context: BrowserContext) -> bool:
        """Log in to Backstage.com if not already logged in."""
        if self._logged_in:
            return True

        page = await context.new_page()
        try:
            await page.goto("https://www.backstage.com/login/", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # Fill login form
            email_input = page.locator('input[type="email"], input[name="email"]').first
            if await email_input.is_visible(timeout=5000):
                await email_input.fill(self.email)

            password_input = page.locator('input[type="password"], input[name="password"]').first
            if await password_input.is_visible(timeout=3000):
                await password_input.fill(self.password)

            # Submit
            submit_btn = page.locator('button[type="submit"]').first
            await submit_btn.click(timeout=5000)
            await asyncio.sleep(3)

            # Verify login succeeded by checking for profile/dashboard elements
            if "/login" not in page.url:
                self._logged_in = True
                logger.info("Successfully logged in to Backstage.com")
                return True

            logger.warning("Backstage login may have failed - still on login page")
            return False
        except Exception as e:
            logger.warning("Backstage login failed: %s", e)
            return False
        finally:
            await page.close()

    async def close(self):
        """Shut down the browser instance."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._logged_in = False

    async def search_creators(
        self,
        gender: Optional[str] = "female",
        age_min: int = 40,
        age_max: int = 60,
        location: Optional[str] = None,
        country: Optional[str] = None,
        niche: Optional[str] = None,
        min_followers: int = 0,
        max_results: int = 50,
        deep_search: bool = False,
    ) -> list[dict]:
        """Search Backstage.com talent database for content creators.

        Backstage provides real self-reported age, gender, and location data.
        """
        if not self._is_configured():
            return []

        try:
            context = await self._get_context()
        except Exception as e:
            logger.warning("Could not get Backstage browser context: %s", e)
            return []

        if not await self._ensure_logged_in(context):
            return []

        internal_cap = max_results if not deep_search else 200
        all_creators: list[dict] = []
        seen_urls: set[str] = set()
        max_pages = 10 if deep_search else 3

        for page_num in range(1, max_pages + 1):
            if len(all_creators) >= internal_cap:
                break

            profiles = await self._scrape_talent_page(context, page_num, gender, age_min, age_max, location, country)

            if not profiles:
                break

            for profile in profiles:
                url = profile.get("profile_url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                creator = self._format_creator(profile, niche)
                all_creators.append(creator)

            await asyncio.sleep(random.uniform(1.5, 3.0))

        return all_creators[:internal_cap]

    async def _scrape_talent_page(
        self,
        context: BrowserContext,
        page_num: int,
        gender: Optional[str],
        age_min: int,
        age_max: int,
        location: Optional[str],
        country: Optional[str],
    ) -> list[dict]:
        """Scrape a single page of Backstage talent search results."""
        page = await context.new_page()
        try:
            # Build search URL with filters
            params = {"page": str(page_num)}
            if gender:
                params["gender"] = gender.lower()
            if age_min:
                params["age_min"] = str(age_min)
            if age_max:
                params["age_max"] = str(age_max)
            if location:
                params["location"] = location
            if country:
                params["location"] = country

            url = f"https://www.backstage.com/talent/?{urlencode(params)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)

            # Extract talent cards from the page
            profiles = await page.evaluate("""() => {
                const results = [];
                // Look for talent cards/list items
                const cards = document.querySelectorAll(
                    '[data-testid="talent-card"], .talent-card, .talent-list-item, ' +
                    'article, .search-result, [class*="TalentCard"], [class*="talent-card"]'
                );

                for (const card of cards) {
                    // Extract profile link
                    const link = card.querySelector('a[href*="/talent/"]') || card.querySelector('a[href*="/profile/"]');
                    if (!link) continue;

                    const profileUrl = link.href || '';
                    const name = (card.querySelector('h2, h3, [class*="name"], [class*="Name"]') || {}).innerText || '';

                    // Extract details text (age, location, etc.)
                    const detailEls = card.querySelectorAll('span, p, [class*="detail"], [class*="Detail"], [class*="info"]');
                    let details = '';
                    for (const el of detailEls) {
                        details += ' ' + (el.innerText || '');
                    }

                    // Extract bio/headline
                    const bioEl = card.querySelector('[class*="bio"], [class*="Bio"], [class*="headline"], [class*="Headline"], [class*="tagline"]');
                    const bio = bioEl ? bioEl.innerText : '';

                    // Extract avatar
                    const img = card.querySelector('img');
                    const avatar = img ? (img.src || '') : '';

                    if (name) {
                        results.push({
                            name: name.trim(),
                            profileUrl,
                            bio: bio.trim(),
                            details: details.trim(),
                            avatar,
                        });
                    }
                }
                return results;
            }""")

            return profiles

        except Exception as e:
            logger.warning("Failed to scrape Backstage page %d: %s", page_num, e)
            return []
        finally:
            await page.close()

    def _format_creator(self, profile: dict, niche: Optional[str] = None) -> dict:
        """Convert scraped Backstage profile into the standardized creator format."""
        name = profile.get("name", "")
        bio = profile.get("bio", "")
        details = profile.get("details", "")
        profile_url = profile.get("profileUrl", "")
        avatar = profile.get("avatar", "")

        # Extract a handle from the profile URL
        handle = ""
        if profile_url:
            parts = profile_url.rstrip("/").split("/")
            handle = parts[-1] if parts else ""

        # Parse age from details text
        age_range = self._parse_age(details)

        # Parse location/country from details
        location = self._parse_location(details)
        country = self._infer_country(location) if location else None

        # Extract social links from bio/details for follower estimation
        combined_text = f"{bio} {details}".lower()
        has_social = any(kw in combined_text for kw in CONTENT_CREATOR_KEYWORDS)

        # Backstage talent typically doesn't have follower counts,
        # so we estimate conservatively
        estimated_followers = 5000 if has_social else 1000

        external_id = f"backstage_{handle}" if handle else f"backstage_{name.lower().replace(' ', '_')}"

        return {
            "userId": external_id,
            "profile": {
                "fullname": name,
                "username": handle,
                "url": profile_url,
                "picture": avatar,
                "bio": bio,
                "followers": estimated_followers,
                "following": 0,
                "engagementRate": 2.0,  # Default estimate for Backstage
                "postCount": 0,
                "interests": [niche] if niche else self._infer_niches(bio),
            },
            "backstage_data": {
                "age_range": age_range,
                "location": location,
                "country": country,
                "gender": "female",  # Backstage search already filters by gender
            },
        }

    @staticmethod
    def _parse_age(details: str) -> Optional[str]:
        """Extract age range from Backstage detail text."""
        if not details:
            return None

        # Look for explicit age mentions like "Age: 45" or "45 years old"
        age_match = re.search(r"(?:age[:\s]+)(\d{2})", details, re.IGNORECASE)
        if age_match:
            age = int(age_match.group(1))
            if 18 <= age <= 99:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}"

        # Look for age range like "40-50" or "40s"
        range_match = re.search(r"(\d{2})\s*-\s*(\d{2})", details)
        if range_match:
            return f"{range_match.group(1)}-{range_match.group(2)}"

        decade_match = re.search(r"(\d{2})s", details)
        if decade_match:
            decade = int(decade_match.group(1))
            return f"{decade}-{decade + 9}"

        return None

    @staticmethod
    def _parse_location(details: str) -> Optional[str]:
        """Extract location from Backstage detail text."""
        if not details:
            return None

        # Common patterns: "New York, NY" or "Los Angeles, CA" or "London, UK"
        loc_match = re.search(
            r"([\w\s]+,\s*(?:[A-Z]{2,3}|[\w\s]+))",
            details,
        )
        if loc_match:
            return loc_match.group(1).strip()

        return None

    @staticmethod
    def _infer_country(location: str) -> Optional[str]:
        """Infer country code from location text."""
        if not location:
            return None

        location_upper = location.upper()

        # US state abbreviations
        us_states = {
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "DC",
        }
        parts = [p.strip() for p in location_upper.split(",")]
        if any(p in us_states for p in parts):
            return "US"
        if "USA" in location_upper or "UNITED STATES" in location_upper:
            return "US"

        country_map = {
            "UK": "UK", "UNITED KINGDOM": "UK", "ENGLAND": "UK", "LONDON": "UK",
            "SCOTLAND": "UK", "WALES": "UK",
            "CANADA": "CA", "TORONTO": "CA", "VANCOUVER": "CA", "MONTREAL": "CA",
            "AUSTRALIA": "AU", "SYDNEY": "AU", "MELBOURNE": "AU",
            "GERMANY": "DE", "BERLIN": "DE", "MUNICH": "DE",
            "FRANCE": "FR", "PARIS": "FR",
        }
        for key, code in country_map.items():
            if key in location_upper:
                return code

        return None

    @staticmethod
    def _infer_niches(bio: str) -> list[str]:
        """Infer niche tags from bio text."""
        bio_lower = bio.lower()
        niche_keywords = {
            "beauty": ["beauty", "skincare", "makeup", "cosmetic"],
            "fitness": ["fitness", "workout", "gym", "training"],
            "food": ["food", "recipe", "cook", "chef"],
            "fashion": ["fashion", "style", "outfit", "clothing"],
            "health": ["health", "wellness", "nutrition"],
            "lifestyle": ["lifestyle", "daily", "life", "mom"],
            "parenting": ["parent", "mom", "baby", "kids"],
        }
        found = []
        for niche_name, keywords in niche_keywords.items():
            if any(kw in bio_lower for kw in keywords):
                found.append(niche_name)
        return found if found else ["content creator"]
