from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from myapi.models.base import BaseModel


class OAuthState(BaseModel):
    __tablename__ = "oauth_states"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    state: Mapped[str] = mapped_column(String, primary_key=True)
    redirect_uri: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
