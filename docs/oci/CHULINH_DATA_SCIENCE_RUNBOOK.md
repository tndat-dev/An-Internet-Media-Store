# Runbook cho `chulinh` — OCI CLI, VS Code, Data Science và shared OKE

Tài liệu này dành cho người chưa từng dùng OCI. Thực hiện theo thứ tự từ trên
xuống. Môi trường hiện dùng region `ap-tokyo-1`, tenancy `svtechcloud`,
identity domain `Default` và user `chulinh`.

`chulinh` có hai nơi làm việc:

1. **OCI Data Science Project** trong `cmp-oe01-development`: nơi tổ chức model,
   job, notebook và các tài nguyên managed của OCI.
2. **Namespace `data-science` trên OKE**: nơi chạy Python Job, API inference,
   notebook container và dùng Kafka đang có của AIMS.

Hai nơi này dùng chung OE01 nhưng được giới hạn bằng OCI IAM, Kubernetes RBAC,
ResourceQuota và Kafka ACL. RBAC không phải tường lửa mạng: workload trong
`data-science` không được chủ động gọi service nội bộ của AIMS. Khi cần cách ly
network bắt buộc, quản trị viên phải triển khai network-policy provider trước.

Tạo một OCI Data Science Project không tạo VM và không phát sinh compute.
Notebook Session, Job Run và Model Deployment của OCI Data Science mới tạo
compute tính phí. Runbook này không tạo các runtime đó.

## 1. Thông số môi trường

| Thông số | Giá trị |
|---|---|
| Tenancy | `svtechcloud` |
| Identity domain | `Default` |
| Region | `ap-tokyo-1` |
| User | `chulinh` |
| Group | `Data-Science` |
| OE01 development compartment | `ocid1.compartment.oc1..aaaaaaaaegqh2wtkfrrtfgrxqnr23j3itdcseim65qhxtmjt57urhtd3quba` |
| OKE cluster | `oe01-oke-development` |
| OKE cluster OCID | `ocid1.cluster.oc1.ap-tokyo-1.aaaaaaaafciaf7nhd6hyx34gf42fyrnkc3iez3sbkijepxwzrcm5h2e7ot2q` |
| Kubernetes API | private `10.1.0.4:6443` |
| Kubernetes namespace | `data-science` |
| Kafka bootstrap | `aims-kafka-kafka-bootstrap.kafka.svc.cluster.local:9093` |

Không ghi password, API private key, Kafka private key hoặc kubeconfig vào Git.

## 2. Đăng nhập OCI lần đầu

1. Mở `https://cloud.oracle.com/?tenant=svtechcloud`.
2. Chọn identity domain **Default**.
3. Username là `chulinh`.
4. Dùng one-time password do quản trị viên cung cấp.
5. Đổi password ngay khi OCI yêu cầu.
6. Sau khi đổi password thành công, xóa file chứa one-time password khỏi máy và
   Recycle Bin.

MFA hiện không được bật cho user này. Sign-on policy có rule
`Password only for chulinh`, vì vậy `chulinh` không phải đăng ký Secure
Verification khi vào OCI Console. Rule MFA dành cho administrator vẫn có độ ưu
tiên cao hơn; nếu sau này cấp quyền administrator cho `chulinh`, MFA sẽ lại được
yêu cầu.

Nếu trình duyệt đang mở trang **Enable Secure Verification** từ trước khi rule
được tạo, sign out, đóng tab, đợi vài phút rồi đăng nhập lại bằng cửa sổ
InPrivate/Incognito. Không chia sẻ password hoặc API key qua chat, email hay
commit Git.

## 3. Cài công cụ trên Windows

Nên dùng **PowerShell** thay cho Command Prompt cổ điển. Tất cả command Windows
trong tài liệu được viết cho PowerShell và chạy được trong terminal của VS Code.
Nếu đang ở cửa sổ **Command Prompt**, gõ `powershell` rồi nhấn Enter trước khi
copy lệnh. Dấu backtick ở cuối dòng trong tài liệu là ký tự nối dòng của
PowerShell và không chạy trực tiếp trong Command Prompt.

### 3.1 Cài VS Code, Git và kubectl

Mở PowerShell bằng **Run as Administrator**:

```powershell
winget install --exact --id Microsoft.VisualStudioCode
winget install --exact --id Git.Git
winget install --exact --id Kubernetes.kubectl
```

Đóng rồi mở lại PowerShell, kiểm tra:

```powershell
git --version
kubectl version --client
ssh -V
code --version
```

Có thể cài extension bằng giao diện VS Code hoặc bằng command line:

