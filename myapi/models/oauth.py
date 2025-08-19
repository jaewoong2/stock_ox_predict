from sqlalchemy import Column, String, DateTime, func
from myapi.models.base import BaseModel


class OAuthState(BaseModel):
    __tablename__ = "oauth_states"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    state = Column(String, primary_key=True)
    redirect_uri = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
