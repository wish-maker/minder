# services/marketplace/models/plugin.py
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


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
    author_email: Optional[str] = None
    repository_url: Optional[str] = None
    distribution_type: DistributionType = DistributionType.GIT
    docker_image: Optional[str] = None
    pricing_model: PricingModel = PricingModel.FREE
    base_tier: str = "community"
    category_id: Optional[str] = None


class PluginUpdate(BaseModel):
    """Model for updating a plugin"""

    display_name: Optional[str] = None
    description: Optional[str] = None
    pricing_model: Optional[PricingModel] = None
    base_tier: Optional[str] = None
    status: Optional[PluginStatus] = None
    featured: Optional[bool] = None


class PluginResponse(BaseModel):
    """Model for plugin response"""

    id: str
    name: str
    display_name: str
    description: Optional[str]
    author: str
    author_email: Optional[str]
    repository_url: Optional[str]
    distribution_type: str
    docker_image: Optional[str]
    current_version: Optional[str]
    pricing_model: str
    base_tier: str
    status: str
    featured: bool
    download_count: int
    rating_average: Optional[float]
    rating_count: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]
    developer_id: Optional[str]
    category_id: Optional[str]

    class Config:
        from_attributes = True


class PluginListResponse(BaseModel):
    """Model for plugin list response"""

    plugins: List[PluginResponse]
    count: int
    page: int
    page_size: int
    total_pages: int
