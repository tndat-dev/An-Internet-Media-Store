# Triển khai AIMS microservices với Kafka, Jenkins, Argo CD và PostgreSQL

Tài liệu này là runbook độc lập để triển khai AIMS lên một Kubernetes cluster
khác khi tầng nền tảng ứng dụng chỉ có Kafka, Jenkins, Argo CD và PostgreSQL.
OCI image được lưu tại GHCR vì Kubernetes vẫn cần một registry để phân phối
image cho các node; GHCR là dịch vụ ngoài cluster, không phải một workload nền
tảng bổ sung.

## 1. Phạm vi và giả định

Cluster tối thiểu phải có Kubernetes hoạt động, CNI, CoreDNS, StorageClass mặc
định, Ingress/Gateway hoặc LoadBalancer, `kubectl` và `helm`. Bốn thành phần
được triển khai trong cluster là:

- Strimzi Kafka ở KRaft mode, không có ZooKeeper;
- CloudNativePG hoặc PostgreSQL HA tương đương;
- Jenkins với Kubernetes ephemeral agents;
- Argo CD làm GitOps/CD duy nhất.

Không sử dụng Redis, RabbitMQ, Keycloak, OpenSearch, Vault, service mesh hoặc
observability stack. Secret được tạo bằng Kubernetes Secret trong lab và phải
được thay bằng secret manager khi chuyển sang production.

## 2. Kiến trúc mục tiêu

```text
Developer → GitHub → Jenkins CI → GHCR
                 │                   │
                 └─ GitOps manifests ┘
                           ↓
                        Argo CD
                           ↓
                     namespace aims

Client → api-gateway
          ├─ auth-service
          ├─ catalog-service
          ├─ cart-service
          ├─ order-service
          ├─ payment-service
          ├─ inventory-service
          ├─ notification-service
          ├─ search-recommendation-service
          └─ security-telemetry-service

Services → PostgreSQL databases riêng
Services ↔ Kafka event/command/retry/DLQ topics
```

### 2.1 Ranh giới mười service

| Service | Sở hữu nghiệp vụ | Database |
|---|---|---|
| `api-gateway` | Routing, JWT validation, rate limit mức ứng dụng | Không |
| `auth-service` | User, password hash, refresh token, role | `aims_auth` |
| `catalog-service` | Product, category, price, media URL | `aims_catalog` |
| `cart-service` | Cart và cart item; thay Redis bằng Postgres | `aims_cart` |
| `order-service` | Order, order line và trạng thái saga | `aims_order` |
| `payment-service` | Payment attempt, idempotency và refund | `aims_payment` |
| `inventory-service` | Stock, reservation và release | `aims_inventory` |
| `notification-service` | Notification, delivery attempt | `aims_notification` |
| `search-recommendation-service` | PostgreSQL FTS, `pg_trgm`, ranking/gợi ý | `aims_search` |
| `security-telemetry-service` | Audit event và detection result | `aims_security` |

Mỗi service có database/user riêng dù tất cả nằm trong cùng một PostgreSQL
cluster. Không service nào được truy vấn bảng thuộc service khác. Trao đổi dữ
liệu qua HTTP API có version hoặc Kafka event có version.

## 3. Kafka thay cả event backbone và task queue

Kafka giữ domain event lâu dài và thay RabbitMQ cho background task. Consumer
dùng consumer group, `enable.auto.commit=false`, chỉ commit sau khi transaction
local thành công. Tất cả handler phải idempotent theo `eventId`.

### 3.1 Topic chính

| Topic | Producer | Consumer |
|---|---|---|
| `aims.catalog.product-changed.v1` | catalog | search-recommendation |
| `aims.cart.checked-out.v1` | cart | order |
| `aims.order.created.v1` | order | inventory, telemetry |
| `aims.inventory.reserved.v1` | inventory | order, payment |
| `aims.inventory.rejected.v1` | inventory | order |
| `aims.payment.requested.v1` | order | payment |
| `aims.payment.completed.v1` | payment | order, notification, recommendation |
| `aims.payment.failed.v1` | payment | order, inventory, notification |
| `aims.notification.requested.v1` | order/payment | notification |
| `aims.security.telemetry.v1` | gateway/services | security-telemetry |

Mỗi task quan trọng có retry và dead-letter topic, ví dụ:

```text
aims.payment.requested.v1
aims.payment.retry-1m.v1
aims.payment.retry-10m.v1
aims.payment.dlq.v1
```

