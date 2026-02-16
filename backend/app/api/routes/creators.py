import asyncio

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import Optional

from app.db.database import get_db
from app.models.creator import Creator, SeenCreator
from app.services.twitter import TwitterService
from app.services.tiktok import TikTokService
from app.services.backstage import BackstageService
from app.services.profile_finder import ProfileFinderService
from app.services.scoring import ScoringService
from app.services.enrichment import EnrichmentService
from app.config import get_settings

router = APIRouter(prefix="/api/creators", tags=["creators"])

twitter = TwitterService()
tiktok = TikTokService()
backstage = BackstageService()
profile_finder = ProfileFinderService()
scoring = ScoringService()
enrichment = EnrichmentService()

# Country inference from bio/location text
COUNTRY_KEYWORDS = {
    "US": [
        "usa", "united states", "america", "nyc", "new york", "los angeles",
        "chicago", "houston", "phoenix", "philadelphia", "san antonio",
        "san diego", "dallas", "san jose", "austin", "jacksonville",
        "california", "texas", "florida", "georgia", "ohio", "michigan",
        "pennsylvania", "illinois", "north carolina", "arizona",
    ],
    "UK": [
        "uk", "united kingdom", "england", "london", "manchester",
        "birmingham", "glasgow", "scotland", "wales", "liverpool", "bristol",
    ],
    "CA": [
        "canada", "toronto", "vancouver", "montreal", "calgary", "ottawa",
        "ontario", "quebec", "british columbia", "alberta",
    ],
    "AU": [
        "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
        "queensland", "victoria", "new south wales",
    ],
    "DE": ["germany", "deutschland", "berlin", "munich", "hamburg", "frankfurt"],
    "FR": ["france", "paris", "lyon", "marseille"],
    "NZ": ["new zealand", "auckland", "wellington"],
    "IE": ["ireland", "dublin", "cork"],
}


def _infer_country(bio: str, location: str = "") -> Optional[str]:
    """Infer country code from bio and location text."""
    text = f"{bio} {location}".lower()
    for code, keywords in COUNTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return code
    return None


def _parse_twitter_creator(raw: dict, target_niche: Optional[str] = None) -> dict:
    """Parse a Twitter creator into standardized format."""
    profile = raw.get("profile", {})
    bio = profile.get("bio", "")
    name = profile.get("fullname", "")
    engagement_rate = profile.get("engagementRate", 0)
    followers = profile.get("followers", 0)
    niche_tags = profile.get("interests", [])
    post_count = profile.get("postCount", 0)

    demographics = enrichment.enrich_creator_demographics(bio, name=name)
    country = _infer_country(bio)

    engagement_score = scoring.calculate_engagement_score(engagement_rate, "twitter")
    quality_score = scoring.calculate_quality_score(followers, engagement_rate, post_count)
    relevance_score = scoring.calculate_relevance_score(bio, niche_tags, target_niche)
    overall_score = scoring.calculate_overall_score(engagement_score, quality_score, relevance_score)
    tier = scoring.classify_tier(followers, post_count, engagement_rate)

    return {
        "external_id": raw.get("userId", ""),
        "name": name,
        "platform": "twitter",
        "handle": profile.get("username", ""),
        "profile_url": profile.get("url", ""),
        "avatar_url": profile.get("picture", ""),
        "follower_count": followers,
        "engagement_rate": engagement_rate,
        "bio": bio,
        "niche_tags": niche_tags,
        "estimated_age_range": demographics.get("age_range"),
        "gender": demographics.get("gender"),
        "demographic_confidence": demographics.get("age_confidence", "low"),
        "engagement_score": engagement_score,
        "quality_score": quality_score,
        "relevance_score": relevance_score,
        "overall_score": overall_score,
        "tier": tier,
        "country": country,
        "post_count": post_count,
    }


async def _search_twitter(
    niche: Optional[str],
    min_followers: int,
    page_size: int,
    deep_search: bool = False,
) -> list[dict]:
    """Search Twitter and parse results into standardized creator dicts."""
    raw_creators = await twitter.search_creators(
        niche=niche,
        min_followers=min_followers,
        max_results=page_size,
        deep_search=deep_search,
    )
    return [_parse_twitter_creator(c, niche) for c in raw_creators]


