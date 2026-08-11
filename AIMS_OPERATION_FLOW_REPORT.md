# Báo cáo luồng hoạt động và đồng bộ triển khai AIMS

**Phạm vi:** lab mô phỏng production, namespace `production`

**Cụm nghiệm thu:** kubeadm, 3 control-plane + 3 worker

**Thời điểm chốt trạng thái:** 11/08/2026 (Asia/Bangkok)
**Repository chuẩn:** `tndat-dev/An-Internet-Media-Store`, nhánh `main`

## 1. Mục đích và nguồn sự thật

Tài liệu này mô tả luồng chạy thực tế của AIMS, quan hệ giữa các thành phần và
cách chứng minh source code đã đồng bộ với cụm. Ba lớp trạng thái được phân biệt
rõ:

1. **Git desired state:** Helm chart, manifest, policy, pipeline và runbook trong
   `Programming/k8s` là nguồn sự thật có version.
2. **Argo CD desired/live:** `Application/aims-production` render chart từ Git,
   tự sync, prune và self-heal workload ứng dụng.
3. **Operator-managed live state:** CNPG, Strimzi, RabbitMQ, Redis, MinIO,
   External Secrets, OpenTelemetry và Velero tiếp tục bổ sung default, status và
   resource con. Vì vậy `kubectl diff` có thể thấy metadata/operator default mà
   không phải drift cấu hình.

Snapshot triển khai trên control-plane tại
`/home/dat/aims-deploy-20260729` dùng để bootstrap/reconcile platform. Sau lần
đồng bộ này, toàn bộ `platform/*.yaml`, `cks-lab/*.yaml`, Helm chart và
`scripts/*.sh` tại đó được lấy lại từ cùng revision Git.

## 2. Sơ đồ tổng thể

```mermaid
flowchart TB
    U[Trình duyệt / API client] -->|HTTP 31088 hoặc HTTPS 32725| IG[Istio Gateway API<br/>aims-ingress]
    IG --> RT[HTTPRoute aims-web]
    RT --> FE[Frontend x2]
    RT --> API[9 Service / 18 pod<br/>Argo Rollouts]

    subgraph Ambient[Istio Ambient]
      Z[ztunnel trên 6 node<br/>HBONE + mTLS]
      WP[waypoint production<br/>L7 policy]
    end
    IG --> Z --> WP --> API

    API --> PG[(CloudNativePG 3)]
    API --> RD[(Redis + Sentinel 3)]
    API --> KF[(Kafka KRaft 3<br/>event log)]
    API --> RMQ[(RabbitMQ 3<br/>task queue + ack/DLQ)]
    API --> KC[Keycloak OIDC]
    API --> OT[OpenTelemetry Collector]

    OT --> PR[Prometheus/Grafana]
    OT --> LK[Loki]
    OT --> TP[Tempo]
    TG[Tetragon] --> ST[security telemetry]
    ST --> KF --> OS[OpenSearch]

    ESO[External Secrets] -->|đọc KV v2| VA[Vault HA]
    ESO -->|tạo Secret runtime| API
    CM[cert-manager] --> IG
    LH[Longhorn] --> PG
    LH --> RD
    LH --> KF
    LH --> RMQ
    LH --> MN[(MinIO)]
    VE[Velero + Kopia] --> MN
```

## 3. Luồng reconcile từ Git tới pod

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant GL as GitLab CI
    participant Git as Git repository
    participant Argo as Argo CD
    participant Roll as Argo Rollouts
    participant K8s as Kubernetes API
    participant Adm as PSA/Kyverno/Gatekeeper
    participant Mesh as Cilium/Istio Ambient

    Dev->>Git: push source + manifest
    GL->>GL: test, build, scan, SBOM, provenance, sign
    GL->>Git: cập nhật image digest đã verify [skip ci]
    Argo->>Git: poll/webhook revision main
    Argo->>K8s: server-side reconcile Helm desired state
    K8s->>Adm: admission và policy validation
    Adm-->>K8s: allow hoặc deny kèm lý do
    K8s->>Roll: tạo revision canary mới
    Roll->>K8s: 20% -> pause -> 50% -> pause -> 100%
    K8s->>Mesh: endpoint/identity mới
    Mesh-->>Argo: pod Ready, route programmed
    Argo-->>Dev: Synced / Healthy
