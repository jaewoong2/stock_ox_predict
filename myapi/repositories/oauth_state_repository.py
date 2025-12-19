import json
from datetime import datetime, timezone
from typing import Dict, Optional, cast

from sqlalchemy.orm import Session

from myapi.models.oauth import OAuthState as OAuthStateModel


class OAuthStateRepository:
    """Persist and retrieve OAuth state to correlate login flow and client redirect."""

    def __init__(self, db: Session):
        self.db = db

    def save(self, state: str, client_redirect_uri: str, expires_at: datetime) -> None:
        """Persist OAuth state with explicit commit/rollback.

        Avoids nesting a new `Session.begin()` after a prior read started a transaction.
        """
        obj = OAuthStateModel(
            state=state, redirect_uri=client_redirect_uri, expires_at=expires_at
        )
        self.db.add(obj)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def pop(self, state: str) -> Optional[Dict[str, str]]:
        """Fetch and delete state. Returns state data as dict.

        Uses explicit commit/rollback to avoid nested transaction errors when a
        previous read implicitly opened a transaction on the Session.

        Returns:
            Dict with state data (type, provider/email, redirect_url) or None if not found/expired.
            For backward compatibility, converts plain string redirect_uri to dict format.
        """
        rec = (
            self.db.query(OAuthStateModel)
            .filter(OAuthStateModel.state == state)
            .first()
        )

        if not rec:
            return None

        # Expire stale states before returning the redirect/email value
        expires_at_value = cast(Optional[datetime], rec.expires_at)
        if expires_at_value and expires_at_value < datetime.now(timezone.utc):
            try:
                self.db.delete(rec)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return None

        # Parse JSON or handle plain string (backward compatibility)
        try:
            state_data = json.loads(str(rec.redirect_uri))
            # Ensure it's a dict
            if not isinstance(state_data, dict):
                state_data = {"redirect_url": str(rec.redirect_uri)}
        except (json.JSONDecodeError, ValueError):
            # Backward compatibility: plain string redirect_uri
            state_data = {"redirect_url": str(rec.redirect_uri)}

        try:
            self.db.delete(rec)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return state_data
