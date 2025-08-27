#!/bin/bash

# 색깔 설정
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 로깅 함수
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# 필요한 변수 설정
AWS_REGION="ap-northeast-2"
AWS_PROFILE="lime_admin"
PROJECT_NAME="ox-universe"
ECR_REPOSITORY_NAME="${PROJECT_NAME}-lambda"
LAMBDA_FUNCTION_NAME="${PROJECT_NAME}-lambda"

# AWS 계정 ID 가져오기
log "Getting AWS Account ID..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile $AWS_PROFILE)
if [ $? -ne 0 ]; then
    error "Failed to get AWS Account ID"
fi

ECR_REPOSITORY="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY_NAME"
IMAGE_NAME="$ECR_REPOSITORY:latest"

log "Starting Lambda deployment process for $LAMBDA_FUNCTION_NAME..."
log "ECR Repository: $ECR_REPOSITORY"

# AWS ECR 로그인
log "Logging in to AWS ECR..."
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | docker login --username AWS --password-stdin $ECR_REPOSITORY
if [ $? -ne 0 ]; then
    error "Failed to login to ECR"
fi

# Docker 이미지 빌드 (docker-compose 사용)
log "Building Docker image using docker-compose..."
docker-compose build ox-universe
if [ $? -ne 0 ]; then
    error "Failed to build Docker image with docker-compose"
fi

# 이미지에 태그 추가
log "Tagging Docker image..."
docker tag ox-universe-lambda:latest $IMAGE_NAME
if [ $? -ne 0 ]; then
    error "Failed to tag Docker image"
fi

# ECR로 푸쉬
log "Pushing Docker image to ECR..."
docker push $IMAGE_NAME
if [ $? -ne 0 ]; then
    error "Failed to push Docker image to ECR"
fi

# Lambda 함수 코드 업데이트
log "Updating Lambda function code..."
aws lambda update-function-code --function-name $LAMBDA_FUNCTION_NAME --image-uri $IMAGE_NAME --region $AWS_REGION --profile $AWS_PROFILE
if [ $? -ne 0 ]; then
    error "Failed to update Lambda function"
fi

log "Docker image $IMAGE_NAME has been pushed to ECR and Lambda function $LAMBDA_FUNCTION_NAME has been updated."
log "Deployment process completed!"