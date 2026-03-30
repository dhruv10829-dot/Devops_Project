# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "application" {
  name              = "/aws/ecs/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.name_prefix}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "log"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          logs = [
            {
              logGroupName = aws_cloudwatch_log_group.application.name
              title        = "Application Logs"
              view         = "Table"
            }
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 6
        height = 6

        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ServiceName", aws_ecs_service.app.name],
            [".", "MemoryUtilization", ".", "."],
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.app[0].arn_suffix],
            [".", "TargetResponseTime", ".", "."]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "Service Metrics"
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 6
        width  = 6
        height = 6

        properties = {
          metrics = [
            ["ML/CICD/Predictor", "PredictionCount", "Environment", var.environment],
            [".", "PredictionLatency", ".", "."],
            [".", "FailureRate", ".", "."],
            [".", "CacheHitRate", ".", "."]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "ML Prediction Metrics"
        }
      },
      {
        type   = "alarm"
        x      = 0
        y      = 12
        width  = 12
        height = 6

        properties = {
          alarms = [
            aws_cloudwatch_metric_alarm.high_error_rate.arn,
            aws_cloudwatch_metric_alarm.high_latency.arn,
            aws_cloudwatch_metric_alarm.low_health.arn
          ]
        }
      }
    ]
  })
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  alarm_name          = "${local.name_prefix}-high-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    LoadBalancer = aws_lb.app[0].arn_suffix
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "high_latency" {
  alarm_name          = "${local.name_prefix}-high-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = "300"
  statistic           = "Average"
  threshold           = "5"

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    LoadBalancer = aws_lb.app[0].arn_suffix
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "low_health" {
  alarm_name          = "${local.name_prefix}-low-health"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "5"
  metric_name         = "HTTPCode_Target_2XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Sum"
  threshold           = "5"

  treat_missing_data = "breaching"

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    LoadBalancer = aws_lb.app[0].arn_suffix
  }

  tags = local.common_tags
}

# Custom Metrics for ML Predictions
resource "aws_cloudwatch_log_metric_filter" "prediction_count" {
  name           = "${local.name_prefix}-prediction-count"
  log_group_name = aws_cloudwatch_log_group.application.name

  pattern = "[timestamp=* level=INFO, prediction=*]"

  metric_transformation {
    name      = "PredictionCount"
    namespace = "ML/CICD/Predictor"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "prediction_latency" {
  name           = "${local.name_prefix}-prediction-latency"
  log_group_name = aws_cloudwatch_log_group.application.name

  pattern = "[timestamp=* latency=*]"

  metric_transformation {
    name      = "PredictionLatency"
    namespace = "ML/CICD/Predictor"
    value     = "$latency"
  }
}

# SNS Topic for Alarms (optional)
resource "aws_sns_topic" "alarms" {
  count = var.enable_alarm_sns ? 1 : 0

  name = "${local.name_prefix}-alarms"

  tags = local.common_tags
}

resource "aws_sns_topic_subscription" "email" {
  count = var.enable_alarm_sns && var.alarm_email != null ? 1 : 0

  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}
