#!/bin/bash

# Trading Day Validation API Test Script
# Tests the /prices/trading-day-summary endpoint with various dates

echo "=========================================="
echo "Trading Day Validation API Tests"
echo "=========================================="
echo ""

# Base URL (update if needed)
BASE_URL="http://localhost:8000/api/v1"

# You need to replace this with a valid auth token
# Get token by logging in first
AUTH_TOKEN="your_auth_token_here"

echo "Prerequisites:"
echo "1. Server must be running: uvicorn myapi.main:app --reload"
echo "2. Replace AUTH_TOKEN in this script with valid token"
echo "3. Ensure database has data for testing"
echo ""
echo "=========================================="
echo ""

# Test 1: Thanksgiving (should return 422)
echo "Test 1: Thanksgiving 2025-11-27 (Should return 422)"
echo "Request: GET /prices/trading-day-summary?trading_day=2025-11-27"
curl -X GET "$BASE_URL/prices/trading-day-summary?trading_day=2025-11-27" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""
echo "Expected: HTTP 422 with error code 'NON_TRADING_DAY' and next_trading_day='2025-11-28'"
echo "=========================================="
echo ""

# Test 2: Normal trading day (should return 200)
echo "Test 2: Friday 2025-11-28 (Should return 200)"
echo "Request: GET /prices/trading-day-summary?trading_day=2025-11-28"
curl -X GET "$BASE_URL/prices/trading-day-summary?trading_day=2025-11-28" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""
echo "Expected: HTTP 200 with trading day data"
echo "=========================================="
echo ""

# Test 3: Weekend Saturday (should return 422)
echo "Test 3: Saturday 2025-11-29 (Should return 422)"
echo "Request: GET /prices/trading-day-summary?trading_day=2025-11-29"
curl -X GET "$BASE_URL/prices/trading-day-summary?trading_day=2025-11-29" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""
echo "Expected: HTTP 422 with day_type='weekend' and next_trading_day='2025-12-01'"
echo "=========================================="
echo ""

# Test 4: Weekend Sunday (should return 422)
echo "Test 4: Sunday 2025-11-30 (Should return 422)"
echo "Request: GET /prices/trading-day-summary?trading_day=2025-11-30"
curl -X GET "$BASE_URL/prices/trading-day-summary?trading_day=2025-11-30" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""
echo "Expected: HTTP 422 with day_type='weekend' and next_trading_day='2025-12-01'"
echo "=========================================="
echo ""

# Test 5: Invalid date format (should return 422)
echo "Test 5: Invalid date format (Should return 422)"
echo "Request: GET /prices/trading-day-summary?trading_day=invalid-date"
curl -X GET "$BASE_URL/prices/trading-day-summary?trading_day=invalid-date" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""
echo "Expected: HTTP 422 with day_type='invalid_format'"
echo "=========================================="
echo ""

# Test 6: No date parameter (should use current KST trading day)
echo "Test 6: No date parameter (Should use current KST trading day)"
echo "Request: GET /prices/trading-day-summary"
curl -X GET "$BASE_URL/prices/trading-day-summary" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""
echo "Expected: Depends on current date - 200 if trading day, 422 if holiday/weekend"
echo "=========================================="
echo ""

echo "All tests completed!"
echo ""
echo "To run this script:"
echo "1. chmod +x test_trading_day_api.sh"
echo "2. Edit script to add your AUTH_TOKEN"
echo "3. ./test_trading_day_api.sh"
