from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserProfile:
    user_id: int
    name: Optional[str] = None
    age: Optional[int] = None
    interests: Optional[str] = None
    mood: Optional[str] = None
    gender: Optional[str] = None
    last_active: datetime = None

    def __post_init__(self):
        if self.last_active is None:
            self.last_active = datetime.now()

    def update_profile(self, name: Optional[str] = None, age: Optional[int] = None,
                       interests: Optional[str] = None, mood: Optional[str] = None, gender: Optional[str] = None):
        if name is not None:
            self.name = name
        if age is not None:
            self.age = age
        if interests is not None:
            self.interests = interests
        if mood is not None:
            self.mood = mood
        if gender is not None:
            self.gender = gender

        self.last_active = datetime.now()