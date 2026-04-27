from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    CITIZEN = "citizen"
    MUNICIPAL = "municipal"
    ADMIN = "admin"


class ReportStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class LocationModel(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None
    source: Literal["gps", "exif", "manual"] = "gps"


class DetectionBox(BaseModel):
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    area_px: Optional[float] = None


class XAIResult(BaseModel):
    method: str
    heatmap_b64: Optional[str] = None
    overlay_b64: Optional[str] = None
    metadata: dict = {}


class InferenceResult(BaseModel):
    detections: List[DetectionBox]
    primary_class: str
    primary_class_id: int
    confidence: float
    severity: SeverityLevel
    severity_score: float
    num_detections: int
    xai: XAIResult
    inference_time_ms: int


class ReportCreate(BaseModel):
    location: LocationModel
    description: Optional[str] = Field(None, max_length=500)
    xai_mode: Optional[Literal["gradcam", "lime", "zoolime", "shap", "none"]] = "gradcam"


class ReportModel(BaseModel):
    id: Optional[str] = None
    citizen_uid: str
    citizen_name: Optional[str] = None
    status: ReportStatus = ReportStatus.PENDING
    location: LocationModel
    description: Optional[str] = None

    # Image info
    image_url: Optional[str] = None
    image_filename: Optional[str] = None

    # AI results
    inference: Optional[InferenceResult] = None

    # XAI image URLs (stored separately for efficient loading)
    gradcam_url: Optional[str] = None
    zoolime_url: Optional[str] = None

    # Municipal
    assigned_to: Optional[str] = None
    municipal_notes: Optional[str] = None
    priority_score: Optional[float] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    # Rewards
    reward_issued: bool = False
    reward_tokens: int = 0

    class Config:
        use_enum_values = True


class ReportUpdate(BaseModel):
    status: Optional[ReportStatus] = None
    assigned_to: Optional[str] = None
    municipal_notes: Optional[str] = None
    priority_score: Optional[float] = None


class UserProfile(BaseModel):
    uid: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole = UserRole.CITIZEN
    total_reports: int = 0
    resolved_reports: int = 0
    total_tokens: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class PaginatedReports(BaseModel):
    reports: List[ReportModel]
    total: int
    page: int
    page_size: int
    has_next: bool
