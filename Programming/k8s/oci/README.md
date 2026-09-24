# AIMS trên OKE `oe01-oke-development`

Thư mục này là desired state riêng cho OKE trên OCI. Không apply trực tiếp bộ
manifest `Programming/k8s/platform` của cluster kubeadm cũ vì bộ đó phụ thuộc
Istio Ambient, Vault, Longhorn, MinIO, RabbitMQ, OpenSearch, gVisor và profile
được cài trực tiếp lên node.

## Thứ tự triển khai

1. `00-namespaces.yaml`
2. `01-storageclass.yaml`
3. CloudNativePG operator chart `0.29.0` (app `1.30.0`)
4. Strimzi operator chart `1.2.0`
5. `10-postgresql.yaml`: PostgreSQL HA, 3 instance × 50 GiB
6. `20-kafka-cluster.yaml`: Kafka KRaft, 3 broker/controller × 50 GiB
7. `21-kafka-resources.yaml`: TLS user và các topic AIMS ban đầu
8. AIMS runtime secrets và database bootstrap
9. AIMS Helm chart đã điều chỉnh cho namespace `aims`
10. ingress-nginx chart `4.15.1`, dùng `31-ingress-nginx-values.yaml`
11. `32-aims-ingress.yaml`
12. Private LB `10.1.2.145` → ba worker port `32080`
13. Public LB `140.245.85.157` → private LB port `80`
14. Regional WAF `aims-public-waf` ở chế độ phát hiện (`CHECK`)
15. `40-data-science-workspace.yaml`: namespace, quota và RBAC cho `chulinh`
16. `41-data-science-kafka.yaml`: Kafka mTLS user và ba topic `ds.*`

Trạng thái xác nhận ngày 23/09/2026: ba node Ready; 11 Deployment AIMS đều
2/2; PostgreSQL 3/3; Kafka KRaft 3/3; hai LB Healthy. Auth dùng PostgreSQL
trực tiếp, không cần Keycloak; catalog và inventory đã có 12 sản phẩm demo.
Data Science dùng chung cụm trong namespace `data-science`; Kafka user/topic
được tách khỏi AIMS bằng certificate và ACL riêng.

Hướng dẫn cho user mới: [36_RUNBOOK.md](../../../docs/oci/36_RUNBOOK.md).
Endpoint lab hiện tại:

```text
http://140.245.85.157/
http://140.245.85.157/api/products/
```

Đây là endpoint HTTP tạm. Cần domain, certificate, listener HTTPS và redirect
trước khi dùng như endpoint production. WAF đang detect SQLi, XSS, LFI/path
traversal, Unix command injection và scanner User-Agent; giữ chế độ `CHECK`
cho tới khi đã rà false positive trong OCI Logging.

Kubeconfig local:

```bash
export KUBECONFIG="$HOME/.kube/oe01-oke-development"
kubectl get nodes -o wide
```

Kubernetes API là private. Khi thao tác từ laptop, phiên OCI Bastion và SSH
port-forward tới `127.0.0.1:26443` phải còn chạy. Khi thao tác trong OCI Cloud
Shell, gắn Cloud Shell vào `oe01-vcn/sn-oke-bastion` và dùng kubeconfig private
do **Access Cluster** sinh ra.

Source code không được copy lên worker. OKE pull image theo digest từ GHCR;
manifest/Helm chart trong repo là desired state, còn runtime secret được tạo
ngoài Git từ file local và không được ghi giá trị vào tài liệu.

## Auth và dữ liệu demo

`auth-service` sở hữu schema `auth_service` trong PostgreSQL. Mật khẩu được
băm bằng scrypt; database chỉ giữ SHA-256 của token đăng nhập. Người dùng tự
đăng ký tại `/register`, sau đó có thể đăng nhập bằng username hoặc email.

Seed catalog và inventory theo đúng thứ tự sau. Script dùng UUID cố định và
upsert nên có thể chạy lại:

```bash
export KUBECONFIG="$HOME/.kube/oe01-oke-development"
CATALOG_POD=$(kubectl -n aims get pod \
  -l app.kubernetes.io/name=catalog-service \
  -o jsonpath='{.items[0].metadata.name}')
kubectl -n aims cp Programming/k8s/oci/seed_catalog.py \
  "$CATALOG_POD:/tmp/seed_catalog.py"
kubectl -n aims exec "$CATALOG_POD" -- \
  python /tmp/seed_catalog.py catalog

INVENTORY_POD=$(kubectl -n aims get pod \
  -l app.kubernetes.io/name=inventory-service \
  -o jsonpath='{.items[0].metadata.name}')
kubectl -n aims cp Programming/k8s/oci/seed_catalog.py \
  "$INVENTORY_POD:/tmp/seed_catalog.py"
kubectl -n aims exec "$INVENTORY_POD" -- \
  python /tmp/seed_catalog.py inventory
```

Checkpoint:

```bash
curl -fsS http://140.245.85.157/api/products/
kubectl -n aims rollout status deployment/auth-service
```
