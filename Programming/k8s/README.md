# AIMS Kubernetes production-like platform

Thư mục này chứa desired state và runbook cho AIMS trong namespace
`production`. Trạng thái nghiệm thu gần nhất 03/08/2026: 3 control-plane + 3 worker,
9 Argo Rollout/18 pod microservice và 2 frontend pod, CloudNativePG 3/3, Kafka
KRaft, RabbitMQ, Redis, MinIO, OpenSearch và backup Velero hoạt động. PSA
Restricted được Enforce; verifier AIMS và CKS đều trả exit code 0.

Báo cáo kiến trúc, lý thuyết, triển khai và sự cố đầy đủ nằm tại
[`../../AIMS_DEPLOYMENT_REPORT.md`](../../AIMS_DEPLOYMENT_REPORT.md).

## Cấu trúc

- `aims-chart/`: 9 microservice dưới dạng Argo Rollout, frontend Deployment,
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
- `scripts/`: cài node profile/gVisor, reconcile, backup và nghiệm thu.

Manifest monolith `aims-production.yaml` đã được loại khỏi desired state để
không thể apply nhầm PostgreSQL/backend/VirtualService cũ vào production.

## Điều kiện tiên quyết

Cụm phải có `kubectl`, `helm`, `jq` và các operator/CRD tương ứng: Argo
Rollouts, CloudNativePG, Strimzi, RabbitMQ Cluster Operator, Redis Operator,
MinIO Operator, Kyverno, Gatekeeper, External Secrets và Velero. Secret thật
phải nằm trong Vault; không commit mật khẩu, token, private key hoặc `.env`.

Image mặc định `aims-backend:prod-sim` phục vụ lab và được nạp cục bộ trên ba
worker. Frontend lab nằm trên worker3/worker4; chạy
`scripts/label-lab-frontend-nodes.sh k8s-worker3.local k8s-worker4.local` trước
reconcile. Khi CI publish registry digest, job GitOps cập nhật cả backend lẫn
frontend và xóa nodeSelector lab.

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

Apply Gatekeeper theo thứ tự ConstraintTemplate trước Constraint. Constraint
runtime hiện dùng `deny`; Kyverno runtime policy cũng Enforce. Cosign/SLSA vẫn
Audit riêng cho image `prod-sim` chưa ký. Không bật Argo CD `prune` cho đến khi
repo Git chứa đầy đủ resource đang quản lý.

## Trạng thái mã CI/CD và GitOps

Bộ mã local đã có Dockerfile backend/frontend, Helm chart AIMS, toàn bộ manifest
platform/CKS, script vận hành và `.gitlab-ci.yml`. Pipeline định nghĩa đủ luồng
`test → build → scan → attest → verify → gitops`, gồm Trivy, kubesec, Syft SBOM,
SLSA provenance, Cosign keyless sign/attest/verify và cập nhật image digest vào
Helm values. `argocd-application.yaml` trỏ tới repository bàn giao
`tndat-dev/An-Internet-Media-Store`, có automated sync/prune/self-heal nhưng chỉ
được apply sau khi commit đã có trên `main`. `scripts/install-cicd-controllers.sh`
tái tạo đúng Argo CD/Argo Rollouts đang chạy; chỉ bật Application khi
`ENABLE_AIMS_GITOPS=true` và script xác nhận chart đã tồn tại trên Git remote.

Repository bàn giao là GitHub, còn engine CI được yêu cầu là GitLab CI. Để chạy
end-to-end, import/mirror repository vào GitLab, cấu hình runner/registry/OIDC và
đặt masked variable `GITOPS_PUSH_URL` là URL xác thực để job GitOps đẩy digest đã
verify về GitHub; `GITOPS_TARGET_BRANCH` mặc định là nhánh mặc định. Identity và
registry trong policy cũng phải khớp project thật. Secret, token, password và
private key không thuộc source code; chúng phải được nạp vào Vault/GitLab masked
variables.

