from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Article:
    title: str
    link: str
    source: str
    source_weight: float
    published: datetime
    summary: str = ""
    cluster_size: int = 1
    score: float = 0.0

    @property
    def hours_old(self) -> float:
        now = datetime.now(timezone.utc)
        return max(0.0, (now - self.published).total_seconds() / 3600)
