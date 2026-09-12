# AIMS Kubernetes production-like platform

Thư mục này chứa desired state và runbook cho AIMS trong namespace
`production`. Trạng thái nghiệm thu gần nhất 12/09/2026: 3 control-plane + 3
worker, 10 Argo Rollout/20 pod microservice độc lập và 2 frontend pod,
CloudNativePG 3/3, Kafka KRaft, RabbitMQ, Redis, MinIO, OpenSearch và Velero hoạt
động. PSA Restricted được Enforce; verifier AIMS và CKS đều trả exit code 0.
Microservice được phân bố 6/7/7 trên ba worker, hai frontend pod nằm trên hai
worker khác nhau.

Repository chuẩn trên workstation là `/home/tndat/An-Internet-Media-Store`.
Control-plane chính giữ clone đầy đủ tại `/home/dat/An-Internet-Media-Store` và
snapshot vận hành K8s tại `/home/dat/aims-deploy-20260729`; workspace HUST không
phải nguồn deploy.

Lần nghiệm thu 11/08 bao gồm phục hồi sau unclean reboot đồng thời sáu node:
filesystem stateful được snapshot trước khi sửa, CNPG/RabbitMQ/OpenSearch/Vault
đã về đủ replica, Argo CD `Synced/Healthy`, ztunnel đủ 6/6 và Velero smoke
backup hoàn tất. Hai `PeerAuthentication` theo port cho phép probe/native TLS
của operator đi qua Ambient nhưng giữ STRICT cho mọi port ứng dụng còn lại.

Báo cáo kiến trúc, lý thuyết, triển khai và sự cố đầy đủ nằm tại
[`../../AIMS_DEPLOYMENT_REPORT.md`](../../AIMS_DEPLOYMENT_REPORT.md). Sơ đồ và
diễn giải request, nghiệp vụ, data/messaging, security telemetry, supply chain,
backup cùng quy trình chứng minh Git/live đồng bộ nằm tại
[`../../AIMS_OPERATION_FLOW_REPORT.md`](../../AIMS_OPERATION_FLOW_REPORT.md).
Runbook riêng cho cluster tối giản chỉ có Kafka, Jenkins, Argo CD và PostgreSQL
nằm tại [`../../AIMS_MINIMAL_CLUSTER_DEPLOYMENT.md`](../../AIMS_MINIMAL_CLUSTER_DEPLOYMENT.md).

## Cấu trúc

- `aims-chart/`: 10 microservice dưới dạng Argo Rollout, frontend Deployment,
  Service, HTTP/HTTPS Gateway API và certificate TLS lab; ingress dùng
  `GatewayClass/istio`, Ambient L7 dùng `GatewayClass/istio-waypoint` riêng.
- `platform/00-namespace.yaml`, `40-production-enforcement.yaml`: bootstrap PSA
  audit/warn rồi chuyển sang Restricted Enforce sau khi workload đã sẵn sàng.
- `platform/00-foundation.yaml`: quota, mTLS, waypoint,
  RuntimeClass và network policy nền.
- `platform/05-rbac.yaml`: Role/RoleBinding cho nhóm Keycloak và service account
  CI/CD theo least privilege; không cấp quyền đọc Secret cho developer.
- `platform/10-data-messaging.yaml`: CNPG, Redis, Kafka KRaft, RabbitMQ và MinIO.
- `platform/15-external-secrets.yaml`: Vault SecretStore/ExternalSecret.
- `platform/20-policy-security.yaml`, `21-gatekeeper-constraint.yaml`: Kyverno,
  Gatekeeper và Tetragon policy.
- `platform/22-supply-chain-policy.yaml`: Kyverno verify Cosign keyless, SLSA v1
  provenance và CycloneDX SBOM attestation.
- `platform/25-kube-bench.yaml`: kube-bench v0.15.5 chạy CIS benchmark trên mọi
  control-plane/worker.
- `audit/audit-policy.yaml`: audit policy cho kube-apiserver, không ghi body
  Secret và có lọc request ồn.
- `platform/30-observability.yaml`: OpenTelemetry và resource quan sát.
- `platform/50-backup.yaml`, `60-backup-schedule.yaml`: Velero/MinIO backup.
- `platform/*-values.yaml`: values cho Vault, Loki, Tempo, OpenSearch, Velero và
  MinIO Operator; `minio-operator-values.yaml` nối operator tới Prometheus CR
  thực trong namespace `monitoring`.
