from __future__ import annotations
from typing import Optional


# Platform average engagement rates for normalization
PLATFORM_AVG_ENGAGEMENT = {
    "tiktok": 5.0,
    "instagram": 2.0,
    "youtube": 3.0,
    "facebook": 1.5,
    "pinterest": 2.5,
    "twitter": 1.5,
    "backstage": 2.0,
}

# Niche-specific keywords for leakproof underwear relevance
NICHE_KEYWORDS = [
    "leakproof", "leak proof", "leak-proof",
    "period", "period underwear", "period panties",
    "incontinence", "bladder",
    "pelvic floor", "pelvic health",
    "postpartum", "post-partum", "post partum",
    "menopause", "perimenopause", "menstrual",
    "feminine", "feminine hygiene", "feminine care",
    "underwear", "intimates", "intimate",
    "women's health", "womens health",
]


class ScoringService:
    def __init__(
        self,
        engagement_weight: float = 0.4,
        quality_weight: float = 0.3,
        relevance_weight: float = 0.3,
    ):
        self.engagement_weight = engagement_weight
        self.quality_weight = quality_weight
        self.relevance_weight = relevance_weight

    def calculate_engagement_score(
        self, engagement_rate: float, platform: str
    ) -> float:
        """Score 0-100 based on engagement rate relative to platform average."""
        avg = PLATFORM_AVG_ENGAGEMENT.get(platform.lower(), 2.0)
        ratio = engagement_rate / avg
        # Sigmoid-like scaling: 1x avg = 50, 2x avg = 80, 3x avg = 95
        score = min(100, 50 * ratio)
        return round(max(0, score), 1)

    def calculate_quality_score(
        self,
        follower_count: int,
        engagement_rate: float,
        post_count: int,
        avg_likes: int = 0,
        avg_comments: int = 0,
    ) -> float:
        """Score 0-100 based on content quality signals."""
        score = 0.0

        # Follower-to-engagement ratio (detect fake followers)
        if follower_count > 0:
            expected_engagement = follower_count * (engagement_rate / 100)
            actual_engagement = avg_likes + avg_comments if (avg_likes + avg_comments) > 0 else expected_engagement
            ratio = actual_engagement / (follower_count * 0.02) if follower_count > 0 else 0
            authenticity = min(40, ratio * 20)
            score += authenticity

        # Post consistency (more posts = more consistent)
        if post_count > 500:
            score += 30
        elif post_count > 200:
            score += 25
        elif post_count > 50:
            score += 15
        else:
            score += 5

        # Comment-to-like ratio (higher = more engaged community)
        if avg_likes > 0 and avg_comments > 0:
            comment_ratio = avg_comments / avg_likes
            if comment_ratio > 0.05:
                score += 30
            elif comment_ratio > 0.02:
                score += 20
            else:
                score += 10
        else:
            score += 15  # neutral if data unavailable

        return round(min(100, max(0, score)), 1)

    def calculate_relevance_score(
        self,
        bio: str = "",
        niche_tags: list[str] | None = None,
        target_niche: Optional[str] = None,
        audience_demographics: dict | None = None,
        target_age_min: int = 40,
        target_age_max: int = 60,
    ) -> float:
        """Score 0-100 based on relevance to target demographic and niche."""
        score = 0.0
        niche_tags = niche_tags or []

        # Bio keyword matching (general UGC relevance)
        bio_lower = bio.lower() if bio else ""
        relevance_keywords = [
            "ugc", "creator", "content creator", "review", "unboxing",
            "authentic", "real", "honest", "everyday", "mom", "mother",
            "women", "lifestyle", "over 40", "over 50", "midlife",
        ]
        keyword_matches = sum(1 for kw in relevance_keywords if kw in bio_lower)
        score += min(20, keyword_matches * 4)

        # Niche-specific keyword matching (leakproof underwear niche)
        niche_matches = sum(1 for kw in NICHE_KEYWORDS if kw in bio_lower)
        score += min(15, niche_matches * 5)

        # Niche tag matching
        if target_niche and niche_tags:
            target_lower = target_niche.lower()
            if any(target_lower in tag.lower() for tag in niche_tags):
                score += 35
            elif any(
                any(word in tag.lower() for word in target_lower.split())
                for tag in niche_tags
            ):
                score += 20

        # Audience demographic alignment
        if audience_demographics and "ages" in audience_demographics:
            target_weight = 0.0
            for age_bucket in audience_demographics["ages"]:
                code = age_bucket.get("code", "")
                weight = age_bucket.get("weight", 0)
                # Check if age bucket overlaps with target range
                try:
                    parts = code.replace("+", "-999").split("-")
                    bucket_min = int(parts[0])
                    bucket_max = int(parts[1]) if len(parts) > 1 else 999
                    if bucket_min <= target_age_max and bucket_max >= target_age_min:
                        target_weight += weight
                except (ValueError, IndexError):
                    continue
            score += min(30, target_weight * 60)

        return round(min(100, max(0, score)), 1)

    def calculate_overall_score(
        self,
        engagement_score: float,
        quality_score: float,
        relevance_score: float,
    ) -> float:
        overall = (
            engagement_score * self.engagement_weight
            + quality_score * self.quality_weight
            + relevance_score * self.relevance_weight
        )
        return round(overall, 1)

    @staticmethod
    def classify_tier(
        follower_count: int,
        post_count: int = 0,
        engagement_rate: float = 0.0,
    ) -> str:
        """Classify a creator as 'established' or 'emerging'.

        Established:
        - 50K+ followers, OR
        - 20K+ followers with 200+ posts, OR
        - 10K+ followers with 3%+ engagement rate

        Everyone else that passes minimum thresholds is Emerging.
        """
        if follower_count >= 50_000:
            return "established"
        if follower_count >= 20_000 and post_count >= 200:
            return "established"
        if follower_count >= 10_000 and engagement_rate >= 3.0:
            return "established"
        return "emerging"
