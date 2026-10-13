from typing import List, Optional
from pydantic import BaseModel, Field

# --- Authentication Models ---

class AuthRequest(BaseModel):
    pin: str = Field(..., description="User access PIN code (default '7777')")

class AuthResponse(BaseModel):
    status: str = Field(default="ok", json_schema_extra={"example": "ok"})
    token: str = Field(..., description="Session token hex string")
    expires_in: int = Field(default=2592000, description="Token validity duration in seconds (30 days)")

class ErrorDetail(BaseModel):
    detail: str

# --- Stakes Models ---

class StakeItem(BaseModel):
    stake: str = Field(..., description="Stake identifier, e.g. '$1'")
    promotion_id: int = Field(..., description="GGPoker promotion ID")
    name: str = Field(..., description="Full promotion display name")
    group_id: Optional[int] = Field(default=None, description="Group ID")
    prize_pool: Optional[str] = Field(default=None, description="Formatted prize pool e.g. '$1,000'")
    total_prize: float = Field(default=0.0, description="Numeric total prize value in USD")
    status: str = Field(default="RUNNING", description="Promotion status")
    started_at: Optional[str] = Field(default=None, description="Promotion start ISO timestamp")
    finished_at: Optional[str] = Field(default=None, description="Promotion finish ISO timestamp")

class StakesResponse(BaseModel):
    group_id: int
    group_name: Optional[str] = None
    cutoff_utc: str
    cached: bool = False
    stakes: List[StakeItem]

# --- Leaderboard & Hero Telemetry Models ---

class PrizeInfo(BaseModel):
    type: Optional[str] = Field(default="TICKET", description="Prize type: TICKET, CASH, etc.")
    text: Optional[str] = Field(default=None, description="Formatted text e.g. '$10 Ticket' or '$15'")
    value: float = Field(default=0.0, description="Total prize USD value")
    currency: Optional[str] = Field(default="USD", description="Currency identifier")
    quantity: Optional[int] = Field(default=None, description="Number of tickets if applicable")

class PlayerEntry(BaseModel):
    rank: int
    nickname: str
    points: float
    country: Optional[str] = None
    prize: Optional[PrizeInfo] = None
    prize_str: Optional[str] = None
    gain_delta: Optional[float] = None
    gap_to_prev: Optional[float] = None
    is_hero: bool = False

class HeroTelemetry(BaseModel):
    nickname: str
    found: bool
    rank: Optional[int] = None
    points: Optional[float] = None
    prize: Optional[PrizeInfo] = None
    prize_value: Optional[float] = None
    prize_type: Optional[str] = None
    target_rank: Optional[int] = None
    pts_to_next: Optional[float] = None
    prize_diff_to_next: Optional[float] = None
    estimated_wins_to_next: Optional[int] = None
    trailing_rank: Optional[int] = None
    lead_over_prev: Optional[float] = None
    cushion_danger: Optional[bool] = False
    status_text: Optional[str] = None
    target_prize: Optional[PrizeInfo] = None

class LeaderboardResponse(BaseModel):
    stake: str
    promotion_id: Optional[int] = None
    updated_at: Optional[str] = None
    cutoff_utc: Optional[str] = None
    cutoff_seconds: Optional[int] = None
    cutoff_seconds_remaining: Optional[int] = None
    cached: bool = False
    cache_age_sec: Optional[float] = 0.0
    total_players: int = 0
    hero: Optional[HeroTelemetry] = None
    players: List[PlayerEntry] = []
    leaderboard: List[PlayerEntry] = []
