from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from uuid import UUID

class UserBase(BaseModel):
    email: str
    full_name: str
    user_name : str
    phone: str

class User(UserBase):
    user_id: UUID
    password_hash: str
    loyalty_points: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True