```powershell
code --install-extension ms-python.python
code --install-extension ms-kubernetes-tools.vscode-kubernetes-tools
code --install-extension redhat.vscode-yaml
```

Nếu `ssh` chưa có, mở **Settings → System → Optional Features** và cài
**OpenSSH Client**.

### 3.2 Cài OCI CLI

Cách dễ nhất là tải MSI từ trang cài đặt chính thức của OCI CLI và chạy
installer. Có thể dùng PowerShell theo tài liệu Oracle:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.ps1 -OutFile install.ps1
./install.ps1 -AcceptAllDefaults
```

Đóng rồi mở terminal mới:

```powershell
oci --version
```

### 3.3 Extension VS Code

Cài các extension sau từ tab **Extensions**:

- Python của Microsoft;
- Kubernetes của Microsoft;
- YAML của Red Hat;
- Docker của Microsoft nếu làm việc với container image.

## 4. Cấu hình OCI CLI và API signing key

Trong PowerShell thường, không cần quyền Administrator:

```powershell
oci setup config
```

Nhập các giá trị:

```text
User OCID: ocid1.user.oc1..aaaaaaaath33u3ot7naidxpwnyl6fn6wywfot2vuhb3bdfgyn6bmkbbhtosa
Tenancy OCID: ocid1.tenancy.oc1..aaaaaaaafjci33w4ic37gzofaokwwiqdalu7httzktukw563fpzeuywv4s4a
Region: ap-tokyo-1
```

Chọn tạo API key mới và đặt passphrase cho private key. OCI CLI tạo file config
trong `%USERPROFILE%\.oci\config` cùng public/private key.

Upload public key:

1. OCI Console → biểu tượng profile → **My profile**.
2. **Tokens and keys → API keys → Add API key**.
3. Chọn **Paste public key**.
4. Mở file public key OCI CLI vừa tạo, copy toàn bộ nội dung rồi paste.
5. Chọn **Add**.

Kiểm tra CLI:

```powershell
$DevCompartment = "ocid1.compartment.oc1..aaaaaaaaegqh2wtkfrrtfgrxqnr23j3itdcseim65qhxtmjt57urhtd3quba"
oci data-science project list --compartment-id $DevCompartment --all --output table
```

Kết quả rỗng vẫn là thành công nếu chưa có Project. `NotAuthorizedOrNotFound`
nghĩa là API key/config hoặc policy chưa đúng.

## 5. Tạo và thao tác OCI Data Science Project

Tạo Project không tạo Notebook/VM:

```powershell
$DevCompartment = "ocid1.compartment.oc1..aaaaaaaaegqh2wtkfrrtfgrxqnr23j3itdcseim65qhxtmjt57urhtd3quba"
$ProjectId = oci data-science project create `
  --compartment-id $DevCompartment `
  --display-name "chulinh-data-science" `
  --description "Data Science project on OE01 shared platform" `
  --wait-for-state ACTIVE `
  --query "data.id" `
  --raw-output

$ProjectId
```

Liệt kê và xem Project:

```powershell
oci data-science project list --compartment-id $DevCompartment --all --output table
oci data-science project get --project-id $ProjectId --output table
```

Cập nhật mô tả:

```powershell
oci data-science project update `
  --project-id $ProjectId `
  --description "Shared OKE and OCI Data Science workspace for chulinh" `
  --force
```

Không tạo Notebook Session, Job Run, Model Deployment hoặc GPU khi chưa duyệt
shape và chi phí. Lệnh xóa Project chỉ dùng khi chắc chắn không còn tài nguyên
bên trong:

```powershell
# Không chạy trong thao tác hằng ngày:
# oci data-science project delete --project-id $ProjectId --force
```

Trên Console, đường dẫn tương ứng là **Analytics & AI → Machine Learning →
Data Science → Projects**, chọn compartment `cmp-oe01-development`.

## 6. Chuẩn bị SSH key cho private OKE

OKE không có public Kubernetes API. Kết nối local phải đi qua OCI Bastion.

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\oci-oke-ds" -C "chulinh-oke"
```

Đặt passphrase cho private key. Hai file được tạo:

- `oci-oke-ds`: private key, không chia sẻ;
- `oci-oke-ds.pub`: public key, dùng khi tạo Bastion session.

Lấy public IP hiện tại:

```powershell
curl.exe https://api.ipify.org
```

Gửi IP này cho quản trị viên để thêm đúng `/32` hoặc dải mạng phù hợp vào
allowlist của `oe01BastionV2`. Không mở Bastion cho `0.0.0.0/0`.

## 7. Tạo Bastion session tới Kubernetes API

Sau khi quản trị viên xác nhận IP đã nằm trong allowlist:

```powershell
$BastionId = "ocid1.bastion.oc1.ap-tokyo-1.amaaaaaantvo5cyagknlv743nkwoftb24w5fu2bbutrz3eiwt22pwx7lmkfa"
$SessionId = oci bastion session create-port-forwarding `
  --bastion-id $BastionId `
  --display-name "chulinh-oke-api" `
  --ssh-public-key-file "$env:USERPROFILE\.ssh\oci-oke-ds.pub" `
  --target-private-ip "10.1.0.4" `
  --target-port "6443" `
  --session-ttl "10800" `
  --wait-for-state SUCCEEDED `
  --query "data.resources[0].identifier" `
  --raw-output

$SessionId
```

