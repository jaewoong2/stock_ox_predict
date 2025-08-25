from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from myapi.models.internal import OAuthState as OAuthStateModel


class OAuthStateRepository:
    """Persist and retrieve OAuth state to correlate login flow and client redirect."""

    def __init__(self, db: Session):
        self.db = db

    def save(self, state: str, client_redirect_uri: str, expires_at: datetime) -> None:
        obj = OAuthStateModel(
            state=state, redirect_uri=client_redirect_uri, expires_at=expires_at
        )
        self.db.add(obj)
        try:
            self.db.flush()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def pop(self, state: str) -> Optional[str]:
        rec = (
            self.db.query(OAuthStateModel)
            .filter(OAuthStateModel.state == state)
            .first()
        )

        if not rec:
            return None

        client_redirect = rec.redirect_uri
        try:
            self.db.delete(rec)
            self.db.flush()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return str(client_redirect)