```

Các resource nền/operator không nên bị Argo CD nhận ownership một cách mơ hồ.
Script `deploy-aims-platform.sh` bootstrap chúng theo thứ tự CRD/operator trước,
custom resource sau. `deploy-aims-resources.sh` chỉ reconcile desired state
AIMS/data/policy khi không muốn nâng cấp chart quan sát lớn.

## 4. Luồng request từ ngoài vào AIMS

### 4.1 Điểm vào

Bare-metal không có cloud LoadBalancer nên Istio-managed Gateway được expose
bằng NodePort:

| Giao thức | Địa chỉ lab | Chức năng |
|---|---|---|
| HTTP | `http://10.1.16.234:31088` | listener 80, host `aims.lab` |
| HTTPS | `https://10.1.16.234:32725` | TLS terminate, certificate self-signed |
| DNS/Host | `aims.lab` | hostname được Certificate và route dùng |

Trên máy client thêm `10.1.16.234 aims.lab` vào `/etc/hosts`, sau đó dùng
`http://aims.lab:31088` hoặc `https://aims.lab:32725`. Với certificate lab,
client cần import CA hoặc dùng `curl -k` khi kiểm thử.

### 4.2 Định tuyến

`HTTPRoute/production/aims-web` gắn vào cả listener HTTP và HTTPS:

| Path prefix | Backend Service |
|---|---|
| `/api/auth/`, `/api/admin/` | `auth-service:8000` |
| `/api/products/` | `catalog-service:8000` |
| `/api/cart/` | `cart-service:8000` |
| `/api/orders/` | `order-service:8000` |
| `/api/payments/` | `payment-service:8000` |
| `/api/inventory/` | `inventory-service:8000` |
| `/api/notifications/` | `notification-service:8000` |
| `/api/security/` | `security-telemetry-service:8000` |
| `/api/` còn lại | `api-gateway:8000` |
| `/` còn lại | `aims-frontend:3000` |

Gateway north-south dùng `GatewayClass/istio`. Waypoint east-west là một
Gateway riêng dùng `GatewayClass/istio-waypoint`; hai khái niệm không được gộp
làm một. Traffic pod-to-Service được ztunnel mã hóa HBONE/mTLS, chuyển qua
waypoint khi cần xử lý L7. `PeerAuthentication/default` giữ STRICT; chỉ port
probe/native TLS đặc thù của operator có ngoại lệ theo port.

## 5. Luồng nghiệp vụ

### 5.1 Luồng mua hàng đồng bộ đang chạy

```mermaid
sequenceDiagram
    actor C as Customer
    participant FE as Frontend
    participant KC as Keycloak/Auth
    participant CAT as Catalog
    participant CART as Cart
    participant ORD as Order
    participant PAY as Payment
    participant PG as PostgreSQL
    participant REDIS as Redis

    C->>FE: đăng nhập / xem sản phẩm
    FE->>KC: OIDC authentication
    KC-->>FE: access token
    FE->>CAT: GET /api/products
    CAT->>PG: đọc catalog/stock
    FE->>CART: thêm/xóa item
    CART->>PG: lưu trạng thái giỏ hàng
    CART->>REDIS: cache/session khi tích hợp runtime
    FE->>ORD: tạo draft + delivery info
    ORD->>PG: transaction order/invoice snapshot
    FE->>PAY: callback/confirm payment
    PAY->>PG: cập nhật payment và order atomically
    ORD-->>FE: trạng thái đơn hàng
```

Source ứng dụng hiện là Django modular monolith. Chín Rollout dùng cùng image
backend nhưng có ServiceAccount, Service, lifecycle, placement và biến
`AIMS_SERVICE_NAME` riêng. Gateway tách path theo domain để mô phỏng biên
microservice và cho phép rollout/policy/telemetry độc lập. Các domain đã có API
trong source là auth, catalog, cart, order và payment; inventory, notification
và security telemetry hiện chủ yếu là topology/integration seam của lab.

