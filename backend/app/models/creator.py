from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.database import Base


class Creator(Base):
    __tablename__ = "creators"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    platform = Column(String, nullable=False, index=True)
    handle = Column(String, nullable=False)
    profile_url = Column(String)
    avatar_url = Column(String)

    follower_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    avg_likes = Column(Integer, default=0)
    avg_comments = Column(Integer, default=0)
    avg_views = Column(Integer, default=0)
    post_count = Column(Integer, default=0)

    estimated_age_range = Column(String)  # e.g. "40-50"
    gender = Column(String)
    bio = Column(Text)
    niche_tags = Column(JSON, default=list)
    audience_demographics = Column(JSON, default=dict)

    overall_score = Column(Float, default=0.0)
    engagement_score = Column(Float, default=0.0)
    quality_score = Column(Float, default=0.0)
    relevance_score = Column(Float, default=0.0)
    demographic_confidence = Column(String, default="low")  # high/medium/low

    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaign_links = relationship("CampaignCreator", back_populates="creator")
