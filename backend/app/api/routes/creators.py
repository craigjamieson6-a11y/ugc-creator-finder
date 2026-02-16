from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.db.database import get_db
from app.models.creator import Creator
from app.services.modash import ModashService
from app.services.phyllo import PhylloService
from app.services.twitter import TwitterService
from app.services.tiktok import TikTokService
from app.services.profile_finder import ProfileFinderService
from app.services.scoring import ScoringService
from app.services.enrichment import EnrichmentService
from app.config import get_settings

router = APIRouter(prefix="/api/creators", tags=["creators"])

modash = ModashService()
phyllo = PhylloService()
twitter = TwitterService()
tiktok = TikTokService()
profile_finder = ProfileFinderService()
scoring = ScoringService()
enrichment = EnrichmentService()


def _parse_modash_creator(raw: dict, platform: str, target_niche: Optional[str] = None) -> dict:
    profile = raw.get("profile", {})
    bio = profile.get("bio", "")
    engagement_rate = profile.get("engagementRate", 0)
    followers = profile.get("followers", 0)
    niche_tags = profile.get("interests", [])
    api_gender = profile.get("gender", "").lower() if profile.get("gender") else None
    api_age = profile.get("age")

    demographics = enrichment.enrich_creator_demographics(bio, api_gender, api_age)

    engagement_score = scoring.calculate_engagement_score(engagement_rate, platform)
    quality_score = scoring.calculate_quality_score(
        followers, engagement_rate,
        profile.get("postCount", 0),
        profile.get("avgLikes", 0),
        profile.get("avgComments", 0),
    )
    relevance_score = scoring.calculate_relevance_score(
        bio, niche_tags, target_niche,
    )
    overall_score = scoring.calculate_overall_score(engagement_score, quality_score, relevance_score)

    return {
        "external_id": raw.get("userId", ""),
        "name": profile.get("fullname", ""),
        "platform": platform,
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
    }


def _parse_phyllo_creator(raw: dict, target_niche: Optional[str] = None) -> dict:
    platform = raw.get("platform", "facebook")
    bio = raw.get("bio", "")
    engagement_rate = raw.get("engagement_rate", 0)
    followers = raw.get("followers", 0)
    niche_tags = [raw.get("category", "")]

    demographics = enrichment.enrich_creator_demographics(bio)

    engagement_score = scoring.calculate_engagement_score(engagement_rate, platform)
    quality_score = scoring.calculate_quality_score(followers, engagement_rate, raw.get("post_count", 0))
    relevance_score = scoring.calculate_relevance_score(bio, niche_tags, target_niche)
    overall_score = scoring.calculate_overall_score(engagement_score, quality_score, relevance_score)

    return {
        "external_id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "platform": platform,
        "handle": raw.get("username", ""),
        "profile_url": raw.get("profile_url", ""),
        "avatar_url": raw.get("avatar_url", ""),
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
    }