Điểm này quan trọng: hạ tầng Kafka/RabbitMQ đã chạy và endpoint đã được inject
vào mọi pod, nhưng source Django hiện chưa có publisher/consumer thực sự dùng
các biến `KAFKA_*` hoặc `RABBITMQ_*`. Vì vậy không tuyên bố giao dịch hiện tại
đã event-driven end-to-end. Luồng mục 5.2 là thiết kế đích có sẵn backbone để
phát triển tiếp, còn luồng mục 5.1 là hành vi ứng dụng đã có trong code.

### 5.2 Luồng event/task đích trên backbone đã triển khai

```mermaid
flowchart LR
    O[order-service] -->|OrderCreated| KB[Kafka<br/>aims-business-events]
    KB --> I[inventory-service]
    I -->|StockReserved / StockRejected| KB
    KB --> P[payment-service]
    P -->|PaymentCompleted / Failed| KB
    KB --> N[notification-service]

    P -->|payment task| R[RabbitMQ quorum queue]
    N -->|email/SMS task| R
    R -->|manual ack| W[worker]
    W -->|retry giới hạn| R
    W -->|poison message| D[DLQ]

    KB --> S[(consumer replay/audit)]
```

Kafka giữ business event lâu, có partition/offset và replay; RabbitMQ điều phối
task cần ack, retry và DLQ. Không dùng Kafka thay task queue và không dùng
RabbitMQ làm immutable event log. Strimzi chạy KRaft ba dual-role node, không có
ZooKeeper; topic `aims-business-events` và `aims-security-telemetry` có
replication factor 3.

## 6. Luồng identity, secret và PKI

```mermaid
sequenceDiagram
    participant Admin as Platform admin
    participant Vault as Vault KV v2
    participant ESO as External Secrets Operator
    participant Sec as Kubernetes Secret
    participant Pod as AIMS pod
    participant KC as Keycloak
    participant API as API/Gateway

    Admin->>Vault: ghi credential production
    ESO->>Vault: Kubernetes auth + role external-secrets
    Vault-->>ESO: chỉ property được khai báo
    ESO->>Sec: reconcile aims-runtime/redis/minio/velero
    Pod->>Sec: envFrom lúc khởi tạo
    Pod->>KC: kiểm tra issuer/token OIDC
    API->>KC: redirect/login/introspect tùy client
```

Secret thật không nằm trong Git. Mỗi backend có ServiceAccount riêng và không
automount token API. RBAC developer chỉ đọc resource vận hành cần thiết, không
được đọc Secret; CI/CD ServiceAccount chỉ có quyền mutation trong phạm vi đã
khai báo. cert-manager cấp certificate self-signed cho `aims.lab`; production
thật phải thay bằng DNS và CA được client tin cậy.

## 7. Luồng security telemetry và quan sát

```mermaid
flowchart LR
    SYS[syscall/process/network] --> TET[Tetragon]
    SYS --> FAL[Falco - CKS practice]
    TET --> SEC[security-telemetry-service]
    SEC --> KSEC[Kafka security topic]
    KSEC --> ML[LSTM / Isolation Forest]
    ML --> OS[OpenSearch security index]
    OS --> DASH[Search/dashboard/alert]

    APP[AIMS services] -->|OTLP traces/logs/metrics| COL[OTel Collector x2]
    COL --> TEMPO[Tempo]
    COL --> LOKI[Loki]
    COL --> PROM[Prometheus]
    PROM --> GRAF[Grafana]
```

Tetragon là runtime detector chính của hệ thống; Falco được giữ để luyện luật
CKS và so sánh engine. OpenTelemetry gắn `deployment.environment=production`,
batch và memory limiter trước khi export. Kafka tạo đường đệm/replay cho dữ liệu
security; mô hình LSTM/Isolation Forest của capstone là consumer phân tích đích,
không nằm trong manifest inference hiện tại.

## 8. Luồng supply chain và policy admission