Chờ session thành `ACTIVE`:

```powershell
oci bastion session get --session-id $SessionId `
  --query "data.lifecycle-state" --raw-output
```

Mở **một cửa sổ PowerShell riêng** và giữ cửa sổ đó chạy:

```powershell
$SessionId = "REPLACE_WITH_SESSION_OCID"
ssh -i "$env:USERPROFILE\.ssh\oci-oke-ds" `
  -N -L 26443:10.1.0.4:6443 -p 22 `
  "${SessionId}@host.bastion.ap-tokyo-1.oci.oraclecloud.com" `
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3
```

SSH đứng yên không in output là bình thường. Không đóng terminal tunnel khi đang
dùng kubectl hoặc VS Code Kubernetes.

## 8. Tạo kubeconfig cho `chulinh`

Trong cửa sổ PowerShell khác:

```powershell
$ClusterId = "ocid1.cluster.oc1.ap-tokyo-1.aaaaaaaafciaf7nhd6hyx34gf42fyrnkc3iez3sbkijepxwzrcm5h2e7ot2q"
$Kubeconfig = "$env:USERPROFILE\.kube\oe01-oke-development"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.kube" | Out-Null

oci ce cluster create-kubeconfig `
  --cluster-id $ClusterId `
  --file $Kubeconfig `
  --region ap-tokyo-1 `
  --token-version 2.0.0 `
  --kube-endpoint PRIVATE_ENDPOINT

$ClusterName = kubectl config view --kubeconfig $Kubeconfig `
  -o jsonpath='{.clusters[0].name}'
kubectl config set-cluster $ClusterName `
  --kubeconfig $Kubeconfig `
  --server=https://127.0.0.1:26443 `
  --tls-server-name=10.1.0.4

$env:KUBECONFIG = $Kubeconfig
kubectl config set-context --current --namespace=data-science
```

Không dùng kubeconfig của người khác. Token do OCI CLI sinh là token ngắn hạn
gắn với chính user `chulinh`.

Kiểm tra quyền mong đợi:

```powershell
kubectl get pods
kubectl get resourcequota
kubectl auth can-i create jobs
kubectl auth can-i create deployments
kubectl auth can-i get pods -n aims
kubectl auth can-i get secrets -n kafka
kubectl auth can-i create rolebindings
```

Kết quả đúng lần lượt là không lỗi, `yes`, `yes`, `no`, `no`, `no`. `kubectl
get nodes` bị từ chối có chủ đích vì `chulinh` không có quyền cấp cluster.

Không dùng `--as`, `--as-group` hoặc kubeconfig của quản trị viên trong công việc
hằng ngày. Những tùy chọn đó chỉ được quản trị viên dùng để kiểm thử RBAC.

## 9. Làm việc trong VS Code

Mở PowerShell tại thư mục source code:

```powershell
$env:KUBECONFIG = "$env:USERPROFILE\.kube\oe01-oke-development"
code .
```

Trong VS Code:

1. **Terminal → New Terminal**.
2. Chạy `$env:KUBECONFIG = "$env:USERPROFILE\.kube\oe01-oke-development"`.
3. Chạy `kubectl config current-context` và `kubectl get pods`.
4. Extension Kubernetes sẽ dùng kubeconfig này để hiển thị namespace.
5. Chỉ thao tác namespace `data-science`.

Nếu deploy Jupyter trong OKE, không tạo public LoadBalancer. Dùng port-forward:

```powershell
kubectl port-forward pod/REPLACE_JUPYTER_POD 8888:8888
```

Sau đó mở `http://127.0.0.1:8888` trên trình duyệt. Token Jupyter lấy từ log
Pod, không commit token.

## 10. Chạy Job Python đầu tiên trên OKE

Tạo file `ds-smoke-job.yaml` trong VS Code:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: ds-smoke
  namespace: data-science
