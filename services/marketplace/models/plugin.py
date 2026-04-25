# services/marketplace/models/plugin.py
import html
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class PricingModel(str, Enum):
    """Pricing model types"""

    FREE = "free"
    PAID = "paid"
    FREEMIUM = "freemium"


class DistributionType(str, Enum):
    """Plugin distribution types"""

    GIT = "git"
    DOCKER = "docker"
    HYBRID = "hybrid"


class PluginStatus(str, Enum):
    """Plugin status in marketplace"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class PluginCreate(BaseModel):
    """Model for creating a new plugin"""

    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    author: str = Field(..., max_length=100)
    author_email: Optional[EmailStr] = None
    repository_url: Optional[HttpUrl] = None
    distribution_type: DistributionType = DistributionType.GIT
    docker_image: Optional[str] = None
    pricing_model: PricingModel = PricingModel.FREE
    base_tier: str = "community"
    category_id: Optional[str] = Field(
        None, pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    developer_id: Optional[str] = Field(
        None, pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )

    @field_validator("display_name", "description", mode="after")
    @classmethod
    def sanitize_html(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize HTML in text fields"""
        if v is None:
            return None
        return html.escape(v)


class PluginUpdate(BaseModel):
    """Model for updating a plugin"""

    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    pricing_model: Optional[PricingModel] = None
    base_tier: Optional[str] = None
    status: Optional[PluginStatus] = None
    featured: Optional[bool] = None

    @field_validator("display_name", "description", mode="after")
    @classmethod
    def sanitize_html(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize HTML in text fields"""
        if v is None:
            return None
        return html.escape(v)


class PluginResponse(BaseModel):
    """Model for plugin response"""

    id: str = Field(..., pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    name: str
    display_name: str
    description: Optional[str]
    author: str
    author_email: Optional[EmailStr]
    repository_url: Optional[HttpUrl]
    distribution_type: DistributionType
    docker_image: Optional[str]
    current_version: Optional[str]
    pricing_model: PricingModel
    base_tier: str
    status: PluginStatus
    featured: bool
    download_count: int = Field(..., ge=0)
    rating_average: Optional[float] = Field(None, ge=0, le=5.0)
    rating_count: int = Field(..., ge=0)
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]
    developer_id: Optional[str] = Field(
        None, pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    category_id: Optional[str] = Field(
        None, pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )

    class Config:
        from_attributes = True


class PluginListResponse(BaseModel):
    """Model for plugin list response"""

    plugins: List[PluginResponse]
    count: int
    page: int
    page_size: int
    total_pages: int
