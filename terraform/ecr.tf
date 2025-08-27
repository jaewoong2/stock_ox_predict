# ECR Repository for ECS
resource "aws_ecr_repository" "fastapi" {
  name                 = "${var.project_name}-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# ECR Repository for Lambda
resource "aws_ecr_repository" "lambda" {
  name                 = "${var.project_name}-lambda"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# ECR Lifecycle Policy for ECS
resource "aws_ecr_lifecycle_policy" "fastapi" {
  repository = aws_ecr_repository.fastapi.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the latest 10 images"
        selection = {
          tagStatus = "any"
          countType = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ECR Lifecycle Policy for Lambda
resource "aws_ecr_lifecycle_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the latest 10 images"
        selection = {
          tagStatus = "any"
          countType = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