- `node-profiles/`: Localhost seccomp và AppArmor profile.
- `cks-lab/`: namespace/NetworkPolicy/RBAC/Quota tách biệt để thực hành CKS.
- `scripts/`: cài node profile/gVisor, reconcile, backup, audit đồng bộ và
  nghiệm thu. `audit-live-sync.sh` là audit read-only tổng hợp trạng thái GitOps,
  pod/Job/PVC, operator, Longhorn và hai verifier.

Manifest monolith `aims-production.yaml` đã được loại khỏi desired state để
không thể apply nhầm PostgreSQL/backend/VirtualService cũ vào production.

## Điều kiện tiên quyết

Cụm phải có `kubectl`, `helm`, `jq` và các operator/CRD tương ứng: Argo
Rollouts, CloudNativePG, Strimzi, RabbitMQ Cluster Operator, Redis Operator,
MinIO Operator, Kyverno, Gatekeeper, External Secrets và Velero. Secret thật
phải nằm trong Vault; không commit mật khẩu, token, private key hoặc `.env`.

Helm values hiện pin immutable GHCR digest cho frontend, backend tương thích và
10 image microservice. Tạo `production/ghcr-pull` loại
`kubernetes.io/dockerconfigjson` bằng Vault/ESO hoặc quy trình out-of-band trước
khi reconcile; không lưu token trong Git. Affinity/anti-affinity phân bố replica
trên ba worker, không còn phụ thuộc image nạp cục bộ theo node.

Trivy Operator quét workload image có registry; GitHub Actions đồng thời quét
chặn Critical trước khi ký và promote. Các exclusion `prod-sim` cũ chỉ còn để
tương thích rollback lịch sử, không khớp image GHCR đang chạy.

## Cài profile trên từng worker

```bash
sudo scripts/configure-gvisor-worker.sh
sudo scripts/install-node-security-profiles.sh \
  node-profiles/aims-runtime.json \
  node-profiles/aims-restricted.apparmor
kubectl label node <worker> runtime.gvisor.dev/enabled=true --overwrite
```

Chỉ dùng `configure-small-disk-worker.sh` cho worker lab 40 GiB. Sau khi mở rộng
disk phải trả eviction reserve về 10–15%.

## Reconcile

Reconcile toàn bộ platform đã có operator:

```bash
scripts/deploy-aims-platform.sh
```

Hoặc chỉ desired state AIMS/data/policy, không nâng cấp các chart Loki/Tempo/
OpenSearch:

```bash
scripts/deploy-aims-resources.sh
```

Nâng cấp bảo mật đầy đủ, gồm server-side dry-run, audit logging tuần tự trên ba
API server, Gateway/RBAC/Kyverno/kube-bench, dọn pod lịch sử và nghiệm thu:

```bash
scripts/reconcile-security-upgrade.sh
```

Script audit tạo bản sao `kube-apiserver.yaml.pre-audit-<timestamp>` trước mỗi
lần sửa và chỉ chuyển sang control-plane tiếp theo sau khi `/readyz` phục hồi.
Audit JSON nằm tại `/var/log/kubernetes/audit/audit.log`, rotate 100 MiB × 10,
giữ tối đa 30 ngày.

## GitHub Actions CI, Jenkins lab và microservice extraction

Pipeline chính là [`.github/workflows/aims-supply-chain.yml`](../../.github/workflows/aims-supply-chain.yml):
test → build frontend/backend và 10 image service → push GHCR → Trivy → Syft
CycloneDX → Cosign keyless → SLSA/in-toto attestation → verify → commit digest
vào Helm values.
GitHub OIDC là identity ký; không lưu Cosign private key. Argo CD vẫn là CD
reconciler duy nhất và workload luôn dùng immutable digest.

Jenkins được cài riêng trong namespace `jenkins`, dùng PVC Longhorn 20GiB,
controller `0` executor và Kubernetes ephemeral agent. Jenkins được giữ để thực
hành Kubernetes agent sau, không nằm trên đường phát hành chính và **không** có
quyền apply vào `production`:

```bash
scripts/install-jenkins-ci.sh
ssh -L 18080:127.0.0.1:18080 dat@10.1.16.234 \
  'kubectl -n jenkins port-forward --address 127.0.0.1 svc/aims-jenkins 18080:8080'
```

