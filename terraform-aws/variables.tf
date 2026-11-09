variable "region" {
  type    = string
  default = "us-east-1"
}

variable "cluster_name" {
  type    = string
  default = "autoscale-lab"
}

variable "kubernetes_version" {
  type    = string
  default = "1.30"
}

variable "node_instance_type" {
  type    = string
  default = "t3.large"
}

variable "node_count" {
  type        = number
  default     = 3
  description = "Fixed node count; the lab scales pods, not nodes, so cost stays predictable."
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
  default = false
}

variable "grafana_admin_password" {
  type        = string
  default     = null
  sensitive   = true
  description = "Required only when enable_grafana is true."
}

variable "image_tag" {
  type    = string
  default = "1.0"
}

variable "tags" {
  type    = map(string)
  default = { project = "predictive-autoscaling" }
}
