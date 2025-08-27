# 출력 값
output "ecr_repository_url" {
  description = "ECR repository URL for ECS"
  value       = aws_ecr_repository.fastapi.repository_url
}

output "ecr_lambda_repository_url" {
  description = "ECR repository URL for Lambda"
  value       = aws_ecr_repository.lambda.repository_url
}

output "load_balancer_dns_name" {
  description = "Load balancer DNS name (existing ALB)"
  value       = data.aws_lb.existing.dns_name
}

output "domain_url" {
  description = "Domain URL"
  value       = "https://${var.domain_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.fastapi.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.fastapi.name
}

output "existing_alb_arn" {
  description = "Existing ALB ARN"
  value       = data.aws_lb.existing.arn
}

output "fastapi_target_group_arn" {
  description = "FastAPI target group ARN"
  value       = aws_lb_target_group.fastapi.arn
}

# output "lambda_function_name" {
#   description = "Lambda function name"
#   value       = aws_lambda_function.api.function_name
# }

# output "lambda_function_url" {
#   description = "Lambda function URL"
#   value       = aws_lambda_function_url.api.function_url
# }