Mở `http://localhost:18080`; password admin chỉ lấy lúc cần đăng nhập từ Secret
`jenkins/aims-jenkins`, không lưu vào Git. [`../../Jenkinsfile`](../../Jenkinsfile)
là pipeline lab, chưa bật publish.

Cả 10 bounded service đều có source, dependency, Dockerfile, test và image riêng
tại [`../../services`](../../services): `api-gateway`, `auth`, `catalog`,
`cart`, `order`, `payment`, `inventory`, `notification`,
`search-recommendation`, `security-telemetry`. Bảy service stateful sở hữu schema
PostgreSQL riêng; giao tiếp liên service hiện đi qua HTTP contract và Kafka
event log/outbox thay vì ORM chéo. RabbitMQ cluster và hai queue đã sẵn sàng ở
tầng platform, nhưng app user, exchange/binding/DLQ và consumer manual-ack vẫn
là phần mở rộng tiếp theo. Contract event versioned nằm ở
[`../../contracts/asyncapi/aims-events.yaml`](../../contracts/asyncapi/aims-events.yaml).

## Dashboard quản trị giao tiếp

Hubble UI là giao diện chính để xem flow giữa các component AIMS. Từ workstation:

```bash
ssh -L 12000:127.0.0.1:12000 dat@10.1.16.234 \
  'kubectl -n kube-system port-forward --address 127.0.0.1 \
  svc/hubble-ui 12000:80'
```

