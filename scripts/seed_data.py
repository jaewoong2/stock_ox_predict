"""
기본 종목 데이터 시드 스크립트
미국 주식 주요 종목들을 초기 데이터로 설정
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime
from sqlalchemy.orm import Session
from myapi.database.connection import SessionLocal
from myapi.models.session import ActiveUniverse
from myapi.models.rewards import RewardsInventory


def seed_universe_data():
    """기본 종목 데이터 시드"""

    # 주요 미국 주식 종목 (인기도 순)
    default_symbols = [
        ("AAPL", 1),  # Apple Inc.
        ("MSFT", 2),  # Microsoft Corporation
        ("GOOGL", 3),  # Alphabet Inc. Class A
        ("AMZN", 4),  # Amazon.com Inc.
        ("TSLA", 5),  # Tesla Inc.
        ("META", 6),  # Meta Platforms Inc.
        ("NVDA", 7),  # NVIDIA Corporation
        ("JPM", 8),  # JPMorgan Chase & Co.
        ("V", 9),  # Visa Inc.
        ("JNJ", 10),  # Johnson & Johnson
    ]

    db = SessionLocal()
    try:
        today = date.today()

        # 기존 오늘 데이터 삭제
        db.query(ActiveUniverse).filter(ActiveUniverse.trading_day == today).delete()

        # 새 데이터 삽입
        for symbol, seq in default_symbols:
            universe_entry = ActiveUniverse(trading_day=today, symbol=symbol, seq=seq)
            db.add(universe_entry)

        db.commit()
        print(f"✅ 종목 시드 데이터 생성 완료: {len(default_symbols)}개 종목")
        print(f"📅 거래일: {today}")
        print("📊 추가된 종목:")
        for symbol, seq in default_symbols:
            print(f"   {seq:2d}. {symbol}")

    except Exception as e:
        db.rollback()
        print(f"❌ 종목 시드 데이터 생성 실패: {str(e)}")
        raise
    finally:
        db.close()


def seed_rewards_data():
    """기본 리워드 데이터 시드"""
    from myapi.models.rewards import RewardsInventory

    # 기본 리워드 목록
    default_rewards = [
        {
            "sku": "STARBUCKS_5000",
            "title": "스타벅스 기프트카드 5,000원",
            "cost_points": 500,
            "stock": 100,
            "vendor": "starbucks",
        },
        {
            "sku": "STARBUCKS_10000",
            "title": "스타벅스 기프트카드 10,000원",
            "cost_points": 1000,
            "stock": 50,
            "vendor": "starbucks",
        },
        {
            "sku": "CGV_MOVIE_TICKET",
            "title": "CGV 영화관람권",
            "cost_points": 1500,
            "stock": 30,
            "vendor": "cgv",
        },
        {
            "sku": "GIFTICON_CHICKEN",
            "title": "치킨 기프티콘",
            "cost_points": 2000,
            "stock": 20,
            "vendor": "gifticon",
        },
        {
            "sku": "AMAZON_GIFTCARD_10",
            "title": "Amazon Gift Card $10",
            "cost_points": 1200,
            "stock": 50,
            "vendor": "amazon",
        },
    ]

    db = SessionLocal()
    try:
        for reward_data in default_rewards:
            # 기존 리워드 확인
            existing = (
                db.query(RewardsInventory)
                .filter(RewardsInventory.sku == reward_data["sku"])
                .first()
            )

            if not existing:
                reward = RewardsInventory(
                    sku=reward_data["sku"],
                    title=reward_data["title"],
                    cost_points=reward_data["cost_points"],
                    stock=reward_data["stock"],
                    reserved=0,
                    vendor=reward_data["vendor"],
                )
                db.add(reward)
                print(f"✅ 리워드 추가: {reward_data['title']}")
            else:
                print(f"⏭️  이미 존재하는 리워드: {reward_data['title']}")

        db.commit()
        print(f"✅ 리워드 시드 데이터 생성 완료: {len(default_rewards)}개 리워드")

    except Exception as e:
        db.rollback()
        print(f"❌ 리워드 시드 데이터 생성 실패: {str(e)}")
        raise
    finally:
        db.close()


def main():
    """시드 데이터 실행"""
    print("🌱 시드 데이터 생성을 시작합니다...")
    print()

    # 종목 데이터 시드
    print("📊 종목 데이터 시드 중...")
    seed_universe_data()
    print()

    # 리워드 데이터 시드
    print("🎁 리워드 데이터 시드 중...")
    seed_rewards_data()
    print()

    print("🎉 모든 시드 데이터 생성이 완료되었습니다!")


if __name__ == "__main__":
    main()
