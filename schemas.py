from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# Для создания пользователя
class UserCreate(BaseModel):
    username: str
    email: EmailStr

# Для ответа
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: Optional[datetime] = None