Mở `http://localhost:12000` và chọn namespace `production`. RabbitMQ Management
dùng tunnel tương tự tới `production/aims-rabbitmq:15672`. Grafana, Prometheus,
Argo CD, Rollouts, Keycloak và Vault đã có NodePort lần lượt `32300`, `32090`,
`30081/30443`, `30100`, `30080` và `30200`. Argo CD đăng nhập bằng user `admin`;
password lấy từ Secret `argocd/argocd-initial-admin-secret`, không ghi vào Git.
Chi tiết URL, credential Secret, MinIO tunnel và danh sách UI chưa cài nằm tại
[`../../AIMS_OPERATION_FLOW_REPORT.md`](../../AIMS_OPERATION_FLOW_REPORT.md#43-giao-diện-quản-trị-giao-tiếp-giữa-các-component).

Apply Gatekeeper theo thứ tự ConstraintTemplate trước Constraint. Constraint
runtime hiện dùng `deny`; Kyverno runtime policy cũng Enforce. Policy
Cosign/SLSA Enforce cho image `ghcr.io/tndat-dev/aims-*`; image node-local cũ
không thuộc selector này. Không bật Argo CD `prune` cho đến khi repo Git chứa
đầy đủ resource đang quản lý.

## Trạng thái mã CI/CD và GitOps

Bộ mã local đã có Dockerfile backend/frontend và 10 service, Helm chart AIMS,
toàn bộ manifest platform/CKS và script vận hành. GitHub Actions định nghĩa đủ
luồng `test → build → scan → attest → verify → gitops`, gồm Trivy, Syft SBOM,
SLSA provenance, Cosign keyless sign/attest/verify và cập nhật image digest vào
Helm values. `argocd-application.yaml` trỏ tới repository bàn giao
`tndat-dev/An-Internet-Media-Store`, có automated sync/prune/self-heal nhưng chỉ
được apply sau khi commit đã có trên `main`. `scripts/install-cicd-controllers.sh`
tái tạo đúng Argo CD/Argo Rollouts đang chạy; chỉ bật Application khi
`ENABLE_AIMS_GITOPS=true` và script xác nhận chart đã tồn tại trên Git remote.

Workflow dùng `GITHUB_TOKEN` để push GHCR và commit GitOps, cùng permission
`id-token: write` cho Fulcio/Rekor. Repository phải cho Actions ghi Contents và
Packages. GHCR package public không cần pull secret; package private phải cấp
`imagePullSecret` qua Vault/External Secrets. Secret, token, password và private
key không thuộc source code.

Trạng thái live 12/09/2026: Argo CD và Argo Rollouts đều khỏe; 10/10 Rollout
AIMS `Healthy`. `Application/aims-production` đã đọc chart trên GitHub
`main`, automated sync/prune/self-heal; cụm chưa cài GitLab Runner. Argo CD UI/API
được expose NodePort `30081`, Rollouts Dashboard `30100`. Jenkins vẫn Ready
nhưng được hoãn làm pipeline theo quyết định hiện tại.

Kiểm tra local sau khi sửa layout pipeline: backend `207 passed`, frontend lint
và typecheck PASS, YAML pipeline parse PASS, Docker build backend/frontend PASS,
Helm lint/render PASS. `config/settings.py` giữ environment làm nguồn ưu tiên để
CI `DATABASE_URL`/Vault Secret không bị `.env.local` ghi đè.

## Nghiệm thu

```bash
scripts/audit-live-sync.sh
scripts/verify-aims.sh
scripts/verify-cks-lab.sh
```

Có thể ràng buộc revision Argo CD mong đợi và xem server-side diff mà không
apply:

```bash
EXPECTED_REVISION=<full-git-sha> \
EXPECTED_SOURCE_REVISION=<source-build-full-git-sha> \
EXPECTED_NOTIFICATION_SOURCE_REVISION=<notification-source-full-git-sha> \
EXPECTED_INVENTORY_SOURCE_REVISION=<inventory-source-full-git-sha> \
  scripts/audit-live-sync.sh
SHOW_KUBECTL_DIFF=true FULL_VERIFY=false scripts/audit-live-sync.sh
```

Script trả non-zero nếu sai bất kỳ tiêu chí nào: topology 3 CP + 3 worker,
node Ready/không DiskPressure, 10 Rollout/20 pod cân bằng với max skew 1,
CNPG/Kafka/RabbitMQ/MinIO/OpenSearch, Vault/Velero, gVisor/Localhost profiles,
frontend Helm/read-only, HTTP+HTTPS Gateway, RBAC, Kyverno/Gatekeeper,
kube-bench/runtime detector và không còn controller legacy. Có thể đổi topology bằng `EXPECTED_READY_NODES`,
`EXPECTED_CONTROL_PLANES`, `EXPECTED_WORKERS` khi join thêm node.

`EXPECTED_SOURCE_REVISION` là tùy chọn nhưng nên luôn đặt khi nghiệm thu release.
Verifier yêu cầu cả 20 pod microservice và hai frontend pod mang đúng annotation
`aims.hust.vn/source-revision`; hai biến revision riêng notification/inventory
được giữ để tương thích với quy trình audit các release trước.

Nếu external Sentinel validation bật binding
`sentinel-experiment-resource-lock`, verifier ghi riêng bốn controller đo tải là
`INFO` và cleanup bảo toàn chúng. Khi binding biến mất, cùng các controller đó
trở lại tiêu chí legacy và phải được `cleanup-production-legacy.sh` xóa.

## Supply chain SLSA

`.github/workflows/aims-supply-chain.yml` là pipeline phát hành chính và thực
hiện test → build → Trivy → Syft CycloneDX → SLSA provenance → Cosign keyless
sign/attest → verify → GitOps. Image được ký theo digest, Fulcio certificate gắn
với GitHub Actions identity và entry được ghi vào Rekor. Hai attestation bắt
buộc là:

- `https://slsa.dev/provenance/v1` với build definition, source revision,
  builder/run metadata và digest SBOM trong resolved dependency/byproduct;
- `https://cyclonedx.org/bom` chứa CycloneDX component/hash/PURL; bản Syft đầy
  đủ được giữ làm CI artifact 30 ngày.

Policy Kyverno chạy `Enforce`, dùng `mutateDigest=false`, `verifyDigest=true` vì
Helm values đã pin GHCR digest. Role giới hạn Kyverno chỉ đọc đúng Secret
`production/ghcr-pull`. Pipeline pin Cosign 2.6.x để sinh `.sig/.att` mà Kyverno
1.18.2 đọc ổn định; bản Cosign 3 OCI 1.1-only hiện có lỗi discovery upstream.
Registry path và GitHub workflow identity trong `22-supply-chain-policy.yaml`
phải được đổi đồng bộ nếu fork repository.

Tạo backup thủ công an toàn:

```bash
scripts/velero-smoke-backup.sh
scripts/velero-final-backup.sh
kubectl -n velero get backups.velero.io
```

Ngày 03/08/2026, Kopia maintenance từng lỗi do drive MinIO chạm
minimum-free-drive threshold. Nguyên nhân gốc là daily backup dùng
`defaultVolumesToFsBackup: true` nhưng chưa loại MinIO, tạo vòng lặp backup PVC
đích vào chính bucket Velero. Pool annotation nay loại `data0,data1,cfg-vol`;
object Kubernetes của Tenant vẫn được backup, còn bucket phải dùng replication/
backup off-cluster. Bốn PVC được nâng từ 10 lên 50 GiB để có headroom prune,
operator được nối đúng Prometheus. `verify-aims.sh` kiểm tra thêm dung lượng 4/4
PVC, repository/maintenance Kopia và không còn volume backup mồ côi.

Ngày 11/08/2026, daily backup khởi chạy đúng lúc MinIO chưa sẵn sàng sau reboot
nên fail nhanh với S3 `503`; đây không phải lỗi repository. Kopia maintenance
kế tiếp đã `Succeeded`, BackupRepository trở lại `Ready`, BSL `Available` và
backup metadata `production-smoke-20260811053150` đã `Completed`. Job failed cũ
được dọn sau khi lưu nguyên nhân trong báo cáo; lịch daily vẫn giữ nguyên. Full
validation `production-post-reboot-recovery-20260811` sau đó `Completed` trong
khoảng 6 phút: 1.730/1.730 object, 43/43 PodVolumeBackup, 0 error. Năm warning
chỉ là volume khai báo nhưng không mount của Redis/waypoint.

Ngày 12/09/2026, ba daily backup bị `PartiallyFailed` do PID RabbitMQ nằm trong
PVC Mnesia và một replica gặp `EIO`. `RABBITMQ_PID_FILE` đã chuyển sang emptyDir
`/operator`; PVC của đúng replica hỏng, không giữ queue/message, được tái tạo sau
khi kiểm tra quorum. RabbitMQ trở lại 3/3 Khepri voter. Full backup
`production-rabbit-fix-20260912135805` hoàn tất 1.158/1.158 object, 32/32
PodVolumeBackup (gồm cả ba RabbitMQ PVC), 0 error. Restore drill
`aims-config-drill-20260912140426` hoàn tất 12 ConfigMap và xác nhận không phục
hồi Pod/Secret/PVC/controller.

Restore drill metadata cô lập chỉ phục hồi ConfigMap vào namespace tạm
`production-drill`; nên truyền rõ backup `Completed` mới nhất:

```bash
BACKUP_NAME=<completed-backup> scripts/velero-config-restore-drill.sh
```

Script từ chối namespace có sẵn/namespace hệ thống, đặt PSA Restricted, loại
Secret/workload/PVC/cluster resource, kiểm tra số lượng object rồi xóa namespace
tạm. Restore CR được giữ trong `velero` làm bằng chứng. Lần nghiệm thu
`aims-config-drill-20260801113325` đã `Completed`: 11 ConfigMap, 0 Pod, 0 Secret,
0 PVC, 0 controller; namespace tạm đã được xóa. Đây là drill metadata an toàn,
không thay thế kiểm thử phục hồi PostgreSQL/Kafka và volume đầy đủ.

## Giới hạn hiện tại

- Keycloak chạy cho ứng dụng nhưng kube-apiserver chưa bật OIDC cho `kubectl`.
- PSA `restricted:latest` đã Enforce trong production; `cks-lab` cố ý dùng
  Baseline Enforce và Restricted Audit/Warn để thực hành negative test.
- GitHub Actions/GHCR/Argo CD đã chạy end-to-end; Jenkins được giữ làm lab và
  chưa được cấp registry/signing credential dài hạn.
- SLSA predicate hiện do job trong repository tạo nên chỉ được tuyên bố là
  provenance tương thích SLSA Build L1; muốn tuyên bố Build L2/L3 cần provenance
  do control plane của hosted/hardened builder sinh ra độc lập với tenant.
- Ingress dùng certificate self-signed `aims.lab` phục vụ lab; production thật
  cần DNS và CA công cộng/nội bộ được client tin cậy. OpenSearch còn dùng demo
  security certificate.
- Worker1 đã mở rộng root lên 300 GiB và trả eviction reserve về 10%; production
  vẫn cần tách disk Longhorn khỏi OS/containerd trên cả ba worker.
