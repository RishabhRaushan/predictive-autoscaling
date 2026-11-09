output "image" {
  value = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
}

output "update_kubeconfig" {
  value = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}"
}
