import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("SCAMSERP_DATA_DIR", "var")))
    mode: str = field(default_factory=lambda: os.getenv("SCAMSERP_MODE", "demo"))
    admin_token: str = field(default_factory=lambda: os.getenv("SCAMSERP_ADMIN_TOKEN", ""))
    api_key: str = field(default_factory=lambda: os.getenv("SERPAPI_API_KEY") or os.getenv("SERP_API_KEY", ""))
    google_maps_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("Google_Maps_Api_Key", ""))
    daily_cap: int = field(default_factory=lambda: int(os.getenv("SCAMSERP_DAILY_CAP", "20")))
    monthly_cap: int = field(default_factory=lambda: int(os.getenv("SCAMSERP_MONTHLY_CAP", "200")))
    public_live: bool = field(default_factory=lambda: os.getenv("SCAMSERP_PUBLIC_LIVE", "false").lower() == "true")
    map_search_enabled: bool = field(default_factory=lambda: os.getenv("SCAMSERP_MAP_SEARCH", "true").lower() == "true")
    min_runs: int = field(default_factory=lambda: int(os.getenv("SCAMSERP_MIN_RUNS", "5")))
    rate_limit: int = field(default_factory=lambda: int(os.getenv("SCAMSERP_RATE_LIMIT", "30")))
    ads_requests_per_run: int = field(default_factory=lambda: int(os.getenv("SCAMSERP_ADS_REQUESTS_PER_RUN", "2")))
    scheduler_enabled: bool = field(default_factory=lambda: os.getenv("SCAMSERP_SCHEDULER", "false").lower() == "true")
    schedule_limit: int = field(default_factory=lambda: int(os.getenv("SCAMSERP_SCHEDULE_LIMIT", "6")))
    schedule_hours: int = field(default_factory=lambda: int(os.getenv("SCAMSERP_SCHEDULE_HOURS", "6")))

    def __post_init__(self):
        if self.mode not in {"demo", "live"}:
            raise ValueError("SCAMSERP_MODE must be demo or live")
        if min(self.daily_cap, self.monthly_cap) < 0 or min(self.min_runs, self.rate_limit) < 1:
            raise ValueError("Invalid cap, sample threshold, or rate limit")
        if not 0 <= self.ads_requests_per_run <= 10 or self.schedule_limit < 1 or self.schedule_hours < 1:
            raise ValueError("Invalid advertiser or scheduler limits")

    @property
    def db_path(self):
        return self.data_dir / f"{self.mode}.sqlite3"
