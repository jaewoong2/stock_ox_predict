import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
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


class TestRewardRoutes:
    """리워드 라우터 테스트"""

    @patch("myapi.routers.reward_router.verify_bearer_token")
    def test_get_reward_catalog(self, mock_verify_token, client):
        """리워드 카탈로그 조회 테스트"""
        # Given
        mock_catalog = {
            "rewards": [
                {
                    "sku": "TEST001",
                    "title": "Test Reward",
                    "cost_points": 100,
                    "stock": 10,
                    "vendor": "Test Vendor",
                    "is_available": True,
                    "description": None,
                    "image_url": None
                }
            ],
            "total_count": 1
        }
        
        with patch("myapi.containers.Container.services.reward_service") as mock_service:
            mock_service.return_value.get_reward_catalog.return_value = mock_catalog
            
            # When
            response = client.get("/api/v1/rewards/catalog")
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert "rewards" in data
            assert "total_count" in data
            assert data["total_count"] == 1

    @patch("myapi.routers.reward_router.verify_bearer_token")
    def test_get_reward_by_sku(self, mock_verify_token, client):
        """SKU로 리워드 조회 테스트"""
        # Given
        mock_reward = {
            "sku": "TEST001",
            "title": "Test Reward",
            "cost_points": 100,
            "stock": 10,
            "vendor": "Test Vendor",
            "is_available": True,
            "description": None,
            "image_url": None
        }
        
        with patch("myapi.containers.Container.services.reward_service") as mock_service:
            mock_service.return_value.get_reward_by_sku.return_value = mock_reward
            
            # When
            response = client.get("/api/v1/rewards/catalog/TEST001")
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["sku"] == "TEST001"
            assert data["title"] == "Test Reward"

    @patch("myapi.routers.reward_router.verify_bearer_token")
    def test_redeem_reward_success(self, mock_verify_token, client, mock_user_token):
        """리워드 교환 성공 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        mock_redemption_result = {
            "success": True,
            "redemption_id": "123",
            "status": "RESERVED",
            "message": "Redemption successful",
            "cost_points": 100,
            "issued_at": "2024-01-01 12:00:00"
        }
        
        with patch("myapi.containers.Container.services.reward_service") as mock_service:
            mock_service.return_value.redeem_reward.return_value = mock_redemption_result
            
            # When
            response = client.post(
                "/api/v1/rewards/redeem",
                json={"sku": "TEST001", "delivery_info": {}},
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["redemption_id"] == "123"

    @patch("myapi.routers.reward_router.verify_bearer_token")
    def test_get_my_redemption_history(self, mock_verify_token, client, mock_user_token):
        """내 교환 내역 조회 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        mock_history = {
            "history": [
                {
                    "redemption_id": "123",
                    "sku": "TEST001",
                    "title": "Test Reward",
                    "cost_points": 100,
                    "status": "ISSUED",
                    "requested_at": "2024-01-01 12:00:00",
                    "issued_at": "2024-01-01 13:00:00",
                    "vendor": "Test Vendor"
                }
            ],
            "total_count": 1,
            "has_next": False
        }
        
        with patch("myapi.containers.Container.services.reward_service") as mock_service:
            mock_service.return_value.get_user_redemption_history.return_value = mock_history
            
            # When
            response = client.get(
                "/api/v1/rewards/my-redemptions",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert "history" in data
            assert data["total_count"] == 1

    @patch("myapi.routers.reward_router.verify_bearer_token")
    def test_create_reward_item_admin_only(self, mock_verify_token, client, mock_admin_token):
        """관리자 전용 리워드 생성 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_created_reward = {
            "sku": "NEW001",
            "title": "New Test Reward",
            "cost_points": 200,
            "stock": 5,
            "reserved": 0,
            "vendor": "Test Vendor",
            "available_stock": 5,
            "created_at": "2024-01-01 12:00:00",
            "updated_at": "2024-01-01 12:00:00"
        }
        
        with patch("myapi.containers.Container.services.reward_service") as mock_service:
            mock_service.return_value.create_reward_item.return_value = mock_created_reward
            
            # When
            response = client.post(
                "/api/v1/rewards/admin/items",
                json={
                    "sku": "NEW001",
                    "title": "New Test Reward",
                    "cost_points": 200,
                    "stock": 5,
                    "vendor": "Test Vendor"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["sku"] == "NEW001"

    @patch("myapi.routers.reward_router.verify_bearer_token")
    def test_non_admin_cannot_create_reward(self, mock_verify_token, client, mock_user_token):
        """일반 사용자의 리워드 생성 권한 없음 테스트"""
        # Given
        mock_verify_token.return_value = mock_user_token
        
        # When
        response = client.post(
            "/api/v1/rewards/admin/items",
            json={
                "sku": "NEW001",
                "title": "New Test Reward",
                "cost_points": 200,
                "stock": 5,
                "vendor": "Test Vendor"
            },
            headers={"Authorization": "Bearer user_token"}
        )
        
        # Then
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    @patch("myapi.routers.reward_router.verify_bearer_token")
    def test_get_admin_stats(self, mock_verify_token, client, mock_admin_token):
        """관리자 통계 조회 테스트"""
        # Given
        mock_verify_token.return_value = mock_admin_token
        mock_stats = {
            "inventory": {
                "total_items": 5,
                "total_stock": 100,
                "total_reserved": 10,
                "available_stock": 90
            },
            "redemptions": {
                "total_redemptions": 20,
                "issued_redemptions": 15,
                "pending_redemptions": 3,
                "failed_redemptions": 2,
                "total_points_spent": 2000
            }
        }
        
        with patch("myapi.containers.Container.services.reward_service") as mock_service:
            mock_service.return_value.get_inventory_summary.return_value = mock_stats["inventory"]
            mock_service.return_value.get_redemption_stats.return_value = mock_stats["redemptions"]
            
            # When
            response = client.get(
                "/api/v1/rewards/admin/stats",
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Then
            assert response.status_code == 200
            data = response.json()
            assert "inventory" in data
            assert "redemptions" in data
            assert data["inventory"]["total_items"] == 5