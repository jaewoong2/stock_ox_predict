from pydantic import BaseModel


class MarketStatusResponse(BaseModel):
    is_trading_day: bool
    message: str
    current_kst: str
    is_prediction_window: bool

    class Config:
        from_attributes = True

