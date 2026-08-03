# BÁO CÁO THỰC HÀNH CKS TRÊN CỤM AIMS

**Phạm vi:** cụm kubeadm production-like phục vụ học tập, không tuyên bố
enterprise production  
**Topology:** 3 control-plane + 3 worker, Kubernetes v1.34.10  
**Ngày nghiệm thu:** 01/08/2026

## 1. Mục tiêu

Bộ thực hành dùng chính AIMS để học bảo mật build, deploy và runtime, nhưng tách
payload thử nghiệm khỏi namespace `production`. Linux Foundation hiện chia CKS
thành sáu domain: Cluster Setup 15%, Cluster Hardening 15%, System Hardening
10%, Minimize Microservice Vulnerabilities 20%, Supply Chain Security 20%, và
Monitoring/Logging/Runtime Security 20%. Trang chứng chỉ hiện ghi môi trường thi
Kubernetes v1.35; cụm lab v1.34.10 đủ gần để luyện workflow và cú pháp.

Nguồn chuẩn:

- [CKS Domains & Competencies](https://training.linuxfoundation.org/certification/certified-kubernetes-security-specialist/)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Kubernetes Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/)
- [Kyverno Sigstore verification](https://kyverno.io/docs/policy-types/cluster-policy/verify-images/sigstore/)

## 2. Mô hình namespace

`production` Enforce `restricted:latest`, đồng thời audit/warn cùng profile.
`cks-lab` Enforce Baseline nhưng Audit/Warn Restricted để người học quan sát
khác biệt giữa hai mức mà không chạy payload lỗi trong production.

Guardrail `cks-lab` gồm:

- default ServiceAccount không automount token;
- ServiceAccount `cks-student` chỉ bind Role đọc pod/log/configmap/event;
- không được đọc Secret hoặc tạo workload;
- ResourceQuota và LimitRange;
- default-deny ingress/egress;
- DNS egress chỉ dành cho pod có label rõ ràng.

## 3. Ánh xạ sáu domain CKS

### 3.1 Cluster Setup — 15%

| Năng lực | Thực hành trong AIMS | Bằng chứng |
|---|---|---|
| NetworkPolicy | Cilium L3-L7, default deny lab, HBONE 15008 | CNP `aims-zero-trust` Valid=True |
| CIS benchmark | kube-bench v0.15.5, CIS 1.12 | 3 CP + 3 worker pod Ready |
| Ingress TLS | Gateway API/Istio, cert-manager | HTTP 31088, HTTPS 32725, TLS 200 |
| Binary/config review | kube-bench và permission hardening | worker 0 FAIL; CP 2 finding chấp nhận/node |

TLS dùng self-signed certificate cho `aims.lab`, phù hợp lab. Production thật
phải dùng DNS và CA được client tin cậy.

### 3.2 Cluster Hardening — 15%

- Role/RoleBinding tách observer, operator và CI/CD deployer.
- Developer/CKS student không đọc Secret.
- ServiceAccount ứng dụng và CI/CD không automount API token nếu không cần.
- kube-apiserver tắt profiling và bound token extension.
- audit policy ghi hoạt động RBAC/admission/production, không ghi body Secret.
- audit rotate 100 MiB, 10 backup, tối đa 30 ngày trên cả ba API server.

OIDC Keycloak cho ứng dụng đã có; OIDC cho `kubectl` chưa bật vì issuer lab chưa
có HTTPS/CA trust ổn định. Đây là giới hạn được ghi nhận, không giả lập là đã
hoàn thành.

### 3.3 System Hardening — 10%

- kubelet config/unit/drop-in mode 0600; thư mục etcd mode 0700.
- seccomp RuntimeDefault cho workload thường, Localhost cho telemetry.
- AppArmor `aims-restricted` cài trên ba worker.
- gVisor RuntimeClass `sandbox` cho payment và notification.
- mọi AIMS web container drop `ALL`, non-root, không privilege escalation.
- kube-bench được ghim Kubernetes 1.34 để tránh fallback benchmark 1.18 sai.

Hai finding control-plane được chấp nhận có chủ đích: etcd static pod kubeadm
chạy root nên volume owner `root:root`; kubelet serving certificate dùng CA cục
bộ của node nên không ép cluster CA chỉ để làm đẹp điểm benchmark.

### 3.4 Minimize Microservice Vulnerabilities — 20%

- PSA Restricted Enforce từ built-in admission.
- Kyverno `production-runtime-hardening` Enforce non-root, seccomp và read-only
  root filesystem cho backend/frontend AIMS.
- Gatekeeper Rego constraint dùng `deny` cho privilege escalation và drop-all.
- Istio Ambient `PeerAuthentication STRICT` cung cấp mTLS; waypoint xử lý L7.
- payment/notification chạy gVisor; telemetry dùng Localhost profiles.
- 18 backend pod và 2 frontend pod Ready sau hardening.

Ba negative test dùng `kubectl apply --dry-run=server`: PSA chặn privileged Pod,
Kyverno chặn AIMS container có rootfs ghi được, Gatekeeper chặn privilege
escalation và thiếu drop-all. Admission từ chối nhưng không tạo tài nguyên thật.

### 3.5 Supply Chain Security — 20%

Pipeline trong `Programming/.gitlab-ci.yml`:

1. pytest, lint/typecheck, Helm render;
2. build/push backend và frontend;
3. Trivy image/config, kubesec PodSpec;
4. Syft tạo CycloneDX SBOM;
5. tạo SLSA provenance v1 chứa source/build/SBOM digest;
6. Cosign keyless ký image và attest CycloneDX + SLSA qua GitLab OIDC;
7. verify signature/attestation trước GitOps commit;
8. cập nhật cả hai image thành immutable digest trong Helm.

Kyverno verifyImages kiểm tra GitLab identity, Rekor, digest, SLSA và CycloneDX.
Policy đang Audit vì image `prod-sim` chỉ nằm trong containerd node và chưa ký.
Đây là giới hạn đúng của lab; chỉ chuyển Enforce sau pipeline registry thật.

### 3.6 Monitoring, Logging and Runtime Security — 20%

- Tetragon chạy 6/6 node và có TracingPolicy theo dõi file nhạy cảm/execve.
- Falco chạy 6/6 node để luyện rule và phân tích alert CKS.
- Kubernetes audit logging hoạt động trên ba API server.
- Cilium/Hubble cung cấp flow/verdict; OpenTelemetry/Loki/Tempo lưu telemetry.
- Trivy Operator ClientServer tạo VulnerabilityReport/ConfigAuditReport/SBOM.
- `security-telemetry-service` có đường Kafka/OpenSearch để tái dùng
  LSTM/Isolation Forest của capstone.

## 4. Lệnh thực hành

```bash
cd Programming/k8s
kubectl apply --server-side -f cks-lab/00-lab-guardrails.yaml
scripts/verify-cks-lab.sh
scripts/verify-cks-lab.sh --show-negative-test
```

Kiểm tra RBAC thủ công:

```bash
kubectl auth can-i list pods \
  --as=system:serviceaccount:cks-lab:cks-student -n cks-lab
kubectl auth can-i get secrets \
  --as=system:serviceaccount:cks-lab:cks-student -n cks-lab
```

Kiểm tra admission/runtime:

```bash
kubectl get ns production --show-labels
kubectl get clusterpolicy
kubectl get k8srequiredruntimehardening
kubectl -n security-system logs -l app.kubernetes.io/component=worker-benchmark
kubectl -n kube-system get ds tetragon
kubectl -n falco get ds falco
kubectl get vulnerabilityreports -A
```

## 5. Kết quả nghiệm thu live

| Kiểm tra | Kết quả |
|---|---|
| PSA production | Restricted Enforce |
| RBAC student đọc pod / Secret | yes / no |
| PSA / Kyverno / Gatekeeper negative test | cả ba bị đúng admission layer từ chối |
| Cilium policy / mTLS | Valid=True / STRICT |
| Ingress certificate / HTTPS | Ready=True / HTTP 200 |
| kube-bench coverage | 3 CP + 3 worker |
| Tetragon / Falco | 6/6 + 6/6 node |
| Trivy report | có report, 0 failed scan Job |
| AIMS runtime policy | Kyverno Enforce + Gatekeeper deny |
| Cluster health | 0 bad pod, 0 incomplete controller |
| Backup sau hardening | Completed 1.102/1.102, 0 error |
| Restore drill | Completed, 11 ConfigMap; 0 Pod/Secret/PVC/controller; namespace đã cleanup |
| Kyverno PolicyReport fail | 0 |

`scripts/verify-cks-lab.sh` và `scripts/verify-aims.sh` đều trả exit code 0.

Restore drill dùng `scripts/velero-config-restore-drill.sh`. Runbook chỉ cho phép
namespace tạm chưa tồn tại, áp PSA Restricted và lọc `includedResources` còn
ConfigMap; đây là cách luyện backup/restore mà không đưa Secret hay workload
không tin cậy trở lại cluster. Bằng chứng live là Restore
`aims-config-drill-20260801113325`, phase `Completed`; namespace
`production-drill` không còn sau kiểm tra.

External Sentinel validation còn giữ một `ValidatingAdmissionPolicy` khóa xóa
bốn workload đo tải. Đây là bài đo đang hoạt động, không phải admission lỗi;
cleanup không phá khóa và verifier chỉ loại trừ chúng trong lúc binding tồn tại.

## 6. Giới hạn lab

- Image AIMS là `prod-sim` node-local; Cosign policy chưa thể Enforce thật.
- Keycloak chưa làm issuer HTTPS cho kube-apiserver OIDC.
- etcd encryption-at-rest chưa được bật; Secret ứng dụng dùng Vault/ESO nhưng
  Kubernetes Secret vẫn cần thiết kế encryption provider cho production thật.
- TLS ingress self-signed; OpenSearch còn demo certificate.
- MinIO backup nằm cùng cluster, chưa phải off-site DR; drill hiện mới kiểm tra
  metadata, chưa kiểm tra stateful data/PITR.

Các giới hạn này không cản mục tiêu thực hành CKS, nhưng phải giải quyết trước
khi tuyên bố hệ thống production thực tế.