```mermaid
flowchart LR
    SRC[Git commit] --> TEST[Test/lint]
    TEST --> BUILD[Build OCI image]
    BUILD --> TRI[Trivy image scan]
    SRC --> KSEC[kubesec manifest scan]
    BUILD --> SYFT[Syft CycloneDX SBOM]
    SYFT --> PROV[SLSA v1 / in-toto provenance]
    PROV --> SIGN[Cosign keyless sign + attest]
    SIGN --> REKOR[Rekor transparency log]
    SIGN --> VERIFY[cosign verify/verify-attestation]
    VERIFY --> GITOPS[commit image digest]
    GITOPS --> ARGO[Argo CD]
    ARGO --> KYV[Kyverno verifyImages]
    KYV --> RUN[Argo Rollouts canary]
```

Pipeline root include `Programming/.gitlab-ci.yml` và thực hiện
`test → build → scan → attest → verify → gitops`. SBOM CycloneDX được đính kèm
thành attestation; provenance dùng predicate SLSA v1 tương thích in-toto. Cosign
keyless ràng buộc certificate với GitLab OIDC identity và ghi transparency log
Rekor. Kyverno nối verify signature/provenance/SBOM tại admission.

Trong lab, image `prod-sim` là node-local và chưa có registry digest/signature,
nên policy supply-chain còn Audit. Sau lần pipeline registry thật đầu tiên phải
điền đúng registry/identity, verify thành công rồi mới chuyển Enforce; các policy
runtime khác và PSA Restricted hiện đã Enforce/deny.

## 9. Luồng backup và phục hồi

```mermaid
flowchart LR
    NS[Resource namespace production] --> V[Velero]
    PVC[PVC ứng dụng] -->|Kopia file-system backup| V
    V -->|S3 API| M[MinIO bucket velero]
    M --> LH[Longhorn volumes 4 x 50 GiB]
    DB[CNPG logical/physical recovery] -. kiểm thử riêng .-> DR[Restore plan]
    V --> DR
```

Lịch `production-daily` backup namespace `production`, TTL 720 giờ. PVC MinIO
đích bị loại khỏi Kopia để tránh vòng lặp “backup bucket vào chính bucket”;
object Kubernetes của Tenant vẫn được lưu. Backup nghiệm thu
`production-post-reboot-recovery-20260811` đã `Completed`: 1.730/1.730 object,
43/43 PodVolumeBackup, 0 error và 5 warning vô hại do volume khai báo nhưng
không mount. Restore drill mặc định chỉ phục hồi ConfigMap vào namespace tạm,
không đụng Secret/PVC/workload production.

## 10. Hardening và thực hành CKS

Mỗi pod ứng dụng chạy non-root, read-only root filesystem, drop toàn bộ Linux
capability, cấm privilege escalation và dùng seccomp. Payment/notification dùng
`RuntimeClass/sandbox` (gVisor); security telemetry dùng Localhost seccomp cùng
Localhost AppArmor. PSA `restricted:latest` Enforce cho production. Kyverno và
Gatekeeper chặn cấu hình runtime yếu; Cilium NetworkPolicy và Istio STRICT bảo
vệ network; audit logging ghi mutation/RBAC/policy nhưng không ghi body Secret.

Hai DaemonSet kube-bench bao phủ ba control-plane và ba worker. `cks-lab` tách
khỏi production; verifier chạy negative server-side dry-run để chứng minh PSA,
Kyverno và Gatekeeper từ chối pod vi phạm mà không tạo workload rác.

## 11. Trạng thái live đã nghiệm thu

| Hạng mục | Trạng thái chốt |
|---|---|
| Node | 6/6 Ready, 3 control-plane + 3 worker |
| AIMS | 9/9 Rollout, 18/18 pod backend, 2/2 frontend |
| Phân bố backend | worker1/worker3/worker4 = 6/6/6 |
| CloudNativePG | 3/3, healthy |
| Kafka KRaft | Ready, 3 broker trên ba worker |
| RabbitMQ | 3/3, `AllReplicasReady=True` |
| Redis/Sentinel | 3/3 + 3/3 |
| MinIO | `Initialized`, health `green`, 4 PVC × 50 GiB |
| OpenSearch | 3/3 |
| Vault | 3/3 Ready và unsealed |
| Istio Ambient | ztunnel 6/6, waypoint Ready, mTLS STRICT |
| Longhorn | 28/28 volume healthy |
| Argo CD | `Synced/Healthy`, revision Git đã chốt |
| Pod/Job/PVC | 0 pod lỗi hiện tại, 0 Job failed hiện tại, 0 PVC unbound |
| Gateway | HTTP và HTTPS được verifier sample lặp, đều HTTP 200 |

