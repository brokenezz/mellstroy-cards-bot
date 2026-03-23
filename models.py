from enum import Enum
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

class Rarity(Enum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    
    @property
    def emoji(self):
        emojis = {
            "common": "⚪",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡"
        }
        return emojis[self.value]
    
    @property
    def chance(self):
        chances = {
            "common": 0.60,
            "rare": 0.25,
            "epic": 0.12,
            "legendary": 0.03
        }
        return chances[self.value]

@dataclass
class User:
    id: int
    username: Optional[str]
    level: int
    exp: int
    cards_count: int
    total_finds: int
    daily_bonus_date: Optional[datetime]
    is_premium: bool
    premium_until: Optional[datetime]
    created_at: datetime
    
    @property
    def next_level_exp(self) -> int:
        return self.level * 100
    
    @property
    def exp_progress(self) -> float:
        return self.exp / self.next_level_exp

@dataclass
class Card:
    id: int
    name: str
    rarity: Rarity
    image_url: str
    description: str
    video_url: Optional[str]
    
@dataclass
class UserCard:
    card_id: int
    name: str
    rarity: Rarity
    count: int
    image_url: str