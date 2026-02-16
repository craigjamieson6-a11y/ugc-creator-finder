import httpx
from typing import Optional

from app.config import get_settings


class ModashService:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.modash_api_key
        self.base_url = settings.modash_base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    async def search_creators(
        self,
        platform: str = "instagram",
        min_followers: int = 1000,
        max_followers: Optional[int] = None,
        min_engagement: float = 0.0,
        gender: Optional[str] = None,
        niche: Optional[str] = None,
        audience_age_min: Optional[int] = None,
        audience_age_max: Optional[int] = None,
        page: int = 0,
        page_size: int = 20,
    ) -> dict:
        if not self._is_configured():
            return self._mock_search(platform, niche, page_size)

        filters = {
            "influencer": {
                "followers": {"min": min_followers},
                "engagementRate": {"min": min_engagement},
            },
            "sort": {"field": "followers", "direction": "desc"},
            "page": page,
            "limit": page_size,
        }

        if max_followers:
            filters["influencer"]["followers"]["max"] = max_followers
        if gender:
            filters["influencer"]["gender"] = gender.upper()
        if niche:
            filters["influencer"]["interests"] = [niche]
        if audience_age_min or audience_age_max:
            age_filter = {}
            if audience_age_min:
                age_filter["min"] = audience_age_min
            if audience_age_max:
                age_filter["max"] = audience_age_max
            filters["influencer"]["age"] = age_filter

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/{platform}/search",
                headers=self.headers,
                json=filters,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_creator_profile(self, platform: str, user_id: str) -> dict:
        if not self._is_configured():
            return self._mock_profile(platform, user_id)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/{platform}/profile/{user_id}/report",
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    def _mock_search(self, platform: str, niche: Optional[str], limit: int) -> dict:
        """Return mock data for development without API keys."""
        mock_creators = [
            {
                "userId": f"mock_{platform}_{i}",
                "profile": {
                    "fullname": name,
                    "username": handle,
                    "url": f"https://{platform}.com/{handle}",
                    "picture": f"https://i.pravatar.cc/150?u={handle}",
                    "bio": bio,
                    "followers": followers,
                    "engagementRate": eng_rate,
                    "gender": "FEMALE",
                    "age": age_range,
                    "interests": interests,
                },
            }
            for i, (name, handle, bio, followers, eng_rate, age_range, interests) in enumerate([
                ("Sarah Mitchell", "sarahmitchell_life", "UGC creator | Mom of 3 | Wellness advocate | Born 1978 | Honest product reviews", 45000, 4.2, "45-54", ["wellness", "lifestyle"]),
                ("Jennifer Adams", "jenadams_beauty", "UGC content creator for beauty brands | Skincare for women over 40 | DM for collabs", 82000, 5.1, "40-49", ["beauty"]),
                ("Lisa Thompson", "lisathompson_home", "UGC creator | Home decor | DIY enthusiast | Empty nester | Honest unboxing videos", 31000, 3.8, "50-59", ["home"]),
                ("Karen Rodriguez", "karenrod_fitness", "Content creator for fitness brands | Certified trainer | Menopause wellness coach", 67000, 6.3, "40-49", ["fitness"]),
                ("Michelle Park", "michellepark_food", "UGC food creator | Korean-American recipes | Brand partner | Honest kitchen reviews", 120000, 4.7, "45-54", ["food"]),
                ("Diana Walsh", "dianawalsh_style", "Fashion UGC creator | Style for the fabulous 50s | Brand ambassador", 28000, 3.2, "50-59", ["fashion"]),
                ("Patricia Chen", "patriciachen_travel", "Travel content creator | 55 countries | UGC for travel brands | Age 48", 95000, 5.5, "45-54", ["travel"]),
                ("Angela Foster", "angelafoster_garden", "UGC creator | Master gardener | Cottage core | Product reviewer | Grandma of 4", 18000, 7.1, "55-60", ["home", "crafts"]),
                ("Carol Martinez", "carolm_yoga", "Yoga content creator | Mindfulness coach | UGC for wellness brands | In my 40s", 54000, 4.9, "40-49", ["wellness", "fitness"]),
                ("Nancy Kim", "nancykim_crafts", "Craft UGC creator | Quilting queen | Honest product reviews since 1998", 37000, 3.5, "50-59", ["crafts"]),
                ("Rebecca Stone", "rebeccastone_wine", "UGC creator for food & drink brands | Sommelier | Honest reviews at 46", 72000, 5.8, "45-54", ["food"]),
                ("Laura Bennett", "laurab_reads", "Book UGC creator | 200+ honest reviews/year | Content creator for publishers", 41000, 4.4, "40-49", ["education", "lifestyle"]),
                ("Donna Reeves", "donnareeves_ugc", "Full-time UGC creator | Product photography | Honest unboxing | Mom | Born 1980", 52000, 5.0, "40-49", ["lifestyle"]),
                ("Tammy Nguyen", "tammyn_skincare", "UGC creator for skincare brands | Esthetician | Anti-aging advocate | Age 51", 39000, 6.8, "50-59", ["beauty", "wellness"]),
                ("Sandra Lopez", "sandralopez_fit", "Fitness UGC creator | Personal trainer | Content for supplement brands | Over 40", 74000, 5.3, "40-49", ["fitness"]),
                ("Brenda White", "brendawhite_cook", "UGC food creator | Southern recipes | Brand partner for kitchen gadgets | 53", 61000, 4.1, "50-59", ["food"]),
                ("Julie Harper", "julieharper_mom", "UGC creator | Parenting content | Product reviews for busy moms | Gen X mama", 48000, 5.7, "40-49", ["parenting", "lifestyle"]),
                ("Christina Yang", "christinayang_decor", "Home decor UGC creator | Interior styling | Honest furniture reviews | Age 47", 33000, 4.6, "45-54", ["home"]),
                ("Heather Brooks", "heatherbrooks_ugc", "UGC content creator | Unboxing videos | Brand collaborations | PR friendly | 44", 87000, 5.9, "40-49", ["lifestyle"]),
                ("Valerie Scott", "valeriescott_well", "Wellness UGC creator | Menopause advocate | Supplement reviewer | Born 1971", 29000, 7.3, "50-59", ["wellness", "health"]),
                ("Denise Carter", "denisecarter_pet", "UGC creator for pet brands | Dog mom x3 | Honest product reviews | 46", 56000, 6.1, "45-54", ["lifestyle"]),
                ("Tina Murray", "tinamurray_fashion", "Fashion UGC creator | Midlife style | Content for clothing brands | Over 50", 43000, 3.9, "50-59", ["fashion"]),
                ("Kimberly Ross", "kimross_organic", "Organic lifestyle UGC creator | Clean eating | Brand ambassador | Mom in her 40s", 65000, 5.4, "40-49", ["food", "health"]),
                ("Stephanie Hall", "stephaniehall_diy", "DIY UGC creator | Home renovation | Product reviewer | Empty nester | 54", 27000, 6.5, "50-59", ["home", "crafts"]),
                ("Cynthia Bell", "cynthiabell_travel", "Travel UGC creator | Weekend getaways | Hotel reviews | Honest content | Age 49", 91000, 4.8, "45-54", ["travel"]),
                ("Amy Griffin", "amygriffin_beauty", "Beauty UGC creator | Anti-aging skincare | Honest brand reviews | 42", 78000, 5.6, "40-49", ["beauty"]),
                ("Teresa Coleman", "teresacoleman_read", "Book UGC creator | Audiobook reviewer | Content for publishers | Librarian | 55", 22000, 7.0, "55-60", ["education"]),
                ("Sharon Price", "sharonprice_craft", "Crafting UGC creator | Knitting & crochet | Yarn brand partner | In my 50s", 34000, 4.3, "50-59", ["crafts"]),
                ("Deborah James", "deborahjames_health", "Health UGC creator | Wellness over 50 | Supplement reviews | Honest content", 47000, 5.2, "50-59", ["health", "wellness"]),
                ("Pamela Rivera", "pamelarivera_cook", "UGC food creator | Meal prep queen | Kitchen gadget reviewer | Mom of teens", 58000, 4.5, "45-54", ["food"]),
                ("Janet Phillips", "janetphillips_yoga", "Yoga UGC creator | Mindful movement | Content for activewear brands | Age 48", 36000, 6.7, "45-54", ["fitness", "wellness"]),
                ("Maria Gonzalez", "mariagonzalez_ugc", "Bilingual UGC creator | Lifestyle content | Brand partner | Latina mom | 43", 69000, 5.1, "40-49", ["lifestyle"]),
                ("Robin Turner", "robinturner_home", "Home UGC creator | Organization expert | Product reviews | Born 1974", 42000, 4.0, "50-59", ["home"]),
                ("Kathleen Ward", "kathleenward_style", "Fashion UGC creator | Classic style | Honest clothing reviews | Fabulous at 56", 25000, 6.2, "55-60", ["fashion"]),
                ("Lori Patterson", "loripatterson_fit", "Fitness UGC creator | Strength training over 45 | Supplement reviews | Content creator", 53000, 5.8, "45-54", ["fitness"]),
                ("Monica Hughes", "monicahughes_life", "Lifestyle UGC creator | Product unboxing | Honest reviews | Midlife mom | Gen X", 44000, 4.7, "45-54", ["lifestyle"]),
                ("Dana Collins", "danacollins_ugc", "UGC creator for brands | Beauty & wellness | PR friendly | DM for collabs | 41", 81000, 5.3, "40-49", ["beauty", "wellness"]),
            ])
        ]
        # Filter by niche if specified
        if niche:
            niche_lower = niche.lower()
            mock_creators = [
                c for c in mock_creators
                if niche_lower in [t.lower() for t in c["profile"]["interests"]]
            ]
        return {
            "lookalikes": mock_creators[:limit],
            "total": len(mock_creators),
            "page": 0,
        }

    def _mock_profile(self, platform: str, user_id: str) -> dict:
        return {
            "userId": user_id,
            "profile": {
                "fullname": "Sarah Mitchell",
                "username": "sarahmitchell_life",
                "url": f"https://{platform}.com/sarahmitchell_life",
                "picture": "https://i.pravatar.cc/150?u=sarahmitchell",
                "bio": "Mom of 3 | Wellness advocate | Born 1978",
                "followers": 45000,
                "following": 1200,
                "engagementRate": 4.2,
                "avgLikes": 1890,
                "avgComments": 145,
                "avgViews": 12000,
                "postCount": 847,
                "gender": "FEMALE",
                "age": "45-54",
                "interests": ["lifestyle", "wellness", "parenting"],
            },
            "audienceReport": {
                "genders": [
                    {"code": "FEMALE", "weight": 0.78},
                    {"code": "MALE", "weight": 0.22},
                ],
                "ages": [
                    {"code": "25-34", "weight": 0.15},
                    {"code": "35-44", "weight": 0.35},
                    {"code": "45-54", "weight": 0.30},
                    {"code": "55-64", "weight": 0.12},
                    {"code": "65+", "weight": 0.08},
                ],
            },
        }
