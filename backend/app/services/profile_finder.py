import asyncio
import httpx
from typing import Optional


# Platform URL templates: (platform_name, url_template)
PLATFORM_TEMPLATES = [
    ("instagram", "https://www.instagram.com/{handle}/"),
    ("tiktok", "https://www.tiktok.com/@{handle}"),
    ("youtube", "https://www.youtube.com/@{handle}"),
    ("linkedin", "https://www.linkedin.com/in/{handle}"),
]


class ProfileFinderService:
    """Given a creator handle from one platform, attempt to find matching
    profiles on other platforms by checking common URL patterns."""

    async def find_cross_platform_profiles(
        self,
        handle: str,
        display_name: Optional[str] = None,
        source_platform: str = "twitter",
    ) -> list[dict]:
        """Check if the handle exists on other platforms via HTTP HEAD requests.

        Returns a list of dicts: [{"platform": "instagram", "url": "...", "found": True}, ...]
        """
        results = []
        tasks = []

        for platform, template in PLATFORM_TEMPLATES:
            if platform == source_platform:
                continue
            url = template.format(handle=handle)
            tasks.append(self._check_url(platform, url))

        # Also try with underscores replaced by dots and vice versa
        alt_handle = handle.replace("_", ".")
        if alt_handle != handle:
            for platform, template in PLATFORM_TEMPLATES:
                if platform == source_platform:
                    continue
                url = template.format(handle=alt_handle)
                tasks.append(self._check_url(platform, url))

        checked = await asyncio.gather(*tasks, return_exceptions=True)
        seen_platforms = set()

        for result in checked:
            if isinstance(result, Exception):
                continue
            if result and result["found"] and result["platform"] not in seen_platforms:
                seen_platforms.add(result["platform"])
                results.append(result)

        return results

    async def _check_url(self, platform: str, url: str) -> dict:
        """Check if a URL returns a valid profile (non-404)."""
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.head(
                    url,
                    timeout=10,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; UGCFinderBot/1.0)",
                    },
                )
                # Consider 200 and 3xx as "found"
                found = resp.status_code < 400
                return {"platform": platform, "url": url, "found": found}
        except httpx.HTTPError:
            return {"platform": platform, "url": url, "found": False}
