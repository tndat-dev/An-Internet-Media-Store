#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for binary in git helm kubectl; do
  command -v "$binary" >/dev/null || {
    printf 'Missing required command: %s\n' "$binary" >&2
    exit 1
  }
done

helm repo add argo https://argoproj.github.io/argo-helm --force-update
helm repo update argo

helm upgrade --install argocd argo/argo-cd --version 10.2.1 \
  --namespace argocd --create-namespace \
  -f "$root/platform/argocd-values.yaml" --history-max 10 \
  --force-conflicts

helm upgrade --install argo-rollouts argo/argo-rollouts --version 2.41.1 \
  --namespace argo-rollouts --create-namespace \
  -f "$root/platform/argo-rollouts-values.yaml" --history-max 10 \
  --force-conflicts

kubectl -n argocd rollout status deployment/argocd-server --timeout=5m
kubectl -n argocd rollout status deployment/argocd-repo-server --timeout=5m
kubectl -n argo-rollouts rollout status deployment/argo-rollouts --timeout=5m

if [[ "${ENABLE_AIMS_GITOPS:-false}" == "true" ]]; then
  repo_url="$(kubectl create --dry-run=client -f "$root/platform/argocd-application.yaml" -o jsonpath='{.spec.source.repoURL}')"
  revision="$(kubectl create --dry-run=client -f "$root/platform/argocd-application.yaml" -o jsonpath='{.spec.source.targetRevision}')"
  checkout_dir="$(mktemp -d)"
  trap 'rm -rf -- "$checkout_dir"' EXIT
  git clone --quiet --depth 1 --branch "$revision" "$repo_url" "$checkout_dir"
  [[ -f "$checkout_dir/Programming/k8s/aims-chart/Chart.yaml" ]] || {
    printf 'AIMS chart is absent from %s@%s; refusing to enable automated prune.\n' "$repo_url" "$revision" >&2
    exit 1
  }
  kubectl apply --server-side --force-conflicts -f "$root/platform/argocd-application.yaml"
else
  printf '%s\n' 'Controllers installed; AIMS Application left disabled.'
  printf '%s\n' 'After deployment code is committed/pushed, run with ENABLE_AIMS_GITOPS=true.'
fi
