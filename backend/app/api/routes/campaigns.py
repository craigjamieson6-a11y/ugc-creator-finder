import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.models.campaign import Campaign, CampaignCreator
from app.models.creator import Creator

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    name: str
    filters_json: dict = {}


class AddCreatorRequest(BaseModel):
    creator_id: int
    notes: str = ""


@router.post("")
async def create_campaign(body: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(name=body.name, filters_json=body.filters_json)
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {
        "id": campaign.id,
        "name": campaign.name,
        "filters_json": campaign.filters_json,
        "created_at": campaign.created_at,
    }


@router.get("")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Campaign).options(selectinload(Campaign.creators)).order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "filters_json": c.filters_json,
            "created_at": c.created_at,
            "creator_count": len(c.creators),
        }
        for c in campaigns
    ]


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Campaign)
        .options(selectinload(Campaign.creators).selectinload(CampaignCreator.creator))
        .where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": campaign.id,
        "name": campaign.name,
        "filters_json": campaign.filters_json,
        "created_at": campaign.created_at,
        "creators": [
            {
                "id": cc.creator.id,
                "name": cc.creator.name,
                "platform": cc.creator.platform,
                "handle": cc.creator.handle,
                "avatar_url": cc.creator.avatar_url,
                "follower_count": cc.creator.follower_count,
                "engagement_rate": cc.creator.engagement_rate,
                "overall_score": cc.creator.overall_score,
                "notes": cc.notes,
                "added_at": cc.added_at,
            }
            for cc in campaign.creators
        ],
    }


@router.post("/{campaign_id}/creators")
async def add_creator_to_campaign(
    campaign_id: int,
    body: AddCreatorRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify campaign exists
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Verify creator exists
    result = await db.execute(select(Creator).where(Creator.id == body.creator_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Creator not found")

    # Check if already added
    result = await db.execute(
        select(CampaignCreator).where(
            CampaignCreator.campaign_id == campaign_id,
            CampaignCreator.creator_id == body.creator_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Creator already in campaign")

    cc = CampaignCreator(
        campaign_id=campaign_id,
        creator_id=body.creator_id,
        notes=body.notes,
    )
    db.add(cc)
    await db.commit()
    return {"status": "added"}


@router.delete("/{campaign_id}/creators/{creator_id}")
async def remove_creator_from_campaign(
    campaign_id: int,
    creator_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CampaignCreator).where(
            CampaignCreator.campaign_id == campaign_id,
            CampaignCreator.creator_id == creator_id,
        )
    )
    cc = result.scalar_one_or_none()
    if not cc:
        raise HTTPException(status_code=404, detail="Creator not in campaign")
    await db.delete(cc)
    await db.commit()
    return {"status": "removed"}


@router.get("/{campaign_id}/export")
async def export_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Campaign)
        .options(selectinload(Campaign.creators).selectinload(CampaignCreator.creator))
        .where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name", "Platform", "Handle", "Profile URL", "Followers",
        "Engagement Rate", "Overall Score", "Engagement Score",
        "Quality Score", "Relevance Score", "Age Range", "Gender",
        "Bio", "Notes",
    ])

    for cc in campaign.creators:
        c = cc.creator
        writer.writerow([
            c.name, c.platform, c.handle, c.profile_url, c.follower_count,
            c.engagement_rate, c.overall_score, c.engagement_score,
            c.quality_score, c.relevance_score, c.estimated_age_range,
            c.gender, c.bio, cc.notes,
        ])

    output.seek(0)
    filename = f"campaign_{campaign.name.replace(' ', '_')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
