# Lambda CloudWatch 로그 그룹
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-lambda"
  retention_in_days = 7
  
  tags = local.common_tags
}

# Lambda Function
# resource "aws_lambda_function" "api" {
#   function_name = "${var.project_name}-lambda"
#   role          = aws_iam_role.lambda_execution_role.arn
  
#   package_type = "Image"
#   image_uri    = "${aws_ecr_repository.lambda.repository_url}:latest"
  
#   timeout     = 30
#   memory_size = 1024
  
#   environment {
#     variables = {
#       ENVIRONMENT     = "production"
#       DEPLOYMENT_TYPE = "lambda"
#     }
#   }
  
#   depends_on = [
#     aws_iam_role_policy_attachment.lambda_basic_execution,
#     aws_cloudwatch_log_group.lambda
#   ]
  
#   tags = local.common_tags
# }

# Lambda Function URL (HTTP API 엔드포인트)
# resource "aws_lambda_function_url" "api" {
#   function_name      = aws_lambda_function.api.function_name
#   authorization_type = "NONE"
  
#   cors {
#     allow_credentials = false
#     allow_methods     = ["*"]
#     allow_origins     = ["*"]
#     allow_headers     = ["date", "keep-alive"]
#     expose_headers    = ["date", "keep-alive"]
#     max_age          = 86400
#   }
# }