def _parse_tiktok_creator(raw: dict, target_niche: Optional[str] = None) -> dict:
    """Parse a TikTok creator into standardized format."""
    profile = raw.get("profile", {})
    bio = profile.get("bio", "")
    name = profile.get("fullname", "")
    engagement_rate = profile.get("engagementRate", 0)
    followers = profile.get("followers", 0)
    niche_tags = profile.get("interests", [])
    post_count = profile.get("postCount", 0)

    demographics = enrichment.enrich_creator_demographics(bio, name=name)
    country = _infer_country(bio)

    engagement_score = scoring.calculate_engagement_score(engagement_rate, "tiktok")
    quality_score = scoring.calculate_quality_score(followers, engagement_rate, post_count)
    relevance_score = scoring.calculate_relevance_score(bio, niche_tags, target_niche)
    overall_score = scoring.calculate_overall_score(engagement_score, quality_score, relevance_score)
    tier = scoring.classify_tier(followers, post_count, engagement_rate)

    return {
        "external_id": raw.get("userId", ""),
        "name": name,
        "platform": "tiktok",
        "handle": profile.get("username", ""),
        "profile_url": profile.get("url", ""),
        "avatar_url": profile.get("picture", ""),
        "follower_count": followers,
        "engagement_rate": engagement_rate,
        "bio": bio,
        "niche_tags": niche_tags,
        "estimated_age_range": demographics.get("age_range"),
        "gender": demographics.get("gender"),
        "demographic_confidence": demographics.get("age_confidence", "low"),
        "engagement_score": engagement_score,
        "quality_score": quality_score,
        "relevance_score": relevance_score,
        "overall_score": overall_score,
        "tier": tier,
        "country": country,
        "post_count": post_count,
    }


async def _search_tiktok(
    niche: Optional[str],
    min_followers: int,
    page_size: int,
    deep_search: bool = False,
) -> list[dict]:
    """Search TikTok and parse results into standardized creator dicts."""
    raw_creators = await tiktok.search_creators(
        niche=niche,
        min_followers=min_followers,
        max_results=page_size,
        deep_search=deep_search,
    )
    return [_parse_tiktok_creator(c, niche) for c in raw_creators]


def _parse_backstage_creator(raw: dict, target_niche: Optional[str] = None) -> dict:
    """Parse a Backstage creator into standardized format."""
    profile = raw.get("profile", {})
    backstage_data = raw.get("backstage_data", {})
    bio = profile.get("bio", "")
    name = profile.get("fullname", "")
    engagement_rate = profile.get("engagementRate", 0)
    followers = profile.get("followers", 0)
    niche_tags = profile.get("interests", [])
    post_count = profile.get("postCount", 0)

    # Backstage provides real demographics
    age_range = backstage_data.get("age_range")
    gender = backstage_data.get("gender", "female")
    country = backstage_data.get("country")
    location = backstage_data.get("location", "")

    if not country:
        country = _infer_country(bio, location)

    engagement_score = scoring.calculate_engagement_score(engagement_rate, "backstage")
    quality_score = scoring.calculate_quality_score(followers, engagement_rate, post_count)
    relevance_score = scoring.calculate_relevance_score(bio, niche_tags, target_niche)
    overall_score = scoring.calculate_overall_score(engagement_score, quality_score, relevance_score)
    tier = scoring.classify_tier(followers, post_count, engagement_rate)

    return {
        "external_id": raw.get("userId", ""),
        "name": name,
        "platform": "backstage",
        "handle": profile.get("username", ""),
        "profile_url": profile.get("url", ""),
        "avatar_url": profile.get("picture", ""),
        "follower_count": followers,
        "engagement_rate": engagement_rate,
        "bio": bio,
        "niche_tags": niche_tags,
        "estimated_age_range": age_range,
        "gender": gender,
        "demographic_confidence": "high" if age_range else "medium",
        "engagement_score": engagement_score,
        "quality_score": quality_score,
        "relevance_score": relevance_score,
        "overall_score": overall_score,
        "tier": tier,
        "country": country,
        "post_count": post_count,
    }


async def _search_backstage(
    niche: Optional[str],
    gender: Optional[str],
    age_min: int,
    age_max: int,
    country: Optional[str],
    max_results: int,
    deep_search: bool = False,
) -> list[dict]:
    """Search Backstage and parse results into standardized creator dicts."""
    raw_creators = await backstage.search_creators(
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        country=country,
        niche=niche,
        max_results=max_results,
        deep_search=deep_search,
    )
    return [_parse_backstage_creator(c, niche) for c in raw_creators]


