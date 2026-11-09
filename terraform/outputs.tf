output "cluster_name" {
  value = kind_cluster.this.name
}

output "kubectl_context" {
  value = "kind-${kind_cluster.this.name}"
}

output "next_step" {
  value = "kind export kubeconfig --name ${kind_cluster.this.name}; then: python scripts/run_experiment.py"
}
