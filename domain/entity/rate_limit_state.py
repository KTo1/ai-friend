# domain/entity/rate_limit_state.py
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RateLimitState:
    user_id: int
    minute_window_start: datetime = None
    minute_count: int = 0
    hour_window_start: datetime = None
    hour_count: int = 0
    last_updated: datetime = None

    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()