async def _enrich_with_cross_platform(creators: list[dict]) -> list[dict]:
    """Attempt to find cross-platform profiles for each creator."""
    for creator in creators:
        handle = creator.get("handle", "")
        if not handle:
            continue
        try:
            profiles = await profile_finder.find_cross_platform_profiles(
                handle=handle,
                display_name=creator.get("name"),
                source_platform=creator.get("platform", "twitter"),
            )
            if profiles:
                creator["cross_platform_profiles"] = [
                    {"platform": p["platform"], "url": p["url"]}
                    for p in profiles
                ]
        except Exception:
            pass
    return creators


def _creator_to_dict(creator: Creator) -> dict:
    """Convert a Creator ORM object to a dict for API response."""
    return {
        "id": creator.id,
        "external_id": creator.external_id,
        "name": creator.name,
        "platform": creator.platform,
        "handle": creator.handle,
        "profile_url": creator.profile_url,
        "avatar_url": creator.avatar_url,
        "follower_count": creator.follower_count,
        "engagement_rate": creator.engagement_rate,
        "bio": creator.bio,
        "niche_tags": creator.niche_tags,
        "estimated_age_range": creator.estimated_age_range,
        "gender": creator.gender,
        "demographic_confidence": creator.demographic_confidence,
        "overall_score": creator.overall_score,
        "engagement_score": creator.engagement_score,
        "quality_score": creator.quality_score,
        "relevance_score": creator.relevance_score,
        "tier": creator.tier,
        "country": creator.country,
        "last_updated": creator.last_updated,
    }


