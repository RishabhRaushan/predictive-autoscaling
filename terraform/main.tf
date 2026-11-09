resource "kind_cluster" "this" {
  name           = var.cluster_name
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
    }

    dynamic "node" {
      for_each = range(var.worker_count)
      content {
        role = "worker"
      }
    }
  }
}

provider "helm" {
  kubernetes {
    host                   = kind_cluster.this.endpoint
    cluster_ca_certificate = kind_cluster.this.cluster_ca_certificate
    client_certificate     = kind_cluster.this.client_certificate
    client_key             = kind_cluster.this.client_key
  }
}

# Images are loaded straight into the kind nodes so pods start without a registry pull.
resource "null_resource" "app_image" {
  triggers = {
    cluster = kind_cluster.this.id
    source  = sha1(join("", [for f in sort(fileset("${path.module}/../app", "*")) : filesha1("${path.module}/../app/${f}")]))
  }

  provisioner "local-exec" {
    command = "docker build -t ${var.app_image} \"${path.module}/../app\" && kind load docker-image ${var.app_image} --name ${var.cluster_name}"
  }
}

resource "null_resource" "k6_image" {
  triggers = {
    cluster = kind_cluster.this.id
    image   = var.k6_image
  }

  provisioner "local-exec" {
    command = "docker pull ${var.k6_image} && kind load docker-image ${var.k6_image} --name ${var.cluster_name}"
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

  depends_on = [kind_cluster.this]
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
    defaultRules       = { create = false }
    alertmanager       = { enabled = false }
    nodeExporter       = { enabled = false }
    kubeEtcd           = { enabled = false }
    kubeScheduler      = { enabled = false }
    kubeControllerManager = { enabled = false }
    kubeProxy          = { enabled = false }
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

  depends_on = [kind_cluster.this]
}
