import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from datetime import date
from myapi.main import create_app


@pytest.fixture
def client():
    """테스트 클라이언트 픽스처"""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_user_token():
    """모의 사용자 토큰"""
    return {
        "user_id": 1,
        "email": "test@example.com",
        "is_admin": False
    }


@pytest.fixture
def mock_admin_token():
    """모의 관리자 토큰"""
    return {
        "user_id": 99,
        "email": "admin@example.com", 
        "is_admin": True
    }


class TestPointRoutes:
    """포인트 라우터 테스트"""

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_get_my_balance(self, mock_verify_token, client, mock_user_token):
        """내 포인트 잔액 조회 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        mock_balance = {"balance": 1000}
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.get_user_balance.return_value = mock_balance
            
            # When
            response = client.get(
                "/api/v1/points/balance",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["balance"] == 1000

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_get_my_ledger(self, mock_verify_token, client, mock_user_token):
        """내 포인트 거래 내역 조회 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        mock_ledger = {
            "balance": 1000,
            "entries": [
                {
                    "id": 1,
                    "transaction_type": "CREDIT",
                    "delta_points": 100,
                    "balance_after": 1000,
                    "reason": "Test reward",
                    "ref_id": "test_ref_1",
                    "created_at": "2024-01-01 12:00:00"
                }
            ],
            "total_count": 1,
            "has_next": False
        }
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.get_user_ledger.return_value = mock_ledger
            
            # When
            response = client.get(
                "/api/v1/points/ledger",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["balance"] == 1000
            assert len(data["entries"]) == 1
            assert data["entries"][0]["delta_points"] == 100

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_get_ledger_by_date_range(self, mock_verify_token, client, mock_user_token):
        """날짜 범위별 거래 내역 조회 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        mock_transactions = [
            {
                "id": 1,
                "transaction_type": "CREDIT",
                "delta_points": 100,
                "balance_after": 1000,
                "reason": "Test reward",
                "ref_id": "test_ref_1",
                "created_at": "2024-01-01 12:00:00"
            }
        ]
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.get_transactions_by_date_range.return_value = mock_transactions
            
            # When
            response = client.get(
                "/api/v1/points/ledger/date-range?start_date=2024-01-01&end_date=2024-01-31",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["delta_points"] == 100

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_get_points_earned_today(self, mock_verify_token, client, mock_user_token):
        """특정일 획득 포인트 조회 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.get_user_points_earned_today.return_value = 200
            
            # When
            response = client.get(
                "/api/v1/points/earned/2024-01-01",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["points_earned"] == 200
            assert data["trading_day"] == "2024-01-01"

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_verify_my_integrity(self, mock_verify_token, client, mock_user_token):
        """내 포인트 정합성 검증 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        mock_integrity = {
            "status": "OK",
            "user_id": 1,
            "calculated_balance": 1000,
            "recorded_balance": 1000,
            "entry_count": 5,
            "verified_at": "2024-01-01 12:00:00"
        }
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.verify_user_integrity.return_value = mock_integrity
            
            # When
            response = client.get(
                "/api/v1/points/integrity/my",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "OK"
            assert data["user_id"] == 1

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_admin_add_points(self, mock_verify_token, client, mock_admin_token):
        """관리자 포인트 추가 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_result = {
            "success": True,
            "transaction_id": 123,
            "delta_points": 100,
            "balance_after": 1100,
            "message": "Transaction completed successfully"
        }
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.add_points.return_value = mock_result
            
            # When
            response = client.post(
                "/api/v1/points/admin/add?user_id=1",
                json={
                    "amount": 100,
                    "reason": "Admin bonus",
                    "ref_id": "admin_bonus_1"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["delta_points"] == 100

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_admin_deduct_points(self, mock_verify_token, client, mock_admin_token):
        """관리자 포인트 차감 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_result = {
            "success": True,
            "transaction_id": 124,
            "delta_points": -50,
            "balance_after": 950,
            "message": "Transaction completed successfully"
        }
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.deduct_points.return_value = mock_result
            
            # When
            response = client.post(
                "/api/v1/points/admin/deduct?user_id=1",
                json={
                    "amount": 50,
                    "reason": "Admin penalty",
                    "ref_id": "admin_penalty_1"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["delta_points"] == -50

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_admin_adjust_points(self, mock_verify_token, client, mock_admin_token):
        """관리자 포인트 조정 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_result = {
            "success": True,
            "transaction_id": 125,
            "delta_points": 75,
            "balance_after": 1075,
            "message": "Transaction completed successfully"
        }
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.admin_adjust_points.return_value = mock_result
            
            # When
            response = client.post(
                "/api/v1/points/admin/adjust",
                json={
                    "user_id": 1,
                    "amount": 75,
                    "reason": "Manual adjustment"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["delta_points"] == 75

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_non_admin_cannot_add_points(self, mock_verify_token, client, mock_user_token):
        """일반 사용자의 포인트 추가 권한 없음 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        
        # When
        response = client.post(
            "/api/v1/points/admin/add?user_id=1",
            json={
                "amount": 100,
                "reason": "Test bonus",
                "ref_id": "test_bonus_1"
            },
            headers={"Authorization": "Bearer user_token"}
        )
        
        # Then
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_admin_get_user_balance(self, mock_verify_token, client, mock_admin_token):
        """관리자 사용자 잔액 조회 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_balance = {"balance": 1500}
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.get_user_balance.return_value = mock_balance
            
            # When
            response = client.get(
                "/api/v1/points/admin/balance/1",
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["balance"] == 1500

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_admin_verify_global_integrity(self, mock_verify_token, client, mock_admin_token):
        """관리자 전체 정합성 검증 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_global_integrity = {
            "status": "OK",
            "total_balance_from_latest": 50000,
            "total_deltas": 50000,
            "user_count": 100,
            "total_entries": 1000,
            "verified_at": "2024-01-01 12:00:00"
        }
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.verify_global_integrity.return_value = mock_global_integrity
            
            # When
            response = client.get(
                "/api/v1/points/admin/integrity/global",
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "OK"
            assert data["user_count"] == 100

    @patch("myapi.routers.point_router.verify_bearer_token")
    def test_check_user_affordability(self, mock_verify_token, client, mock_admin_token):
        """사용자 지불 능력 확인 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_balance = {"balance": 1000}
        
        with patch("myapi.containers.Container.services.point_service") as mock_service:
            mock_service.return_value.can_afford.return_value = True
            mock_service.return_value.get_user_balance.return_value = mock_balance
            
            # When
            response = client.get(
                "/api/v1/points/admin/check-affordability/1/500",
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["can_afford"] is True
            assert data["amount"] == 500
            assert data["current_balance"] == 1000
            assert data["shortfall"] == 0