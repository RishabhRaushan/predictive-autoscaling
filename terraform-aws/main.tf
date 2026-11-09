provider "aws" {
  region = var.region

  default_tags {
    tags = var.tags
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

# Public subnets only: no NAT gateway, which keeps the lab cheap. Nodes get public IPs.
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name                    = var.cluster_name
  cidr                    = "10.0.0.0/16"
  azs                     = local.azs
  public_subnets          = ["10.0.0.0/20", "10.0.16.0/20"]
  enable_nat_gateway      = false
  map_public_ip_on_launch = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.8"

  cluster_name                             = var.cluster_name
  cluster_version                          = var.kubernetes_version
  vpc_id                                   = module.vpc.vpc_id
  subnet_ids                               = module.vpc.public_subnets
  cluster_endpoint_public_access           = true
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      min_size       = var.node_count
      max_size       = var.node_count
      desired_size   = var.node_count
    }
  }
}

resource "aws_ecr_repository" "app" {
  name         = "${var.cluster_name}/demo-app"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Build for linux/amd64 so the image runs on the x86 nodes even when built on an ARM laptop.
resource "null_resource" "app_image" {
  triggers = {
    repo   = aws_ecr_repository.app.repository_url
    tag    = var.image_tag
    source = sha1(join("", [for f in sort(fileset("${path.module}/../app", "*")) : filesha1("${path.module}/../app/${f}")]))
  }

  provisioner "local-exec" {
    command = "aws ecr get-login-password --region ${var.region} | docker login --username AWS --password-stdin ${split("/", aws_ecr_repository.app.repository_url)[0]} && docker build --platform linux/amd64 -t ${aws_ecr_repository.app.repository_url}:${var.image_tag} \"${path.module}/../app\" && docker push ${aws_ecr_repository.app.repository_url}:${var.image_tag}"
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}

resource "helm_release" "keda" {
  name             = "keda"
  namespace        = "keda"
  create_namespace = true
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = var.keda_chart_version
  wait             = true
  timeout          = 600

  depends_on = [module.eks]
}

# Release name must stay "kube-prometheus-stack": the ScaledObject points at its Prometheus service.
resource "helm_release" "prometheus_stack" {
  name             = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = true
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = var.prometheus_stack_chart_version
  wait             = true
  timeout          = 900

  values = [yamlencode({
    defaultRules          = { create = false }
    alertmanager          = { enabled = false }
    nodeExporter          = { enabled = false }
    kubeEtcd              = { enabled = false }
    kubeScheduler         = { enabled = false }
    kubeControllerManager = { enabled = false }
    kubeProxy             = { enabled = false }
    grafana = {
      enabled       = var.enable_grafana
      adminPassword = var.grafana_admin_password
    }
    prometheus = {
      prometheusSpec = {
        retention                               = "6h"
        serviceMonitorSelectorNilUsesHelmValues = false
        podMonitorSelectorNilUsesHelmValues     = false
      }
    }
  })]

  depends_on = [module.eks]
}