Kafka không có delayed queue nguyên bản. Consumer retry ghi `nextAttemptAt` rồi
retry worker chỉ chuyển message về topic chính khi đến hạn. Giới hạn số lần thử
và chuyển DLQ sau ngưỡng. Không retry vô hạn.

### 3.2 Event envelope chuẩn

```json
{
  "eventId": "uuid",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "occurredAt": "2026-09-09T10:00:00Z",
  "producer": "order-service",
  "aggregateId": "order-uuid",
  "correlationId": "checkout-uuid",
  "causationId": "request-or-event-uuid",
  "payload": {}
}
```

Partition key phải là aggregate ID (`orderId`, `productId`) để giữ thứ tự trong
một aggregate. Schema breaking change tạo topic/event version mới.

## 4. Saga đặt hàng và transactional outbox

`order-service` là saga orchestrator; không dùng distributed transaction:

```text
OrderCreated
  → reserve inventory
    → InventoryReserved
      → request payment
        → PaymentCompleted → confirm order → notify
        → PaymentFailed    → release inventory → reject order
    → InventoryRejected    → reject order → notify
```

Mỗi service cập nhật domain table và bảng `outbox_events` trong cùng transaction
PostgreSQL. Outbox publisher khóa batch bằng `FOR UPDATE SKIP LOCKED`, publish
Kafka, rồi đánh dấu `published_at`. Consumer lưu `eventId` vào
`processed_events` trong cùng transaction với thay đổi domain để chống xử lý
lặp.

## 5. Chuẩn bị namespace và secret

```bash
kubectl create namespace aims
kubectl label namespace aims \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted --overwrite

kubectl -n aims create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username='<github-user>' \
  --docker-password='<github-token-read-packages>'
```

Không commit token. Với GHCR public có thể bỏ `ghcr-pull`. Token Jenkins cần
`write:packages`; token pull của cluster chỉ cần `read:packages`.

## 6. PostgreSQL bằng CloudNativePG

Cài operator:

```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update
helm upgrade --install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system --create-namespace
```

Tạo cluster ba instance:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: aims-postgres
  namespace: aims
spec:
  instances: 3
  storage:
    size: 50Gi
  postgresql:
    parameters:
      shared_buffers: 256MB
  bootstrap:
    initdb:
      database: app
      owner: app
```

Sau khi cluster Ready, tạo chín database/user ứng dụng bằng migration job quản
trị. Quyền của user chỉ giới hạn trên database của nó. Bật extension tìm kiếm:

```sql
\c aims_search
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

Không dùng superuser trong Pod ứng dụng. Mỗi service nhận đúng một `DATABASE_URL`
qua Secret riêng.

## 7. Kafka KRaft bằng Strimzi

Cài operator:

```bash
helm repo add strimzi https://strimzi.io/charts/
helm repo update
helm upgrade --install strimzi strimzi/strimzi-kafka-operator \
  --namespace kafka --create-namespace \
  --set watchNamespaces='{aims}'
```

Triển khai Kafka ba node KRaft bằng `KafkaNodePool`, `Kafka` và listener TLS.
Tạo `KafkaUser` TLS với ACL theo prefix `aims.`. Topic production nên có ba
replica, `min.insync.replicas=2`, `unclean.leader.election.enable=false` và
`acks=all` ở producer. Lab nhỏ có thể dùng ba partition/topic; tăng partition
theo throughput và số consumer replica.

Kiểm tra:

```bash
kubectl -n aims wait kafka/aims-kafka --for=condition=Ready --timeout=15m
kubectl -n aims get kafkanodepool,kafka,kafkatopic,kafkauser
```

## 8. Chuẩn workload cho mỗi microservice

Mỗi service có Dockerfile, health endpoint và Deployment riêng. Pod tối thiểu:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: aims
spec:
  replicas: 2
  selector:
    matchLabels: {app: order-service}
  template:
    metadata:
      labels: {app: order-service}
    spec:
      serviceAccountName: order-service
      automountServiceAccountToken: false
      imagePullSecrets: [{name: ghcr-pull}]
      securityContext:
        runAsNonRoot: true
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: app
          image: ghcr.io/tndat-dev/aims-order-service@sha256:<digest>
          ports: [{name: http, containerPort: 8000}]
          envFrom: [{secretRef: {name: order-service-runtime}}]
          readinessProbe:
            httpGet: {path: /readyz, port: http}
          livenessProbe:
            httpGet: {path: /healthz, port: http}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          resources:
            requests: {cpu: 100m, memory: 128Mi}
            limits: {cpu: 500m, memory: 512Mi}
          volumeMounts: [{name: tmp, mountPath: /tmp}]
      volumes: [{name: tmp, emptyDir: {sizeLimit: 128Mi}}]
