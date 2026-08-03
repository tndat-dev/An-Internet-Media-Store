# AIMS CKS hands-on lab

Namespace `cks-lab` tách bài thực hành khỏi `production`. Namespace dùng PSA
`baseline` ở mức Enforce và `restricted` ở mức Audit/Warn để có thể thử cả ca
được phép lẫn ca bị cảnh báo. `production` mới là nơi Restricted được Enforce.

## Cài guardrail

```bash
kubectl apply --server-side -f cks-lab/00-lab-guardrails.yaml
scripts/verify-cks-lab.sh
```

Verifier bao phủ sáu domain CKS hiện hành:

1. Cluster setup: NetworkPolicy, kube-bench/CIS và Gateway TLS.
2. Cluster hardening: least-privilege RBAC, tắt automount token và API audit.
3. System hardening: AppArmor, seccomp, gVisor và quyền file kubelet/etcd.
4. Microservice vulnerabilities: PSA Restricted, drop capabilities, non-root,
   read-only root filesystem và Istio Ambient mTLS STRICT.
5. Supply chain: Trivy, kubesec, Syft SBOM, Cosign/SLSA và Kyverno verifyImages.
6. Monitoring/runtime: Tetragon, Falco, audit log, Hubble và report Trivy.

## Bài tập nhanh

Kiểm tra RBAC của tài khoản lab:

```bash
kubectl auth can-i list pods \
  --as=system:serviceaccount:cks-lab:cks-student -n cks-lab
kubectl auth can-i get secrets \
  --as=system:serviceaccount:cks-lab:cks-student -n cks-lab
```

Chạy ba negative test bằng server dry-run. PSA chặn privileged Pod, Kyverno chặn
root filesystem ghi được của AIMS, Gatekeeper chặn privilege escalation và
thiếu capability drop-all. Không test nào tạo tài nguyên thật:

```bash
scripts/verify-cks-lab.sh --show-negative-test
```

Xem kết quả benchmark và runtime detection:

```bash
kubectl -n security-system logs -l app.kubernetes.io/name=kube-bench --tail=20
kubectl -n kube-system logs -l app.kubernetes.io/name=tetragon -c export-stdout --tail=30
kubectl -n falco logs -l app.kubernetes.io/name=falco -c falco --tail=30
```

Không chạy payload tấn công thật trong `production`. Khi cần thực hành Falco/
Tetragon, tạo pod ngắn hạn trong `cks-lab`, ghi nhận event rồi xóa pod.
