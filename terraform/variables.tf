variable "cluster_name" {
  type    = string
  default = "autoscale-lab"
}

variable "worker_count" {
  type    = number
  default = 2
}

variable "keda_chart_version" {
  type    = string
  default = "2.14.0"
}

variable "prometheus_stack_chart_version" {
  type    = string
  default = "58.2.2"
}

variable "enable_grafana" {
  type    = bool
  default = true
}

variable "grafana_admin_password" {
  type        = string
  default     = "admin"
  sensitive   = true
  description = "Local lab only; Grafana is reachable through port-forward."
}

variable "app_image" {
  type    = string
  default = "demo-app:1.0"
}

variable "k6_image" {
  type    = string
  default = "grafana/k6:0.52.0"
}
