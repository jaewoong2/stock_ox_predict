"""
이 파일은 시스템에서 사용할 기본 티커 목록을 중앙에서 관리합니다.
향후 동적으로 인기 종목을 가져오는 로직으로 쉽게 교체할 수 있도록 분리되었습니다.
"""

# 2025-12-09 기준, 시가총액 상위 주요 미국 주식 20개
DEFAULT_TICKERS = [
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    "GOOGL",  # Alphabet
    "AMZN",  # Amazon
    "NVDA",  # NVIDIA
    "META",  # Meta
    "TSLA",  # Tesla
    "AVGO",  # Broadcom
    "TSM",  # Taiwan Semiconductor
    "ORCL",  # Oracle
    "ASML",  # ASML
    "CRM",  # Salesforce
    "NFLX",  # Netflix
    "AMD",  # AMD
    "INTU",  # Intuit
    "UBER",  # Uber
    "IREN",  # Iren
    "APP",  # S&P 500 ETF
    "HOOD",  # Robinhood
    "MSTR",  # Microstrategy
    "PLTR",  # Palantir
]


def get_default_tickers() -> list[str]:
    """기본 유니버스 티커 목록을 반환합니다."""
    return DEFAULT_TICKERS
