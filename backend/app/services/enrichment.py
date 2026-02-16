import re
from datetime import datetime
from typing import Optional


# Common female first names for low-confidence gender signal
COMMON_FEMALE_NAMES = {
    "sarah", "jennifer", "lisa", "jessica", "michelle", "amanda", "stephanie",
    "nicole", "melissa", "elizabeth", "heather", "amy", "anna", "angela",
    "rebecca", "laura", "karen", "christine", "catherine", "andrea",
    "susan", "rachel", "mary", "donna", "carol", "sandra", "diane",
    "pamela", "sharon", "kelly", "deborah", "julie", "kim", "tammy",
    "tracy", "tina", "wendy", "cheryl", "brenda", "denise", "teresa",
    "maria", "linda", "barbara", "nancy", "betty", "margaret", "patricia",
    "dorothy", "ruth", "helen", "janet", "debra", "carolyn", "cynthia",
    "christina", "ashley", "emily", "kimberly", "megan", "brittany",
    "samantha", "danielle", "natalie", "kathleen", "victoria", "vanessa",
    "jacqueline", "holly", "jill", "amber", "allison", "erin", "april",
    "katie", "kate", "lauren", "hannah", "abigail", "alexis", "courtney",
    "brooke", "dawn", "stacey", "tiffany", "crystal", "robin", "shannon",
    "tamara", "colleen", "leslie", "jenn", "jen", "liz", "sue", "becky",
    "steph", "nikki", "manda", "missy",
}


class EnrichmentService:
    """Infer age/gender from bio text and other signals."""

    # Keywords suggesting age ranges
    AGE_INDICATORS = {
        "40-49": [
            "in my 40s", "40s", "over 40", "forty", "born 198",
            "born in the 80s", "gen x", "gen-x",
        ],
        "45-54": [
            "born 197", "born in the 70s", "midlife", "middle age",
            "mom of teens", "teenage kids",
        ],
        "50-59": [
            "in my 50s", "50s", "over 50", "fifty", "born 196",
            "born in the 60s", "empty nester", "grandma", "grandmother",
            "nana", "grandkids",
        ],
        "55-60": [
            "born 196", "late 50s", "almost 60", "approaching 60",
        ],
    }

    FEMALE_INDICATORS = [
        "mom", "mother", "mama", "mum", "wife", "she/her",
        "girl", "woman", "women", "queen", "goddess", "lady",
        "feminine", "sister", "daughter", "grandma", "grandmother",
        "auntie", "aunt",
    ]

    def infer_age_range(self, bio: str) -> tuple[Optional[str], str]:
        """Return (estimated_age_range, confidence)."""
        if not bio:
            return None, "low"

        bio_lower = bio.lower()

        # Try to extract explicit birth year
        birth_year_match = re.search(r"born\s*(?:in\s*)?(\d{4})", bio_lower)
        if birth_year_match:
            birth_year = int(birth_year_match.group(1))
            age = datetime.now().year - birth_year
            if 40 <= age <= 60:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}", "high"

        # Try to extract explicit age
        age_match = re.search(r"(?:age\s*|aged?\s*|i'?m\s+)(\d{2})", bio_lower)
        if age_match:
            age = int(age_match.group(1))
            if 40 <= age <= 60:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}", "high"

        # Explicit age mention like "at 47" or "47 years"
        explicit_age = re.search(r"(?:at\s+)(\d{2})(?:\s+years|\s+and)", bio_lower)
        if explicit_age:
            age = int(explicit_age.group(1))
            if 40 <= age <= 60:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}", "high"

        # "XX-year-old" or "XX year old" pattern
        year_old_match = re.search(r"(\d{2})[\s-]*year[\s-]*old", bio_lower)
        if year_old_match:
            age = int(year_old_match.group(1))
            if 40 <= age <= 60:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}", "high"

        # "class of 19XX" → infer birth year (~18 at graduation)
        class_of_match = re.search(r"class\s+of\s+(?:'?)((?:19|20)\d{2})", bio_lower)
        if class_of_match:
            grad_year = int(class_of_match.group(1))
            birth_year = grad_year - 18
            age = datetime.now().year - birth_year
            if 40 <= age <= 60:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}", "medium"

        # "est. 19XX" or "since 19XX" → birth year
        est_match = re.search(r"(?:est\.?\s*|since\s+)(19[67]\d)", bio_lower)
        if est_match:
            birth_year = int(est_match.group(1))
            age = datetime.now().year - birth_year
            if 40 <= age <= 60:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}", "medium"

        # Pipe-delimited or standalone age: "| 47 |" or "52 yo" or "47 y/o"
        pipe_age = re.search(r"(?:\|\s*)(\d{2})(?:\s*\||(?:\s*y/?o))", bio_lower)
        if pipe_age:
            age = int(pipe_age.group(1))
            if 40 <= age <= 60:
                decade_start = (age // 5) * 5
                return f"{decade_start}-{decade_start + 4}", "high"

        # Check keyword indicators
        for age_range, keywords in self.AGE_INDICATORS.items():
            if any(kw in bio_lower for kw in keywords):
                return age_range, "medium"

        return None, "low"

    def infer_gender(self, bio: str, name: str = "") -> tuple[Optional[str], str]:
        """Return (gender, confidence).

        Uses bio keywords as primary signal, and first name as a
        low-confidence fallback.
        """
        if not bio and not name:
            return None, "low"

        bio_lower = (bio or "").lower()
        female_matches = sum(1 for kw in self.FEMALE_INDICATORS if kw in bio_lower)

        if female_matches >= 2:
            return "female", "high"
        elif female_matches == 1:
            return "female", "medium"

        # Fallback: check if first name is a common female name
        if name:
            first_name = name.strip().split()[0].lower() if name.strip() else ""
            if first_name in COMMON_FEMALE_NAMES:
                return "female", "low"

        return None, "low"

    def enrich_creator_demographics(
        self,
        bio: str = "",
        api_gender: Optional[str] = None,
        api_age_range: Optional[str] = None,
        name: str = "",
    ) -> dict:
        """Combine API data with bio inference for best demographic estimate."""
        result = {
            "gender": api_gender,
            "gender_confidence": "high" if api_gender else "low",
            "age_range": api_age_range,
            "age_confidence": "high" if api_age_range else "low",
        }

        if not api_gender:
            gender, confidence = self.infer_gender(bio, name)
            result["gender"] = gender
            result["gender_confidence"] = confidence

        if not api_age_range:
            age_range, confidence = self.infer_age_range(bio)
            result["age_range"] = age_range
            result["age_confidence"] = confidence

        return result