```

Dùng image digest, hai replica, PodDisruptionBudget và topology spread. API
gateway là workload duy nhất được expose qua Ingress/Gateway; các service còn
lại dùng ClusterIP.

## 9. Jenkins CI, GHCR và GitOps

Jenkins chạy test và build, nhưng không giữ kubeconfig và không gọi `kubectl
apply`. Pipeline chuẩn:

```text
checkout → unit/integration test → build OCI image
→ Trivy scan → Syft SBOM → Cosign sign/attest
→ push GHCR → cập nhật digest trên nhánh GitOps
```

Credentials cần tạo trong Jenkins:

- `github-source`: read repository;
- `ghcr-push`: username + fine-grained/classic token có `write:packages`;
- `gitops-push`: token chỉ được ghi repository/nhánh GitOps;
- khóa Cosign nếu Jenkins không có OIDC workload identity.

Với bare-metal Jenkins không có OIDC native, dùng Cosign key pair lưu trong
Jenkins Credentials hoặc Vault. Muốn keyless thật nên chạy phần sign/attest bằng
GitHub Actions OIDC. Không giả lập keyless bằng token dài hạn.

Job GitOps chỉ thay:

```yaml
image:
  repository: ghcr.io/tndat-dev/aims-order-service
  digest: sha256:<verified-digest>
```

Commit theo dạng `deploy: order-service <short-sha>`. Không ghi tag mutable như
`latest` vào desired state.

## 10. Argo CD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: aims
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/tndat-dev/An-Internet-Media-Store.git
    targetRevision: main
    path: Programming/k8s/aims-chart
    helm:
      releaseName: aims
  destination:
    server: https://kubernetes.default.svc
    namespace: aims
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - PruneLast=true
```

Argo CD là actor duy nhất thay đổi workload. Jenkins chỉ ghi Git. Nếu repository
private, thêm deploy key/repository credential vào Argo CD; không đặt credential
trong Application manifest.

## 11. Thứ tự tách và triển khai

1. Chốt OpenAPI/AsyncAPI contract và event envelope.
2. Dựng PostgreSQL/Kafka, database ownership, user và topic/ACL.
3. Triển khai `notification-service` consumer độc lập.
4. Tách `inventory-service`, sau đó `payment-service` và `order-service` để hoàn
   chỉnh saga/outbox/idempotency.
5. Tách `catalog-service`, rồi tạo `search-recommendation-service` bằng
   PostgreSQL FTS và event-fed projection.
6. Tách `cart-service`, `auth-service`, `api-gateway`.
7. Đưa `security-telemetry-service` ra khỏi critical path.
8. Chuyển route từng lát cắt; luôn giữ rollback về endpoint cũ trong giai đoạn
   strangler migration.

Không copy cùng một monolith image thành mười Deployment rồi gọi đó là mười
microservice. Một service độc lập phải có source/build artifact, contract,
runtime configuration, migration và quyền dữ liệu riêng.

## 12. Nghiệm thu

```bash
kubectl get nodes
kubectl -n aims get pods,svc,pdb
kubectl -n aims get cluster,kafka,kafkatopic,kafkauser
kubectl -n argocd get application aims
```

Các kiểm thử bắt buộc:

- đặt hàng thành công đi hết `order → inventory → payment → notification`;
- payment lỗi kích hoạt release inventory;
- gửi trùng event không tạo payment/order/notification lần hai;
- consumer chết trước commit có thể xử lý lại an toàn;
- message vượt retry limit xuất hiện trong DLQ;
- scale consumer group không làm sai thứ tự cùng aggregate;
- image trong Pod đúng digest đã ghi trong Git;
- rollback Git làm Argo CD đưa workload về digest trước;
- PostgreSQL backup và restore drill thành công.

## 13. Giới hạn của kiến trúc tối giản

Thiết kế này đủ cho học microservice, event-driven, CI và GitOps nhưng chưa phải
production hoàn chỉnh. PostgreSQL cart chậm hơn Redis; PostgreSQL FTS kém linh
hoạt hơn OpenSearch; Kafka retry phức tạp hơn RabbitMQ; auth tự quản lý có rủi
ro hơn Keycloak; thiếu service mesh, secret manager và telemetry tập trung.
Không nên che giấu các giới hạn này trong báo cáo nghiệm thu.