def _parse_twitter_creator(raw: dict, target_niche: Optional[str] = None) -> dict:
    """Parse a Twitter creator (same Modash-like format from TwitterService) into standardized format."""
    profile = raw.get("profile", {})
    bio = profile.get("bio", "")
    name = profile.get("fullname", "")
    engagement_rate = profile.get("engagementRate", 0)
    followers = profile.get("followers", 0)
    niche_tags = profile.get("interests", [])

    # Pass name to enrichment for name-based gender inference
    demographics = enrichment.enrich_creator_demographics(bio, name=name)

    engagement_score = scoring.calculate_engagement_score(engagement_rate, "twitter")
    quality_score = scoring.calculate_quality_score(
        followers, engagement_rate,
        profile.get("postCount", 0),
    )
    relevance_score = scoring.calculate_relevance_score(bio, niche_tags, target_niche)
    overall_score = scoring.calculate_overall_score(engagement_score, quality_score, relevance_score)

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
    """Parse a TikTok creator (same format from TikTokService) into standardized format."""
    profile = raw.get("profile", {})
    bio = profile.get("bio", "")
    name = profile.get("fullname", "")
    engagement_rate = profile.get("engagementRate", 0)
    followers = profile.get("followers", 0)
    niche_tags = profile.get("interests", [])

    # Pass name to enrichment for name-based gender inference
    demographics = enrichment.enrich_creator_demographics(bio, name=name)

    engagement_score = scoring.calculate_engagement_score(engagement_rate, "tiktok")
    quality_score = scoring.calculate_quality_score(
        followers, engagement_rate,
        profile.get("postCount", 0),
    )
    relevance_score = scoring.calculate_relevance_score(bio, niche_tags, target_niche)
    overall_score = scoring.calculate_overall_score(engagement_score, quality_score, relevance_score)

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
            pass  # Don't fail the whole search if cross-platform lookup fails
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

    # Filter by gender if specified
    if gender:
        query = query.where(Creator.gender == gender)

    # Get total count
    count_query = select(func.count()).select_from(Creator)
    if gender:
        count_query = count_query.where(Creator.gender == gender)
    total_result = await db.execute(count_query)
    db_total = total_result.scalar() or 0

    # Sort
    sort_col = getattr(Creator, sort_by, Creator.overall_score)
    query = query.order_by(sort_col.desc())

    # Paginate
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
    platform: str = Query("instagram", description="Platform to search"),
    niche: Optional[str] = Query(None, description="Niche/category filter"),
    min_followers: int = Query(1000, description="Minimum follower count"),
    max_followers: Optional[int] = Query(None, description="Maximum follower count"),
    min_engagement: float = Query(0.0, description="Minimum engagement rate"),
    gender: Optional[str] = Query("female", description="Creator gender filter"),
    age_min: int = Query(40, description="Minimum age"),
    age_max: int = Query(60, description="Maximum age"),
    sort_by: str = Query("overall_score", description="Sort field"),
    page: int = Query(0, ge=0),
    page_size: int = Query(20, ge=1, le=500),
    deep_search: bool = Query(False, description="Enable exhaustive multi-query paginated search"),
    db: AsyncSession = Depends(get_db),
):
    creators = []
    is_live_scraper = False  # Track whether we're using live API (Twitter/TikTok)

    if platform.lower() == "twitter":
        # Twitter API search
        if twitter._is_configured():
            is_live_scraper = True
            creators = await _search_twitter(niche, min_followers, page_size, deep_search)
        else:
            # Fallback to mock data via Modash when no Twitter API key
            data = await modash.search_creators(
                platform="instagram",
                min_followers=min_followers,
                max_followers=max_followers,
                min_engagement=min_engagement,
                gender=gender,
                niche=niche,
                audience_age_min=age_min,
                audience_age_max=age_max,
                page=page,
                page_size=page_size,
            )
            raw_creators = data.get("lookalikes", [])
            creators = [_parse_modash_creator(c, "twitter", niche) for c in raw_creators]

    elif platform.lower() == "tiktok":
        # TikTok web scraper — fall back to Modash if empty
        if tiktok._is_configured():
            tiktok_creators = await _search_tiktok(niche, min_followers, page_size, deep_search)
            if tiktok_creators:
                is_live_scraper = True
                creators = tiktok_creators

        if not creators:
            data = await modash.search_creators(
                platform="tiktok",
                min_followers=min_followers,
                max_followers=max_followers,
                min_engagement=min_engagement,
                gender=gender,
                niche=niche,
                audience_age_min=age_min,
                audience_age_max=age_max,
                page=page,
                page_size=page_size,
            )
            raw_creators = data.get("lookalikes", [])
            creators = [_parse_modash_creator(c, "tiktok", niche) for c in raw_creators]

    elif platform.lower() == "all":
        # Search Twitter first
        if twitter._is_configured():
            is_live_scraper = True
            twitter_creators = await _search_twitter(niche, min_followers, page_size, deep_search)
            twitter_creators = await _enrich_with_cross_platform(twitter_creators)
            creators.extend(twitter_creators)

        # Search TikTok
        if tiktok._is_configured():
            tiktok_creators = await _search_tiktok(niche, min_followers, page_size, deep_search)
            if tiktok_creators:
                is_live_scraper = True
                creators.extend(tiktok_creators)

        # Also search Modash (Instagram) for more results
        data = await modash.search_creators(
            platform="instagram",
            min_followers=min_followers,
            max_followers=max_followers,
            min_engagement=min_engagement,
            gender=gender,
            niche=niche,
            audience_age_min=age_min,
            audience_age_max=age_max,
            page=page,
            page_size=page_size,
        )
        raw_creators = data.get("lookalikes", [])
        creators.extend([_parse_modash_creator(c, "instagram", niche) for c in raw_creators])

    elif platform.lower() in ("instagram", "youtube"):
        data = await modash.search_creators(
            platform=platform.lower(),
            min_followers=min_followers,
            max_followers=max_followers,
            min_engagement=min_engagement,
            gender=gender,
            niche=niche,
            audience_age_min=age_min,
            audience_age_max=age_max,
            page=page,
            page_size=page_size,
        )
        raw_creators = data.get("lookalikes", [])
        creators = [_parse_modash_creator(c, platform.lower(), niche) for c in raw_creators]
    elif platform.lower() in ("facebook", "pinterest"):
        data = await phyllo.search_creators(
            platform=platform.lower(),
            min_followers=min_followers,
            niche=niche,
            page=page,
            page_size=page_size,
        )
        raw_creators = data.get("creators", [])
        creators = [_parse_phyllo_creator(c, niche) for c in raw_creators]

    # Filter by gender first (for live scrapers, require confirmed gender)
    if gender:
        if is_live_scraper:
            creators = [
                c for c in creators
                if (c.get("gender") or "").lower() == gender.lower()
            ]
        else:
            creators = [
                c for c in creators
                if c.get("gender") is None
                or (c.get("gender") or "").lower() == gender.lower()
            ]

    # Filter by age range
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
            # For Twitter: the demo-targeted queries already select for
            # age signals (mom, gen x, over 40, etc.), so if gender is
            # confirmed we include them — the query match IS the age signal.
            # For non-Twitter: keep them (Modash demographics are always set).
            filtered.append(c)

    # Sort
    reverse = True
    filtered.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

    # Save/update creators in DB
    for c in filtered:
        existing = await db.execute(
            select(Creator).where(Creator.external_id == c["external_id"])
        )
        existing = existing.scalar_one_or_none()
        if existing:
            for key, val in c.items():
                if key != "cross_platform_profiles":
                    setattr(existing, key, val)
        else:
            db_data = {k: v for k, v in c.items() if k != "cross_platform_profiles"}
            db.add(Creator(**db_data))
    await db.commit()

    # Get total DB count for the response
    count_result = await db.execute(select(func.count()).select_from(Creator))
    db_total = count_result.scalar() or 0

    return {"creators": filtered, "total": len(filtered), "db_total": db_total, "page": page}


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
        "last_updated": creator.last_updated,
    }
