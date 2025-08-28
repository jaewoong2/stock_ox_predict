"""
이 파일은 시스템에서 사용할 기본 티커 목록을 중앙에서 관리합니다.
향후 동적으로 인기 종목을 가져오는 로직으로 쉽게 교체할 수 있도록 분리되었습니다.
"""

# 2025-08-27 기준, 주요 미국 주식 100개
DEFAULT_TICKERS = [
    "CRWV", "SPY", "QQQ", "AMAT", "AMD", "ANET", "ASML", "AVGO", "COHR",
    "GFS", "KLAC", "MRVL", "MU", "NVDA", "NVMI", "ONTO", "SMCI", "STX",
    "TSM", "VRT", "WDC", "AXON", "LMT", "NOC", "RCAT", "AFRM", "APP",
    "COIN", "HOOD", "IREN", "MQ", "MSTR", "SOFI", "TOST", "CEG", "FSLR",
    "LNG", "NRG", "OKLO", "PWR", "SMR", "VST", "CRWD", "FTNT", "GTLB",
    "NET", "OKTA", "PANW", "S", "TENB", "ZS", "AAPL", "ADBE", "ADSK",
    "AI", "AMZN", "ASAN", "BILL", "CRM", "DDOG", "DOCN", "GOOGL", "HUBS",
    "META", "MNDY", "MSFT", "NOW", "PCOR", "PLTR", "SNOW", "VEEV", "IONQ",
    "QBTS", "RGTI", "PL", "RKLB", "LUNR", "ACHR", "ARBE", "JOBY", "TSLA",
    "UBER", "ORCL", "CFLT", "CRNC", "DXCM", "INTU", "IOT", "LRCX", "NFLX",
    "PODD", "PSTG", "RBLX", "RDDT", "SERV", "SHOP", "SOUN", "TDOC", "PATH",
    "DXYZ", "NKE",
]

def get_default_tickers() -> list[str]:
    """기본 유니버스 티커 목록을 반환합니다."""
    return DEFAULT_TICKERS