@router.get("/database")
async def get_database(
    gender: Optional[str] = Query(None, description="Filter by gender"),
    age_min: int = Query(0, description="Minimum age"),
    age_max: int = Query(999, description="Maximum age"),
    sort_by: str = Query("overall_score", description="Sort field"),
    page: int = Query(0, ge=0),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Return ALL creators stored in the database across all past searches."""
    query = select(Creator)

    if gender:
        query = query.where(Creator.gender == gender)

    count_query = select(func.count()).select_from(Creator)
    if gender:
        count_query = count_query.where(Creator.gender == gender)
    total_result = await db.execute(count_query)
    db_total = total_result.scalar() or 0

    sort_col = getattr(Creator, sort_by, Creator.overall_score)
    query = query.order_by(sort_col.desc())
    query = query.offset(page * page_size).limit(page_size)

    result = await db.execute(query)
    creators = result.scalars().all()

    return {
        "creators": [_creator_to_dict(c) for c in creators],
        "total": len(creators),
        "db_total": db_total,
        "page": page,
    }


@router.get("/search")
async def search_creators(
    platform: str = Query("tiktok", description="Platform to search"),
    niche: Optional[str] = Query(None, description="Niche/category filter"),
    min_followers: int = Query(1000, description="Minimum follower count"),
    max_followers: Optional[int] = Query(None, description="Maximum follower count"),
    min_engagement: float = Query(0.0, description="Minimum engagement rate"),
    gender: Optional[str] = Query("female", description="Creator gender filter"),
    age_min: int = Query(40, description="Minimum age"),
    age_max: int = Query(60, description="Maximum age"),
    country: Optional[str] = Query(None, description="Country filter (US, UK, CA, AU, DE, etc.)"),
    strict_demo: bool = Query(False, description="Only include creators with confirmed age/gender"),
    sort_by: str = Query("overall_score", description="Sort field"),
    page: int = Query(0, ge=0),
    page_size: int = Query(20, ge=1, le=500),
    exclude_seen: bool = Query(False, description="Exclude previously seen creators (de-duplication)"),
    deep_search: bool = Query(False, description="Enable exhaustive multi-query paginated search"),
    db: AsyncSession = Depends(get_db),
):
    creators = []

    if platform.lower() == "twitter":
        creators = await _search_twitter(niche, min_followers, page_size, deep_search)
        creators = await _enrich_with_cross_platform(creators)

    elif platform.lower() == "tiktok":
        if tiktok._is_configured():
            creators = await _search_tiktok(niche, min_followers, page_size, deep_search)

    elif platform.lower() == "backstage":
        if backstage._is_configured():
            creators = await _search_backstage(
                niche, gender, age_min, age_max, country, page_size, deep_search,
            )

    elif platform.lower() == "all":
        # Search all platforms in parallel
        tasks = [_search_twitter(niche, min_followers, page_size, deep_search)]

        if tiktok._is_configured():
            tasks.append(_search_tiktok(niche, min_followers, page_size, deep_search))

        if backstage._is_configured():
            tasks.append(_search_backstage(
                niche, gender, age_min, age_max, country, page_size, deep_search,
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                import logging
                logging.getLogger(__name__).warning("Platform search failed: %s", result)
                continue
            creators.extend(result)

    # --- De-duplication: only when exclude_seen is enabled ---
    if exclude_seen:
        seen_result = await db.execute(select(SeenCreator.external_id))
        seen_ids = {row[0] for row in seen_result.fetchall()}
        creators = [c for c in creators if c.get("external_id") not in seen_ids]

        # Mark new creators as seen
        for c in creators:
            ext_id = c.get("external_id")
            if ext_id and ext_id not in seen_ids:
                db.add(SeenCreator(
                    external_id=ext_id,
                    platform=c.get("platform", ""),
                ))
                seen_ids.add(ext_id)

    # --- Filter by gender ---
    if gender:
        if strict_demo:
            # Strict: only include confirmed matching gender
            creators = [
                c for c in creators
                if (c.get("gender") or "").lower() == gender.lower()
            ]
        else:
            # Lenient: include unknown gender (don't discard undetected)
            creators = [
                c for c in creators
                if c.get("gender") is None
                or (c.get("gender") or "").lower() == gender.lower()
            ]

    # --- Filter by age range ---
    filtered = []
    for c in creators:
        age_range = c.get("estimated_age_range")
        if age_range:
            try:
                parts = age_range.replace("+", "-999").split("-")
                lo = int(parts[0])
                hi = int(parts[1]) if len(parts) > 1 else lo + 9
                if lo <= age_max and hi >= age_min:
                    filtered.append(c)
            except (ValueError, IndexError):
                filtered.append(c)
        else:
            # No age data: include only in lenient mode
            if not strict_demo:
                filtered.append(c)

    # --- Filter by country ---
    if country:
        country_upper = country.upper()
        filtered = [
            c for c in filtered
            if c.get("country") is None
            or (c.get("country") or "").upper() == country_upper
        ]

    # --- Sort ---
    filtered.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

    # --- Save/update creators in DB ---
    skip_keys = {"cross_platform_profiles", "post_count"}
    for c in filtered:
        existing = await db.execute(
            select(Creator).where(Creator.external_id == c["external_id"])
        )
        existing = existing.scalar_one_or_none()
        if existing:
            for key, val in c.items():
                if key not in skip_keys:
                    setattr(existing, key, val)
        else:
            db_data = {k: v for k, v in c.items() if k not in skip_keys}
            db.add(Creator(**db_data))
    await db.commit()

    # Get total DB count
    count_result = await db.execute(select(func.count()).select_from(Creator))
    db_total = count_result.scalar() or 0

    return {"creators": filtered, "total": len(filtered), "db_total": db_total, "page": page}


@router.post("/reset-seen")
async def reset_seen_creators(db: AsyncSession = Depends(get_db)):
    """Clear all seen creator history so they appear in future searches again."""
    await db.execute(delete(SeenCreator))
    await db.commit()
    return {"status": "ok", "message": "Seen creators history cleared"}


@router.get("/{creator_id}")
async def get_creator(creator_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Creator).where(Creator.id == creator_id))
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    return {
        "id": creator.id,
        "external_id": creator.external_id,
        "name": creator.name,
        "platform": creator.platform,
        "handle": creator.handle,
        "profile_url": creator.profile_url,
        "avatar_url": creator.avatar_url,
        "follower_count": creator.follower_count,
        "following_count": creator.following_count,
        "engagement_rate": creator.engagement_rate,
        "avg_likes": creator.avg_likes,
        "avg_comments": creator.avg_comments,
        "avg_views": creator.avg_views,
        "post_count": creator.post_count,
        "bio": creator.bio,
        "niche_tags": creator.niche_tags,
        "estimated_age_range": creator.estimated_age_range,
        "gender": creator.gender,
        "demographic_confidence": creator.demographic_confidence,
        "audience_demographics": creator.audience_demographics,
        "overall_score": creator.overall_score,
        "engagement_score": creator.engagement_score,
        "quality_score": creator.quality_score,
        "relevance_score": creator.relevance_score,
        "tier": creator.tier,
        "country": creator.country,
        "last_updated": creator.last_updated,
    }
