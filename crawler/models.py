# crawler/models.py
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional
from datetime import datetime


class Book(BaseModel):
    id: str = Field(..., description="Unique id")
    title: str
    description: Optional[str]
    category: Optional[str]
    price_including_tax: Optional[float]
    price_excluding_tax: Optional[float]
    availability: Optional[str]
    num_reviews: Optional[int]
    image_url: Optional[HttpUrl]
    rating: Optional[int]  # 1-5
    source_url: HttpUrl
    crawl_timestamp: datetime
    content_hash: str
    raw_snapshot_id: Optional[str]