spec:
  ttlSecondsAfterFinished: 600
  template:
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      containers:
        - name: python
          image: python:3.12-slim
          command: ["python", "-c"]
          args:
            - |
              import platform
              print("Data Science workspace is ready")
              print(platform.python_version())
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
            runAsNonRoot: true
            runAsUser: 10001
            seccompProfile:
              type: RuntimeDefault
```

Apply và đọc log:

```powershell
kubectl apply -f .\ds-smoke-job.yaml
kubectl wait --for=condition=complete job/ds-smoke --timeout=180s
kubectl logs job/ds-smoke
kubectl delete job ds-smoke
```

## 11. Dùng Kafka chung với AIMS

Data Science dùng broker hiện có nhưng có certificate, ACL và topic riêng:

```text
Bootstrap: aims-kafka-kafka-bootstrap.kafka.svc.cluster.local:9093
TLS Secret: data-science-kafka-tls
Topics:
  ds.feature.events.v1
  ds.training.jobs.v1
  ds.predictions.v1
Consumer group prefix: ds.
```

Mount certificate vào Pod:

```yaml
volumes:
  - name: kafka-tls
    secret:
      secretName: data-science-kafka-tls
containers:
  - name: app
    volumeMounts:
      - name: kafka-tls
        mountPath: /var/run/data-science-kafka
        readOnly: true
```

Các file cần dùng là `ca.crt`, `user.crt` và `user.key`. Kafka client phải bật
TLS client certificate authentication. Không dùng secret `aims-services` và
không xin quyền vào namespace `kafka`.

## 12. Quota và giới hạn

Namespace hiện có giới hạn:

| Resource | Giới hạn |
|---|---:|
| Tổng CPU request | 4 CPU |
| Tổng CPU limit | 10 CPU |
| Tổng memory request | 24 GiB |
| Tổng memory limit | 48 GiB |
| Một container tối đa | 6 CPU / 24 GiB |
| Pod | 20 |
| PVC | 4, tổng 200 GiB |
| LoadBalancer/NodePort | 0 |

Cụm hiện chỉ có worker CPU. Deep learning CPU chạy được nhưng chậm. GPU chỉ có
khi quản trị viên bổ sung GPU node pool hoặc duyệt OCI Data Science GPU runtime;
hai lựa chọn đó đều tạo thêm compute và chi phí.

## 13. Troubleshooting theo thứ tự

### OCI CLI báo `NotAuthorizedOrNotFound`

1. Chạy `oci --version`.
2. Mở `%USERPROFILE%\.oci\config`, kiểm tra region, tenancy OCID và user OCID.
3. Kiểm tra public API key đã upload đúng fingerprint.
4. Đợi IAM policy propagation vài phút rồi thử lại.

### SSH đóng ngay hoặc timeout

1. Chạy `curl.exe https://api.ipify.org`.
2. Nhờ admin xác nhận IP nằm trong Bastion allowlist.
3. Kiểm tra Bastion session `ACTIVE` và chưa hết TTL.
4. Kiểm tra đúng private key tương ứng public key của session.
5. Giữ `ServerAliveInterval=30` trong SSH command.

### kubectl báo connection refused `127.0.0.1:26443`

Tunnel SSH chưa chạy hoặc đã hết hạn. Tạo session mới và mở lại terminal tunnel.

### kubectl báo `Forbidden`

Kiểm tra namespace hiện tại:

```powershell
kubectl config view --minify -o jsonpath='{..namespace}'
kubectl config set-context --current --namespace=data-science
```

`Forbidden` khi đọc `aims`, `kafka`, `data`, node hoặc RBAC là kết quả đúng của
thiết kế phân quyền.

### Pod Pending

```powershell
kubectl describe pod REPLACE_POD
kubectl get resourcequota
kubectl get pvc
```

Kiểm tra quota, CPU/memory request, PVC và image trước khi yêu cầu scale cluster.

## 14. Kết thúc phiên làm việc

1. Dừng port-forward/Jupyter bằng `Ctrl+C`.
2. Dừng SSH tunnel bằng `Ctrl+C`.
3. Xóa Bastion session nếu không dùng nữa:

```powershell
oci bastion session delete --session-id $SessionId --force
```

4. Không xóa Project, PVC, Kafka topic hoặc model nếu chưa kiểm tra dữ liệu cần
   giữ.

## 15. Tài liệu chính thức

- [Cài OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)
- [Thiết lập quyền truy cập OKE](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengdownloadkubeconfigfile.htm)
- [Bastion cho private OKE](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengsettingupbastion.htm)
- [Tạo OCI Data Science Project](https://docs.oracle.com/en-us/iaas/Content/data-science/using/create-projects.htm)