Trạng thái live 03/08/2026: Argo CD 3.4.5 và Argo Rollouts 1.9.1 đều khỏe; 9/9
Rollout AIMS `Healthy`. `Application/aims-production` đã đọc chart trên GitHub
`main`, automated sync/prune/self-heal; cụm chưa cài GitLab Runner. Argo CD UI/API
được expose NodePort `30081`, Rollouts Dashboard `30100`. GitLab CI có thể dùng
shared runner bên ngoài; nếu dùng self-managed runner trong cụm thì phải tạo
runner authentication token/Secret trước, không lưu token trong repository.

Kiểm tra local sau khi sửa layout pipeline: backend `207 passed`, frontend lint
và typecheck PASS, YAML pipeline parse PASS, Docker build backend/frontend PASS,
Helm lint/render PASS. `config/settings.py` giữ environment làm nguồn ưu tiên để
GitLab `DATABASE_URL`/Vault Secret không bị `.env.local` ghi đè.

## Nghiệm thu

```bash
scripts/verify-aims.sh
scripts/verify-cks-lab.sh
```

Script trả non-zero nếu sai bất kỳ tiêu chí nào: topology 3 CP + 3 worker,
node Ready/không DiskPressure, 9 Rollout/18 pod cân bằng với max skew 1,
CNPG/Kafka/RabbitMQ/MinIO/OpenSearch, Vault/Velero, gVisor/Localhost profiles,
frontend Helm/read-only, HTTP+HTTPS Gateway, RBAC, Kyverno/Gatekeeper,
kube-bench/runtime detector và không còn controller legacy. Có thể đổi topology bằng `EXPECTED_READY_NODES`,
`EXPECTED_CONTROL_PLANES`, `EXPECTED_WORKERS` khi join thêm node.

Nếu external Sentinel validation bật binding
`sentinel-experiment-resource-lock`, verifier ghi riêng bốn controller đo tải là
`INFO` và cleanup bảo toàn chúng. Khi binding biến mất, cùng các controller đó
trở lại tiêu chí legacy và phải được `cleanup-production-legacy.sh` xóa.

## Supply chain SLSA

`.gitlab-ci.yml` thực hiện test → build → Trivy + kubesec → Syft CycloneDX →
SLSA provenance → Cosign keyless sign/attest → verify → GitOps. Image được ký
theo digest, Fulcio certificate gắn với GitLab pipeline identity và entry được
ghi vào Rekor. Hai attestation bắt buộc là:

- `https://slsa.dev/provenance/v1` với build definition, source revision,
  builder/run metadata và digest SBOM trong resolved dependency/byproduct;
- `https://cyclonedx.org/schema` chứa SBOM đầy đủ.

Policy Kyverno đang ở `Audit` vì image lab `aims-backend:prod-sim` chưa ở
registry; mode này dùng `mutateDigest=false`, `verifyDigest=true`. Sau pipeline
registry đầu tiên thành công và `cosign verify*` pass, đổi
`validationFailureAction` thành `Enforce` và bật `mutateDigest=true`. Registry
path và GitLab identity
trong `22-supply-chain-policy.yaml` phải khớp project thực tế nếu fork repo.

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

Restore drill metadata cô lập, mặc định lấy backup nghiệm thu và chỉ phục hồi
ConfigMap vào namespace tạm `production-drill`:

```bash
scripts/velero-config-restore-drill.sh
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
- GitLab CI/Argo CD cần repository, runner, registry và credential thật để chạy
  end-to-end.
- SLSA predicate hiện do job trong repository tạo nên chỉ được tuyên bố là
  provenance tương thích SLSA Build L1; muốn tuyên bố Build L2/L3 cần provenance
  do control plane của hosted/hardened builder sinh ra độc lập với tenant.
- Ingress dùng certificate self-signed `aims.lab` phục vụ lab; production thật
  cần DNS và CA công cộng/nội bộ được client tin cậy. OpenSearch còn dùng demo
  security certificate.
- Worker1 đã mở rộng root lên 300 GiB và trả eviction reserve về 10%; production
  vẫn cần tách disk Longhorn khỏi OS/containerd trên cả ba worker.
