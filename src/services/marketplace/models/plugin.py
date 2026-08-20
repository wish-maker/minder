# services/marketplace/models/plugin.py
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


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
        None,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    developer_id: Optional[str] = Field(
        None,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    # Backend services this plugin needs at runtime (e.g. ["influxdb"]) -- synced
    # from plugin-registry's own PluginMetadata.databases (#484), surfaced on
    # Available/Installed Plugins so a user can tell it needs a bundle they
    # haven't enabled instead of it just silently writing nowhere.
    requires_services: List[str] = Field(default_factory=list)
    # display_name/description are plain-text fields, stored and returned as
    # JSON string values and rendered by the client as React text nodes
    # (`{plugin.description}`), which HTML-escapes on insertion into the DOM
    # -- there is no raw-HTML consumer anywhere in this codebase. An
    # html.escape() here used to run at WRITE time regardless, so "&" and "'"
    # were stored as literal "&amp;"/"&#x27;" and then rendered verbatim
    # (correctly, but of the already-corrupted text) -- e.g. a real plugin's
    # "inventories & monitors" became "inventories &amp; monitors" in the API
    # response and on the page. Removed; if a future consumer ever renders
    # these fields as raw HTML, it must escape at that render site instead.


class PluginUpdate(BaseModel):
    """Model for updating a plugin"""

    # #747: lets plugin-registry's id-based sync reconcile a plugin's catalog
    # row in place when its (stable-id-tracked) directory has been renamed,
    # instead of `name` only ever being set once at creation and going stale.
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    author: Optional[str] = Field(None, max_length=100)
    pricing_model: Optional[PricingModel] = None
    base_tier: Optional[str] = None
    status: Optional[PluginStatus] = None
    featured: Optional[bool] = None
    requires_services: Optional[List[str]] = None


class PluginResponse(BaseModel):
    """Model for plugin response"""

    id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
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
        None,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    category_id: Optional[str] = Field(
        None,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    requires_services: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PluginListResponse(BaseModel):
    """Model for plugin list response.

    Carries the platform-standard ``limit``/``offset``/``total`` fields (#147/C6)
    alongside the original ``page``/``page_size``/``total_pages`` — a superset, so
    existing page-based clients keep working while new clients use limit/offset.
    """

    plugins: List[PluginResponse]
    count: int
    # Platform-standard pagination (canonical)
    total: int = 0
    limit: int = 0
    offset: int = 0
    # Deprecated page-based fields, kept for backward compatibility
    page: int
    page_size: int
    total_pages: int
