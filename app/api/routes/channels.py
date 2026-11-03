import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.lookups import get_channel_or_404
from app.models import Channel
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post("", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
def create_channel(payload: ChannelCreate, db: DbSession) -> Channel:
    channel = Channel(**payload.model_dump())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.get("", response_model=list[ChannelRead])
def list_channels(db: DbSession) -> list[Channel]:
    return list(db.scalars(select(Channel).order_by(Channel.created_at)))


@router.get("/{channel_id}", response_model=ChannelRead)
def get_channel(channel_id: uuid.UUID, db: DbSession) -> Channel:
    return get_channel_or_404(db, channel_id)


@router.patch("/{channel_id}", response_model=ChannelRead)
def update_channel(channel_id: uuid.UUID, payload: ChannelUpdate, db: DbSession) -> Channel:
    channel = get_channel_or_404(db, channel_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(channel, key, value)
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: uuid.UUID, db: DbSession) -> None:
    db.delete(get_channel_or_404(db, channel_id))
    db.commit()