## 12. Quy trình đồng bộ và kiểm chứng

### 12.1 Đồng bộ snapshot triển khai trên master

Từ workstation, đồng bộ đúng thư mục K8s; không sao chép `.git`, credential hay
file môi trường:

```bash
rsync -a --delete \
  Programming/k8s/ \
  dat@10.1.16.234:/home/dat/aims-deploy-20260729/
```

Trong lần bàn giao này, checksum được đối chiếu cho toàn bộ manifest/script sau
khi copy. Thư mục báo cáo ở root repository được đồng bộ riêng vào workspace
HUST để nộp bài; nó không cần nằm trên control-plane để Kubernetes chạy.

### 12.2 Audit read-only trên control-plane

```bash
cd /home/dat/aims-deploy-20260729
EXPECTED_REVISION="$(kubectl -n argocd get application aims-production \
  -o jsonpath='{.status.sync.revision}')" \
  scripts/audit-live-sync.sh
```

Script kiểm tra node Ready/DiskPressure, mọi pod/container, Job hiện đang fail,
PVC, Argo sync/health/revision, chín Rollout, các operator stateful, Longhorn và
chạy tiếp hai verifier AIMS/CKS. Để xem diff server-side mà không apply:

```bash
SHOW_KUBECTL_DIFF=true FULL_VERIFY=false scripts/audit-live-sync.sh
```

Exit 1 của `kubectl diff` chỉ có nghĩa có khác biệt. Với CR do operator quản lý,
phải đọc diff trước khi apply: `last-applied-configuration`, status/default,
immutable volume template hay Job bootstrap đã TTL cleanup không phải lúc nào
cũng là drift. Exit lớn hơn 1 mới là lỗi gọi API trong audit.

### 12.3 Điều kiện hoàn thành

Một lần đồng bộ chỉ được coi là hoàn thành khi đồng thời thỏa mãn:

- Git working tree sạch và commit đã push;
- snapshot master có checksum giống `Programming/k8s` của commit đó;
- Argo CD báo đúng revision, `Synced` và `Healthy`;
- `audit-live-sync.sh`, `verify-aims.sh`, `verify-cks-lab.sh` đều exit 0;
- không còn pod non-ready/Unknown, Job đang failed hoặc PVC unbound;
- HTTP/HTTPS đều trả 200 qua Gateway, không chỉ nhìn condition `Programmed`.

## 13. Giới hạn có chủ đích của lab

- Đây là production-like lab, không phải SLA enterprise; certificate ingress
  self-signed và MinIO backup cùng failure domain với cluster.
- Keycloak đã phục vụ OIDC ứng dụng, nhưng kube-apiserver chưa hoàn tất OIDC cho
  `kubectl`.
- GitLab Runner/Registry/OIDC thật không chạy trong cụm; pipeline đã có code
  nhưng cần import/mirror repository và cấp masked credential để chạy end-to-end.
- Chín deployment unit chưa phải chín codebase độc lập; các publisher/consumer
  Kafka/RabbitMQ và ML inference cần được hiện thực trong application code.
- SLSA provenance tự sinh trong job chỉ được tuyên bố tương thích Build L1;
  mức L2/L3 cần builder độc lập/hardened sinh provenance.
- Backup MinIO cần replication/off-cluster nếu muốn chống mất toàn cụm.

Các giới hạn này không làm sai mục tiêu học tập: cụm hiện chứng minh đầy đủ
orchestration, operator, HA, policy, supply-chain wiring, runtime security,
observability, backup/restore và quy trình phát hiện/khôi phục lỗi.
