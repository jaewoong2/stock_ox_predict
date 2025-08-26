"""
배치 스케줄링 시스템 사용 예제

이 파일은 시간대별 Queue 기반 배치 시스템의 사용법을 보여줍니다.
"""

import asyncio
import json
from datetime import date, datetime
from typing import Dict, Any

# 예제 SQS FIFO 큐 URL (실제 환경에서는 AWS 콘솔에서 생성)
EXAMPLE_QUEUE_URL = "https://sqs.ap-northeast-2.amazonaws.com/123456789012/prediction-batch-jobs.fifo"

async def example_schedule_daily_workflow():
    """일일 워크플로우 스케줄링 예제"""
    import httpx
    
    # API 엔드포인트
    base_url = "http://localhost:8000"
    headers = {"Authorization": "Bearer YOUR_ADMIN_TOKEN"}
    
    # 오늘의 전체 배치 워크플로우 스케줄링
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/batch/schedule/daily-workflow",
            params={
                "queue_url": EXAMPLE_QUEUE_URL,
                "trading_day": "2024-01-15"  # 선택사항
            },
            headers=headers
        )
        
        result = response.json()
        print("=== 일일 워크플로우 스케줄링 결과 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if result["success"]:
            workflow_result = result["data"]["workflow_result"]
            print(f"총 작업 수: {workflow_result['total_jobs']}")
            print(f"성공: {workflow_result['successful_jobs']}")
            print(f"실패: {workflow_result['failed_jobs']}")
            
            print("\n스케줄된 작업들:")
            for job in workflow_result["jobs"]:
                print(f"- {job['operation']}: {job['status']} (지연: {job.get('delay_seconds', 0)}초)")


async def example_schedule_immediate_settlement():
    """즉시 정산 스케줄링 예제"""
    import httpx
    
    base_url = "http://localhost:8000"
    headers = {"Authorization": "Bearer YOUR_ADMIN_TOKEN"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/batch/schedule/immediate-settlement",
            params={
                "queue_url": EXAMPLE_QUEUE_URL,
                "trading_day": "2024-01-14"  # 어제 결과를 즉시 정산
            },
            headers=headers
        )
        
        result = response.json()
        print("=== 즉시 정산 스케줄링 결과 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_get_upcoming_jobs():
    """예정된 작업 조회 예제"""
    import httpx
    
    base_url = "http://localhost:8000"
    headers = {"Authorization": "Bearer YOUR_ADMIN_TOKEN"}
    
    with httpx.Client() as client:
        response = client.get(
            f"{base_url}/batch/schedule/upcoming",
            params={"hours_ahead": 48},  # 48시간 내 예정 작업
            headers=headers
        )
        
        result = response.json()
        print("=== 예정된 배치 작업들 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if result["success"]:
            upcoming_jobs = result["data"]["upcoming_jobs"]
            print(f"\n다음 {result['data']['hours_ahead']}시간 내 {len(upcoming_jobs)}개 작업 예정:")
            
            for job in upcoming_jobs:
                print(f"- {job['job_type']}: {job['scheduled_time']} ({job['time_until']} 후)")


async def example_queue_status():
    """큐 상태 조회 예제"""
    import httpx
    
    base_url = "http://localhost:8000"
    headers = {"Authorization": "Bearer YOUR_ADMIN_TOKEN"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/batch/queue/status",
            params={"queue_url": EXAMPLE_QUEUE_URL},
            headers=headers
        )
        
        result = response.json()
        print("=== 큐 상태 조회 결과 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))


async def example_execute_batch_job():
    """배치 작업 실행 예제 (SQS 워커에서 사용)"""
    import httpx
    
    base_url = "http://localhost:8000"
    headers = {"Authorization": "Bearer YOUR_ADMIN_TOKEN"}
    
    # SQS에서 받은 메시지 예제
    job_message = {
        "job_id": "settlement_2024-01-15_abc12345",
        "job_type": "settlement",
        "trading_day": "2024-01-14",
        "scheduled_time": "2024-01-15T06:00:00+09:00",
        "payload": {
            "action": "settle_predictions",
            "trading_day": "2024-01-14",
            "auto_award_points": True,
            "settlement_source": "eod_price"
        },
        "priority": 1,
        "created_at": "2024-01-15T05:59:50Z"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/batch/execute/job",
            json=job_message,
            headers=headers
        )
        
        result = response.json()
        print("=== 배치 작업 실행 결과 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if result["success"]:
            execution_result = result["data"]["execution_result"]
            print(f"작업 ID: {execution_result['job_id']}")
            print(f"작업 타입: {execution_result['job_type']}")
            print(f"실행 시간: {execution_result['execution_time_ms']}ms")
            print(f"메시지: {execution_result['message']}")


def example_schedule_timeline():
    """배치 스케줄링 타임라인 예제"""
    print("=== 일일 예측 시스템 배치 스케줄 (KST) ===")
    print("""
    00:00 - 다음날 유니버스 준비 (선택사항)
    06:00 - 전날 예측 결과 정산 및 포인트 지급 🎯
    06:01 - 새로운 예측 세션 시작 (OPEN) 🎯  
    06:05 - 오늘의 유니버스 설정 (기본 20개 종목)
    09:30 - 가격 캐시 갱신 (미장 시작 후)
    23:59 - 예측 마감 및 세션 종료 (CLOSED) 🎯
    
    🎯 = 중요한 시스템 전환 시점
    """)
    
    print("=== 지원하는 작업 타입들 ===")
    job_types = [
        ("settlement", "예측 결과 정산 및 포인트 지급"),
        ("session_start", "예측 세션 시작 (OPEN 상태로 전환)"),
        ("session_end", "예측 세션 종료 (CLOSED 상태로 전환)"),
        ("universe_prepare", "일일 예측 대상 종목 설정"),
        ("price_cache_refresh", "실시간 가격 데이터 캐시 갱신")
    ]
    
    for job_type, description in job_types:
        print(f"- {job_type}: {description}")


async def main():
    """모든 예제를 실행합니다."""
    print("🚀 배치 스케줄링 시스템 예제 실행")
    print("=" * 50)
    
    # 1. 타임라인 설명
    example_schedule_timeline()
    
    print("\n" + "=" * 50)
    
    # 2. API 사용 예제들 (실제 API가 실행 중일 때만 동작)
    try:
        # 주석을 해제하고 실제 토큰을 사용하여 테스트
        # await example_schedule_daily_workflow()
        # await example_schedule_immediate_settlement()  
        # example_get_upcoming_jobs()
        # await example_queue_status()
        # await example_execute_batch_job()
        
        print("API 예제들은 주석 처리되어 있습니다.")
        print("실제 테스트하려면 main() 함수에서 주석을 해제하고 올바른 토큰을 설정하세요.")
        
    except Exception as e:
        print(f"API 호출 중 오류 발생: {e}")
        print("API 서버가 실행 중인지 확인하고, 올바른 인증 토큰을 사용하세요.")


if __name__ == "__main__":
    asyncio.run(main())