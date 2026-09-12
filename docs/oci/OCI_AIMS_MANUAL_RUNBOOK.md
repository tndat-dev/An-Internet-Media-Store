# OCI Landing Zone cho AIMS — Runbook triển khai thủ công

**Thiết kế:** Multi-OE Generic v1 · Hub B · Regional WAF · OKE 3 worker · Kafka KRaft · PostgreSQL · Jenkins/Argo CD.  
**Ngày biên soạn:** 09/09/2026. **Trạng thái:** hướng dẫn triển khai kiến trúc đích; chưa phải biên bản triển khai thành công trên tenancy.  
**Công cụ:** OCI Console, OCI CLI, kubectl, Helm. Không dùng Terraform hoặc Resource Manager stack.

Tài liệu này dành cho người triển khai lab từ đầu. Công việc tách microservice được thực hiện riêng; ở đây coi image, migration và contract của từng service là đầu vào của giai đoạn ứng dụng. Các lệnh chỉ được thực hiện khi người vận hành chạy chúng. Giá trị `REPLACE_*` phải được thay bằng dữ liệu thật.

Sơ đồ đi kèm: [OCI_AIMS_ARCHITECTURE.drawio](OCI_AIMS_ARCHITECTURE.drawio) · [Bản PDF ba trang](OCI_AIMS_ARCHITECTURE.pdf). Sơ đồ có ba trang: tổng thể, routing và nền tảng ứng dụng. Các quyết định riêng của lab được ghi rõ; chúng không phải yêu cầu bắt buộc của blueprint Oracle.

## Mục lục

1. [Khái niệm cơ bản](#1-khái-niệm-cơ-bản)
2. [Lựa chọn kiến trúc](#2-lựa-chọn-kiến-trúc)
3. [Thông số và kế hoạch tài nguyên](#3-thông-số-và-kế-hoạch-tài-nguyên)
4. [Chuẩn bị quyền và công cụ](#4-chuẩn-bị-quyền-và-công-cụ)
5. [Compartment và IAM](#5-compartment-và-iam)
6. [Cloud Guard, Vault và Security Zones](#6-cloud-guard-vault-và-security-zones)
7. [Tạo mạng Hub và Spoke](#7-tạo-mạng-hub-và-spoke)
8. [Firewall và bảng route hai chiều](#8-firewall-và-bảng-route-hai-chiều)
9. [NSG và security list](#9-nsg-và-security-list)
10. [Tạo OKE và Bastion](#10-tạo-oke-và-bastion)
11. [Storage, namespace và ingress](#11-storage-namespace-và-ingress)
12. [Web smoke test, Public LB, DNS và WAF](#12-web-smoke-test-public-lb-dns-và-waf)
13. [PostgreSQL](#13-postgresql)
14. [Kafka KRaft](#14-kafka-kraft)
15. [Ứng dụng AIMS](#15-ứng-dụng-aims)
16. [Jenkins và Argo CD](#16-jenkins-và-argo-cd)
17. [Backup và vận hành](#17-backup-và-vận-hành)
18. [Nghiệm thu và xử lý lỗi](#18-nghiệm-thu-và-xử-lý-lỗi)
19. [Dọn dẹp](#19-dọn-dẹp)
20. [Nguồn và cách sử dụng sơ đồ](#20-nguồn-và-cách-sử-dụng-sơ-đồ)

## 1. Khái niệm cơ bản

| Khái niệm | Hiểu đơn giản và áp dụng trong lab |
|---|---|
| Landing Zone | Nền quản trị gồm IAM, mạng, bảo mật, logging và tổ chức tài nguyên trước khi chạy ứng dụng. Không chỉ là một VCN. |
| Tenancy | Phạm vi tài khoản OCI cấp cao nhất của tổ chức. Lab dùng một tenancy có sẵn. |
| Operating Entity — OE | Đơn vị vận hành có quyền, môi trường và workload riêng. OE01 vận hành AIMS. |
| Compartment | Nhóm tài nguyên phục vụ phân quyền và quản trị. Không phải subnet, không tự tạo cách ly mạng. |
| Identity domain / group / policy | Domain quản lý danh tính; group gom người dùng; IAM policy cấp quyền gọi API OCI. |
| Resource principal | Danh tính của dịch vụ/tài nguyên OCI khi gọi dịch vụ khác. Khác danh tính người dùng và Kubernetes ServiceAccount. |
| Region / AD / FD | Region là khu vực; Availability Domain là miền hạ tầng độc lập; Fault Domain giúp phân tán lỗi trong một AD. |
| VCN / subnet / CIDR | Mạng ảo, mạng con và dải địa chỉ. Hub dùng `10.0.0.0/16`, Spoke dùng `10.1.0.0/16`. |
| Public / private subnet | Subnet public cho phép public IP; muốn truy cập Internet vẫn cần route và security rules. Private subnet không gán public IP. |
| IGW / NAT Gateway | IGW phục vụ tài nguyên public; NAT cho kết nối Internet do tài nguyên private chủ động mở và traffic trả lời. |
| Service Gateway — SGW | Truy cập Oracle Services Network bằng service CIDR của region, không đi Internet công cộng. |
| DRG | Router kết nối các VCN và mạng ngoài OCI. Bảng route DRG chọn attachment tiếp theo, không trỏ thẳng vào firewall IP. |
| VCN ingress route table | Bảng route xử lý gói đi vào VCN từ attachment/gateway; dùng để đưa gói tới firewall. |
| NSG / security list | NSG áp lên VNIC/tài nguyên thành viên; security list áp theo subnet. Các allow rule kết hợp cộng dồn. |
| Stateful / stateless | Stateful theo dõi kết nối và cho phép chiều trả lời; stateless yêu cầu rule cho cả hai chiều. |
| Hub-Spoke | Mạng hub cung cấp dịch vụ chung, các spoke chứa workload. Route quyết định traffic nào thực sự qua hub. |
| Network Firewall | Kiểm soát kết nối và inspection trên đường mạng; chỉ nhìn thấy traffic được route qua nó. |
| Load Balancer — LB | Proxy nhận một kết nối từ client rồi mở kết nối khác tới backend. Cần kiểm tra hai nửa kết nối độc lập. |
| Regional WAF | Policy HTTP được thực thi tại OCI Load Balancer, lọc request độc hại và giới hạn tần suất. |
| Cloud Guard | Phát hiện cấu hình/hoạt động có vấn đề theo target và detector; responder xử lý vấn đề. |
| Security Zone | Kiểm tra policy khi tạo/cập nhật tài nguyên và từ chối thao tác vi phạm. Không thay thế IAM hay NetworkPolicy. |
| Vault / KMS | Quản lý key mã hóa và secrets trên OCI. OCI Vault khác HashiCorp Vault chạy trong cluster. |
| OKE | Kubernetes do OCI quản lý control plane; ba worker trong lab là ba VM chạy Pod, không phải ba control-plane node. |
| Pod / Deployment / Service | Pod chạy container; Deployment duy trì replica; Service cung cấp endpoint ổn định tới các Pod. |
| Ingress controller / API gateway | Controller đưa HTTP vào Kubernetes; API gateway của AIMS làm routing nghiệp vụ, JWT và giới hạn ở tầng ứng dụng. |
| PVC / StorageClass / CSI | PVC yêu cầu ổ lưu trữ; StorageClass quy định cách cấp ổ; CSI kết nối OCI Block Volume với Pod. |
| Kafka topic / partition / group | Topic phân loại event; partition giữ thứ tự cục bộ; consumer group chia công việc giữa consumer. |
| KRaft / replication / ISR | KRaft quản lý metadata Kafka; replica sao chép dữ liệu; ISR là tập replica đang theo kịp. |
| Saga / outbox / idempotency | Chuỗi transaction cục bộ có bù trừ; outbox tránh mất event sau commit DB; idempotency tránh tác dụng lặp. |
| CI / GitOps / CD | CI kiểm tra và build; Git lưu trạng thái mong muốn; Argo CD đồng bộ cluster về trạng thái đó. |

Ví dụ: NSG cho phép TCP/80 không đảm bảo web chạy nếu route sai; Pod Running không đảm bảo Kafka consumer đã kết nối; ba bản sao PostgreSQL không thay thế backup ngoài cluster.

## 2. Lựa chọn kiến trúc

### 2.1 So sánh kịch bản Landing Zone

| Tiêu chí | One-OE | Multi-OE | Multi-tenancy |
|---|---|---|---|
| Tổ chức | Một đơn vị | Nhiều đơn vị trong một tenancy | Nhiều tenancy |
| Cách ly quản trị | IAM/compartment | IAM/compartment riêng từng OE | Ranh giới tenancy và IAM riêng |
| Dịch vụ chung | Tổ chức theo nhu cầu OE | Network/security dùng chung rõ ràng | Phải thiết kế chia sẻ hoặc lặp lại giữa tenancy |
| Phù hợp | Một dự án/doanh nghiệp | Tổ chức có nhiều bộ phận | Nhu cầu pháp lý, sở hữu hoặc cách ly mạnh |
| Lab này | Đủ chức năng | Chọn để trình diễn mô hình mở rộng | Chưa cần |

**Quyết định của lab:** dùng cách tổ chức Multi-OE Generic v1, triển khai OE01 trước. Một OE không chứng minh được cách ly giữa hai OE; mục 18 có phép thử mở rộng OE02. One-OE vẫn có thể dùng Hub-Spoke. Tên compartment theo mẫu chỉ là quy ước, không phải điều kiện kỹ thuật OCI. [Blueprints Open LZ](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities)

### 2.2 So sánh Hub

| Model | Firewall | Khi phù hợp |
|---|---|---|
| A | Hai OCI Network Firewall | Cần phân tách kiểm soát DMZ/inbound khỏi internal/outbound |
| B | Một OCI Network Firewall | Cần inspection tập trung, ít thành phần vận hành |
| C | Firewall bên thứ ba Active/Active | Có tiêu chuẩn thiết bị/license tương ứng |
| D | Firewall bên thứ ba Active/Passive | Có nhu cầu HA theo active/passive |
| E | Không Network Firewall | Nhu cầu kiểm soát bằng routing/security rules phù hợp |

Chọn **Hub B** vì đủ cho một spoke AIMS và giúp kiểm chứng luồng dễ hơn. Đây là managed firewall; một resource không đồng nghĩa một VM firewall tự quản. Hub B chỉ thấy nguồn backend từ Public LB đối với inbound web. Hub A đáng cân nhắc khi cần inspection trước Public LB; không suy ra throughput gấp đôi chỉ từ số firewall. [Hub menu](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/tree/master/addons/oci-hub-models), [Hub A](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/blob/master/addons/oci-hub-models/hub_a/readme.md), [Hub B](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/blob/master/addons/oci-hub-models/hub_b/readme.md)

### 2.3 Luồng chốt cho lab

```text
Web: Internet → IGW → Hub Public LB [TLS + Regional WAF]
     → OCI Network Firewall → DRG → Spoke Private LB → Traefik
       ├─ /      → frontend
       └─ /api/  → api-gateway → service nghiệp vụ

Internet egress: worker/pod → DRG → Hub Firewall → Hub NAT → Internet
Oracle services: Spoke → Spoke SGW → Oracle Services Network
Admin: laptop → OCI Bastion session → private API endpoint:6443
Data: services → PostgreSQL; services ↔ Kafka (TLS, ACL)
CI/CD: GitHub → Jenkins → GHCR; Jenkins → GitOps branch ← Argo CD → OKE
```

Spoke SGW là **điều chỉnh riêng của lab** để OKE/Bastion/Object Storage truy cập Oracle services trực tiếp. Luồng này được ghi nhận là ngoại lệ khỏi inspection hub; không tuyên bố mọi egress đều qua firewall. Trong cùng Spoke, NSG và Kubernetes NetworkPolicy kiểm soát traffic nội bộ.

**TLS baseline:** HTTPS client→Public LB; HTTP/80 trên đoạn private LB backend và ingress để đơn giản hóa lab và kiểm chứng IDS. Kafka dùng TLS; PostgreSQL dùng TLS. Đây không phải TLS end-to-end cho web. Khi nâng cấp, bật backend TLS và xác thực CA ở cả hai LB/ingress; firewall không tự đọc HTTPS đã mã hóa nếu chưa thiết kế decryption. Không dùng certificate tự ký ở endpoint Internet.

## 3. Thông số và kế hoạch tài nguyên

### 3.1 Cây compartment và ownership

```text
tenancy
└─ mb-home-cmp                      # giả định parent dùng chung có sẵn
   └─ tndat-lz-cmp                  # toàn bộ resource lab
      ├─ cmp-network               # Hub VCN, IGW/NAT, DRG, FW, Public LB
      ├─ cmp-security              # WAF policy, Bastion resource, logs, Vault/key
      │  └─ cmp-backup              # private Object Storage backup; custom SZ
      ├─ cmp-security-test          # resource rỗng dùng kiểm thử Cloud Guard
      └─ cmp-oe1                    # custom SZ chung của OE01
         ├─ cmp-oe01-common
         │  ├─ cmp-oe01-common-network # Spoke VCN/subnet/SGW/NSG
         │  └─ cmp-oe01-common-infra   # dự trữ, không cần tạo ngay
         ├─ cmp-oe01-prod          # OKE, nodes, volumes, Private LB
         ├─ cmp-oe01-nonprod       # dự trữ
         └─ cmp-oe01-development   # dự trữ
```

Không tạo zone riêng chồng lên network và prod: một custom zone ở `cmp-oe1` bao phủ network/compute liên quan. Bastion resource thuộc security nhưng private endpoint nằm trong subnet của Spoke. Kubernetes namespaces không phải OCI compartments. Public LB thuộc hub; Private LB do Kubernetes tạo thuộc compartment cluster dù subnet nằm ở common-network.

Nếu `mb-home-cmp` đã ở sâu, truy ngược parent OCID trước khi tạo: OCI giới hạn độ sâu compartment. Rút gọn các lớp dự trữ nếu cần; không cố giữ tên/cấu trúc đến mức vượt giới hạn.

### 3.2 Địa chỉ

| VCN | Subnet | CIDR | Loại |
|---|---|---|---|
| Hub `10.0.0.0/16` | hub-publiclb-sn | `10.0.2.0/24` | Public |
| Hub | hub-fw-sn | `10.0.3.0/24` | Private |
| Hub | hub-mgmt-sn | `10.0.4.0/24` | Private, dự trữ |
| Hub | hub-monitoring-sn | `10.0.5.0/24` | Private, dự trữ |
| Hub | hub-dns-sn | `10.0.6.0/24` | Private, dự trữ |
| Spoke `10.1.0.0/16` | oke-api-sn | `10.1.0.0/28` | Private |
| Spoke | oke-workers-sn | `10.1.1.0/24` | Private |
| Spoke | oke-lb-sn | `10.1.2.0/24` | Private |
| Spoke | oke-bastion-sn | `10.1.3.0/28` | Private |
| Spoke | oke-pods-sn | `10.1.16.0/20` | Private |
| OE02 tùy chọn | spoke kiểm thử | `10.2.0.0/16` | Private |

Tránh trùng CIDR với VPN, LAN laptop và VCN khác sẽ kết nối. Service CIDR của Kubernetes chọn dải riêng không chồng VCN/pod/on-prem; dùng giá trị OKE cho phép và ghi vào inventory. Không chọn một IP firewall giả định rồi điền route: lấy **Private IP OCID thật** sau khi FW Active.

### 3.3 Sizing ban đầu — cần đo lại khi có tải

| Thành phần | Số lượng | Requests gợi ý mỗi Pod | Storage |
|---|---:|---|---|
| Worker E4.Flex x86 | 3 | 4 OCPU / 32 GB mỗi VM | Boot 100 GB mỗi VM |
| Kafka combined broker/controller | 3 | 1 CPU / 3 GiB | 100 GiB mỗi broker |
| PostgreSQL | 3 | 500m / 2 GiB | 50 GiB mỗi instance |
| 10 service + frontend | 2 replica mỗi workload | 100–250m / 128–512 MiB | Stateless |
| Traefik | 2 | 100m / 128 MiB | Không PVC |
| Jenkins controller | 1 | 500m / 1 GiB | 20 GiB |
| Jenkins agent | Tối đa 1 job build đồng thời | Giới hạn 2 CPU / 4 GiB | Workspace ephemeral |
| Argo CD/operators/system | Theo chart | Dự trữ 2–4 GiB toàn cluster | Theo cấu hình |

OKE có tài nguyên system-reserved; OCPU khác vCPU tùy kiến trúc, lấy `kubectl describe node` làm số allocatable thực tế. Chọn một AD và phân ba FD cho lab để tránh ràng buộc attach Block Volume giữa AD khi reschedule. Thiết kế này chịu được một số lỗi worker, không cam kết chịu mất toàn AD. Với multi-AD cần thiết kế volume topology và phục hồi tương ứng.

### 3.4 Inventory phải điền

Lưu file riêng ngoài Git chứa: region, tenancy/parent/lab/network/security/OE/prod/backup OCID, VCN/subnet/NSG OCID, DRG attachments và route-table OCID, firewall private IP + private-IP OCID, cluster OCID/API IP, public/private LB IP, DNS hostname, Bastion OCID, key OCID, phiên bản OKE/operators/chart và digest image.

Không ghi secret/password/token/private key vào inventory hoặc ảnh báo cáo.

## 4. Chuẩn bị quyền và công cụ

### 4.1 Những việc cần tenancy administrator thực hiện một lần

1. Xác nhận region có OKE, Network Firewall, WAF; quota đủ VM, OCPU, RAM, LB, Block Volume, VCN và firewall.
2. Cấp quyền tạo lab compartment dưới parent; tạo groups trong identity domain dùng chung với tên tiền tố `tndat-` để tránh trùng.
3. Xác nhận Cloud Guard đã enabled và reporting region. Nếu chưa, tenancy administrator bật và thêm service policies theo trang setup OCI. Không tự đổi reporting region hoặc xóa target của tenancy đang dùng chung.
4. Cho người lab xem configuration Cloud Guard và quản lý target/recipe trong phạm vi đã phân quyền.
5. Xác nhận policies bắt buộc OKE, Block Volume và KMS theo cấu hình tenancy hiện tại.

Quyền quản lý một compartment không tự cấp quyền quản lý identity domain hoặc bật Cloud Guard toàn tenancy. [Cloud Guard prerequisites](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/prerequisites.htm), [Security Zones setup](https://docs.oracle.com/en-us/iaas/Content/security-zone/using/get-started.htm)

### 4.2 Máy thao tác

Cài OCI CLI theo [hướng dẫn Oracle](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm), kubectl tương thích phiên bản cluster, Helm, Git, jq và OpenSSH. Docker/BuildKit chỉ cần ở máy build hoặc Jenkins agent. Xác thực OCI bằng profile người dùng hoặc session; dùng MFA theo tenancy.

```bash
oci --version
kubectl version --client
helm version
oci session authenticate
```

Trong các shell ví dụ, đặt profile/region trước. Nếu dùng API-key profile thì không thêm `--auth security_token`; nếu dùng session phải chọn đúng auth mode cho các lệnh và kubeconfig exec.

```bash
export OCI_CLI_PROFILE='REPLACE_PROFILE'
export OCI_CLI_REGION='REPLACE_REGION'
# Chỉ khi profile là session token:
export OCI_CLI_AUTH=security_token
export AIMS_WORKDIR="$HOME/aims-oci-lab"
mkdir -p "$AIMS_WORKDIR/manifests" "$AIMS_WORKDIR/evidence"
chmod 700 "$AIMS_WORKDIR"
```

Chốt phiên bản trước khi cài: ghi Kubernetes version từ OKE Console, chart version và appVersion từ `helm search repo ... --versions`. Dùng phiên bản được operator hỗ trợ trên Kubernetes đã chọn; không mặc định chọn bản mới nhất của từng thành phần độc lập. Mỗi lệnh Helm dưới đây có biến phiên bản bắt buộc. Với Strimzi chọn release phục vụ API `kafka.strimzi.io/v1` để dùng manifest trong mục 14.

## 5. Compartment và IAM

### 5.1 Tạo compartment trên Console

1. **Identity & Security → Compartments → Create Compartment**.
2. Parent = `mb-home-cmp`, Name = `tndat-lz-cmp`; description ghi chủ sở hữu và mục đích lab.
3. Tạo các compartment dùng thật trong cây mục 3 theo đúng parent. Dự trữ không cần tạo ngay.
4. Gắn free-form tags `project=aims`, `owner=tndat`, `environment=lab` trên từng tài nguyên hỗ trợ tag.
5. Tạo budget/alert cho phạm vi lab qua **Billing & Cost Management → Budgets**. Budget cảnh báo, không tự chặn mọi phát sinh.

CLI minh họa một thao tác tương đương:

```bash
oci iam compartment create \
  --compartment-id 'REPLACE_PARENT_OCID' \
  --name tndat-lz-cmp --description 'AIMS OCI manual lab'
oci iam compartment list --compartment-id 'REPLACE_LAB_OCID' \
  --compartment-id-in-subtree true --all
```

### 5.2 Quyền người dùng

Tạo group `tndat-lz-admins`, `tndat-network-admins`, `tndat-security-admins`, `tndat-oe01-admins`. Với lab một người, có thể dùng group lab-admin trong bước bootstrap. Muốn kiểm thử phân quyền phải dùng identity không đồng thời thuộc group toàn quyền.

Tạo policy `tndat-lz-administration` ở lab hoặc parent phù hợp. Các mẫu dưới dùng OCID để không phụ thuộc tên/path; thay domain thực tế, ví dụ `Default`.

```text
Allow group REPLACE_DOMAIN/tndat-lz-admins to manage all-resources in compartment id REPLACE_LAB_OCID
Allow group REPLACE_DOMAIN/tndat-network-admins to manage virtual-network-family in compartment id REPLACE_NETWORK_OCID
Allow group REPLACE_DOMAIN/tndat-network-admins to manage network-firewall-family in compartment id REPLACE_NETWORK_OCID
Allow group REPLACE_DOMAIN/tndat-network-admins to manage load-balancers in compartment id REPLACE_NETWORK_OCID
Allow group REPLACE_DOMAIN/tndat-oe01-admins to manage all-resources in compartment id REPLACE_OE_OCID
Allow group REPLACE_DOMAIN/tndat-security-admins to manage waf-family in compartment id REPLACE_SECURITY_OCID
Allow group REPLACE_DOMAIN/tndat-security-admins to manage cloud-guard-family in compartment id REPLACE_LAB_OCID
```

Đây là nhóm quyền lab; không phải bộ least-privilege production đầy đủ. Security admin cần thêm quyền Vault/key, Bastion và logging theo việc được giao; xem policy builder của từng dịch vụ. WAF resource liên kết policy với LB cũng cần quyền dùng LB ở hub. Các quyền xem config Cloud Guard cấp tenancy do administrator bổ sung, không đặt policy cấp con để cố cấp quyền cao hơn phạm vi parent.

### 5.3 Quyền OKE xuyên compartment

Trong lab, cluster/Private LB/volumes ở prod, subnet/NSG ở common-network. Thiết lập quyền cluster dùng tài nguyên mạng bằng cluster principal. Sau khi có cluster OCID, giới hạn theo ID:

```text
Allow any-user to use virtual-network-family in compartment id REPLACE_SPOKE_NETWORK_OCID where all {request.principal.type = 'cluster', request.principal.id = 'REPLACE_CLUSTER_OCID'}
Allow any-user to manage load-balancers in compartment id REPLACE_PROD_OCID where all {request.principal.type = 'cluster', request.principal.id = 'REPLACE_CLUSTER_OCID'}
```

Người tạo OKE cần quyền dùng subnet và tạo node trong các compartment tương ứng. Chính sách trên bổ sung cho tài nguyên mạng tách compartment, không thay thế bộ quyền OKE cấp tenancy có sẵn. Nếu bật tự quản lý NSG của cloud controller, cần `manage network-security-groups` tương ứng; baseline ở đây quản lý security rules thủ công và dùng annotation `security-rule-management-mode: None`.

Không cấp quyền OKE sửa Hub Public LB: LB đó được người quản trị tạo thủ công. Không dùng một dynamic group chung để đại diện đồng thời cluster, CSI, ingress controller và ứng dụng. [OKE LB configuration/IAM](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengconfiguringloadbalancersnetworkloadbalancers-subtopic.htm), [WAF policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/wafpolicyreference_topic-Details_for_WAF_Policies.htm)

**Checkpoint:** đúng cây compartment; OE admin thử đọc resource của OE thành công và sửa resource Hub bị từ chối; lưu kết quả khi dùng identity chỉ có quyền OE.

## 6. Cloud Guard, Vault và Security Zones

### 6.1 Cloud Guard baseline

1. **Identity & Security → Cloud Guard → Overview/Settings**: xác nhận enabled, reporting region và targets hiện có.
2. **Recipes → Detector recipes**: clone OCI Configuration và OCI Activity detector recipes để giữ bản lab. Bật các rule có sẵn liên quan public bucket/public instance/security rules. Ghi ID từng rule dùng để nghiệm thu.
3. **Targets → Create target**: chọn `tndat-lz-cmp`, gắn recipes lab và responder recipe. Nếu parent có target, kiểm tra phạm vi hiệu lực sau khi thêm target con; không xóa target người khác.
4. Ban đầu responder ở chế độ cần người xử lý cho các thay đổi resource. Thiết lập Notifications qua Events theo rule thật của OCI; không giả định mọi detector đều có responder tự động phù hợp.
5. Không tự viết một detector tùy ý chỉ bằng clone recipe. Với yêu cầu riêng như thay đổi FW policy, kiểm tra rule có sẵn; nếu không có thì dùng Audit/Events/Logging với cơ chế riêng và ghi rõ.

[Oracle detector recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes-about.htm)

### 6.2 Vault và backup bucket

1. **Identity & Security → Vault → Create Vault**, compartment `cmp-security`. Chọn loại vault phù hợp lab, tạo master encryption key symmetric AES-256 tên `aims-backup-key`.
2. Cấp quyền Object Storage sử dụng key theo [policy Oracle Vault](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/assigningkeys.htm). Service principal dùng region thực tế; kiểm tra quyền trước khi tạo bucket.
3. Tạo custom recipe cho `cmp-backup` ở bước tiếp theo rồi tạo bucket **Storage → Object Storage & Archive Storage → Buckets**: compartment `cmp-backup`, private, Standard, encryption chọn key trên, bật versioning theo nhu cầu, không tạo public access/PAR vô hạn.
4. Tạo lifecycle rule giữ backup lab theo thời hạn đã chọn, ví dụ 14 ngày. Versioning cần lifecycle cho phiên bản cũ nếu không muốn tích lũy vô hạn.

### 6.3 Custom Security Zones cụ thể

**Chọn baseline nhỏ có thể kiểm chứng**, không bật nguyên Maximum Security. Tại **Security Zones → Recipes → Create recipe**, chọn các policy bằng tên trong Console và đối chiếu ID mô tả dưới đây:

| Zone | Compartment gốc | Policy bật trong baseline |
|---|---|---|
| `sz-oe01-private` | `cmp-oe1` | `deny public_subnets`, `deny public_load_balancer`, `deny public_buckets` |
| `sz-backup` | `cmp-backup` | `deny public_buckets`, `deny buckets_without_vault_key` |

Baseline OE không bắt buộc CMK cho boot/PVC; ổ vẫn dùng mã hóa mặc định OCI. Đây là lựa chọn lab minh bạch. Nếu muốn bắt buộc CMK, cấu hình node-pool boot key, StorageClass `kms-key-id`, service permissions và test cấp/attach volume trước khi bật thêm hai policy CMK.

Để nguyên **không chọn** policy cấm DRG/SGW, quản lý OKE, sửa route, detach volume, hoặc yêu cầu subnet/instance khác zone theo kiểu không phù hợp. Nếu cần thêm ràng buộc cùng zone, giữ network và prod dưới zone OE chung. Không gắn zone private lên `cmp-network` có Public LB. NSG/Flow Logs là cấu hình riêng, không phải policy tùy ý trong recipe.

Tạo zone ở **Security Zones → Create security zone**, chọn compartment và recipe. Sau khi tạo, mở lại Cloud Guard Targets: OCI tạo/thay đổi security-zone targets, vì vậy không duy trì giả định chỉ một target trên toàn nhánh lab. [Policy catalogue](https://docs.oracle.com/en-us/iaas/Content/security-zone/using/security-zone-policies.htm), [quan hệ Cloud Guard–Security Zones](https://docs.oracle.com/en-us/iaas/Content/security-zone/using/security-zones.htm)

**Checkpoint:** thử tạo public subnet nhỏ trong network OE bị từ chối; tạo private subnet vẫn được. Thử bucket không CMK trong `cmp-backup` bị từ chối; bucket private có key tạo được. Dùng `cmp-security-test` ngoài zone cho phép thử Cloud Guard, chỉ bucket rỗng; không kỳ vọng cùng thao tác bị preventive chặn mà vẫn tạo resource để detector quét.

## 7. Tạo mạng Hub và Spoke

### 7.1 Hub VCN

1. **Networking → Virtual Cloud Networks → Create VCN**, compartment `cmp-network`, name `hub-vcn`, CIDR `10.0.0.0/16`, DNS label `aimshub`. Chọn tạo VCN riêng, không dùng wizard tự mở Internet cho mọi subnet.
2. Tạo regional subnets theo mục 3. Public LB subnet cho phép public IP; firewall và các subnet còn lại private.
3. Trong VCN, tạo `hub-igw` ở Internet Gateways và `hub-natgw` ở NAT Gateways, enabled.
4. Tạo route tables với tên mục 8; có thể để trống trước khi có FW private IP. Gắn từng table đúng subnet ngay từ đầu.
5. Không gắn ingress route table ép Internet traffic qua FW trên IGW: Hub B ở đây inspect đoạn **sau Public LB**.

### 7.2 Spoke VCN

1. Tạo `oe01-vcn`, compartment common-network, CIDR `10.1.0.0/16`, DNS label `aimsoe01`.
2. Tạo năm subnet regional private: API, workers, pods, LB và Bastion.
3. Tạo `oe01-sgw`, chọn **All <region> Services in Oracle Services Network**. Ghi service CIDR label do OCI hiển thị, không thay bằng một dải IP tự đoán.
4. Tạo `rt-spoke` và gắn cho các subnet; route Oracle services→SGW, route mặc định→DRG ở bước sau.
5. DHCP options dùng VCN resolver; chưa cần custom DNS resolver endpoint cho một spoke. DNS subnet hub là chỗ dự trữ, không có nghĩa cần chạy DNS VM.

### 7.3 DRG và attachments

1. **Networking → Customer Connectivity → Dynamic Routing Gateways → Create DRG**: `lz-drg`, compartment `cmp-network`.
2. **VCN attachments → Create attachment**: `att-hub` tới Hub VCN; `att-oe01` tới Spoke VCN. Người tạo cần quyền ở cả network compartments.
3. Tạo hai DRG route tables `drg-rt-from-hub`, `drg-rt-from-spoke`. Dùng static routes cho lab để dễ kiểm chứng; không nhận import distribution tự thêm direct spoke→spoke routes.
4. Gán bảng **from-hub** cho attachment Hub, bảng **from-spoke** cho attachment OE01.
5. Edit attachment `att-hub` → VCN route table chọn `rt-hub-from-drg`. Đây là bảng VCN khác với DRG route table vừa gán.

**Checkpoint:** VCN attachments Available; chưa tiếp tục OKE cho đến khi bảng route và firewall ở mục 8 hoàn tất.

## 8. Firewall và bảng route hai chiều

### 8.1 Tạo OCI Network Firewall

1. **Identity & Security → Network Firewall → Network Firewall Policies → Create**: `aims-hub-b-policy`, compartment `cmp-network`.
2. Tạo address lists cho Hub LB `10.0.2.0/24`, Spoke LB `10.1.2.0/24`, OE01 `10.1.0.0/16`; service lists cho TCP/80 và TCP/443.
3. Tạo rule theo thứ tự dưới đây. Đây là policy lab, không dùng allow-any-all không giải thích.

| Thứ tự | Nguồn → đích | Service | Hành động |
|---:|---|---|---|
| 10 | Hub LB subnet → Spoke LB subnet | TCP/80 | Intrusion Detection trong bước đầu, sau đó Intrusion Prevention khi test ổn |
| 20 | OE01 → Internet | TCP/443 | Cho phép/inspection theo nhu cầu dependency |
| 30 | OE01 → Internet | TCP/80 | Chỉ bật nếu bootstrap/package mirror thực sự cần; ghi lại ngoại lệ |
| 90 | OE01 → OE02 và ngược lại | Any | Drop trong baseline cách ly |
| 100 | Phần còn lại | Any | Drop |

OCI rule action và inspection mode dùng lựa chọn thực tế trên Console; không nhầm `Allow` thông thường với bật IDS. DNS dùng VCN resolver, không cần cho Pod tùy ý UDP/53 tới Internet. Thêm endpoint SMTP/payment theo contract nếu phát sinh.

4. Tạo firewall `aims-hub-b-fw` trong `hub-fw-sn`, gắn policy. Chờ Active.
5. Lấy địa chỉ IP và **OCID của private IP** từ resource network của firewall. Không dùng OCID firewall hoặc VNIC thay cho private-IP OCID khi chọn route target.
6. Bật traffic/threat logs vào log group lab. Cấu hình NSG/security list của firewall cho đúng các luồng, không để packet bị lớp VCN chặn trước khi tới policy.

[Network Firewall documentation](https://docs.oracle.com/en-us/iaas/Content/network-firewall/home.htm)

### 8.2 VCN route tables — cấu hình đầy đủ cho CIDR lab

Trong VCN → Route Tables → table → Add Route Rules. Route chọn theo **đích**, không phải nguồn. Route cụ thể hơn thắng `0.0.0.0/0`.

| Table / gắn ở đâu | Destination | Target |
|---|---|---|
| `rt-hub-publiclb` / hub-publiclb-sn | `10.1.0.0/16` | Private IP firewall |
| như trên | `0.0.0.0/0` | Hub IGW |
| `rt-hub-fw` / hub-fw-sn | `10.1.0.0/16` | DRG |
| như trên | `0.0.0.0/0` | Hub NAT Gateway |
| `rt-hub-from-drg` / VCN ingress table của att-hub | `10.0.2.0/24` | Private IP firewall |
| như trên | `0.0.0.0/0` | Private IP firewall |
| `rt-hub-nat-return` / route table gắn NAT Gateway | `10.1.0.0/16` | Private IP firewall |
| `rt-hub-private` / các subnet hub private dự trữ | `0.0.0.0/0` | Private IP firewall |
| `rt-hub-nat-return`, nếu sử dụng subnet dự trữ | `10.0.4.0/24`, `10.0.5.0/24`, `10.0.6.0/24` — mỗi CIDR một rule | Private IP firewall |
| `rt-spoke` / các subnet Spoke | service CIDR **All <region> Services…** | Spoke SGW |
| như trên | `0.0.0.0/0` | DRG |

Traffic firewall→Hub LB dùng local VCN routing; không thêm rule khiến gói tới LB quay lại chính firewall. Hub IGW không dùng bảng `rt-hub-from-drg`. Tại NAT Gateway details chọn route table `rt-hub-nat-return` để đảm bảo chiều trả lời Internet egress trở lại firewall.

### 8.3 DRG route tables

| DRG table | Attachment sử dụng khi gói vào DRG | Destination | Next-hop attachment |
|---|---|---|---|
| `drg-rt-from-spoke` | `att-oe01` | `0.0.0.0/0` | `att-hub` |
| `drg-rt-from-hub` | `att-hub` | `10.1.0.0/16` | `att-oe01` |

Kiểm tra Effective routes để chắc không có route cụ thể tới spoke khác bypass firewall. Khi thêm OE02: bảng from-hub thêm `10.2.0.0/16→att-oe02`; att-oe02 dùng from-spoke; FW subnet thêm route OE02→DRG; NAT return thêm OE02→FW. Policy firewall quyết định cho/chặn E-W. Không tạo LPG trực tiếp nối spokes.

### 8.4 Đi từng luồng để chứng minh không bất đối xứng

| Kết nối | Chiều đi | Chiều về |
|---|---|---|
| Client→Public LB | Internet→IGW→Public LB | Public LB→IGW→client |
| Public LB→Private LB | Public LB→FW→DRG→Spoke LB | Spoke LB→DRG→Hub ingress table→FW→Public LB |
| Pod→Internet | Spoke→DRG→Hub ingress table→FW→NAT | NAT return table→FW→DRG→Spoke |
| Pod→Object Storage | Spoke→SGW→Oracle services | Theo SGW trở lại Spoke |

Đây là các route được điều chỉnh cho CIDR và Spoke OKE của lab dựa trên [Hub B network configuration](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/blob/master/addons/oci-hub-models/hub_b/addon_network_hub_b.json); không copy nguyên bảng mẫu rồi giữ CIDR khác. Dùng Network Path Analyzer cho các đoạn được hỗ trợ, sau đó kiểm chứng bằng kết nối thật và log; diagram không thay thế phép thử data plane.

## 9. NSG và security list

### 9.1 Quy tắc cấu hình

Trong mỗi VCN → Network Security Groups → Create NSG. Tạo các nhóm `nsg-hub-lb`, `nsg-hub-fw`, `nsg-oke-api`, `nsg-oke-workers`, `nsg-oke-pods`, `nsg-oke-lb`. Gắn resource đúng NSG; tạo NSG mà không gắn không có tác dụng.

NSG reference chỉ dùng nơi OCI hỗ trợ trong cùng VCN; Hub→Spoke dùng CIDR/IP vì khác VCN. Security lists không được chứa allow rộng làm mất ý nghĩa NSG hẹp. Với firewall, dùng stateless rules theo hướng dẫn dịch vụ và khai báo chiều đối ứng; các endpoints thông thường dùng stateful. Cần ICMP type 3 code 4 để Path MTU Discovery.

### 9.2 Ma trận luồng lab

Mỗi dòng tạo egress ở nguồn và ingress ở đích phù hợp. Các port backend thực tế được xác nhận sau khi ingress Service được tạo.

| Nguồn | Đích | Protocol/port | Mục đích |
|---|---|---|---|
| Internet | Hub LB | TCP/443 | Web public; chỉ mở 80 nếu cấu hình redirect |
| Hub LB subnet | Spoke LB subnet | TCP/80 | Backend qua FW; nguồn vẫn là LB, không phải FW IP |
| Spoke LB | Workers | TCP NodePort của Traefik | Private LB TCP backend |
| Spoke LB | Workers | TCP healthCheckNodePort nếu dùng Local | Health check cloud controller |
| Bastion endpoint `/32` | API endpoint | TCP/6443 | kubectl |
| Bastion endpoint `/32` | Workers | TCP/22, tùy chọn | SSH debug |
| Workers, Pods | API endpoint | TCP/6443, TCP/12250 | OKE control-plane communication |
| API endpoint | Workers | TCP/10250 và ICMP | kubelet |
| API endpoint | Pod CIDR | All | OKE VCN-native baseline |
| Workers ↔ Workers | Trong worker CIDR | All | OKE VCN-native baseline |
| Workers ↔ Pods | Hai CIDR nội bộ | All | OKE VCN-native baseline |
| Pods ↔ Pods | Trong pod CIDR | All ở VCN layer | Thu hẹp theo Kubernetes NetworkPolicy |
| API, Workers, Pods | Oracle Services Network | TCP/443 | OKE/images/storage qua SGW |
| Workers, Pods | Internet | TCP/443; 80 nếu đã duyệt dependency | GHCR, GitHub, charts, package repos qua Hub |

Theo dõi chi tiết baseline VCN-native tại [OKE network configuration](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfig.htm). CNI không đồng nghĩa NetworkPolicy được enforce: nếu chọn Calico policy-only thì cài theo [hướng dẫn OKE NetworkPolicy](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengsettingupcalico.htm), đúng Kubernetes version, và kiểm thử deny thực tế trước khi ghi nghiệm thu.

Bật **VCN Flow Logs** cho các subnet/VNIC phù hợp, lưu trong log group `aims-network-logs`. Logs thuộc dịch vụ OCI, không cần VM trong hub-monitoring-sn để nhận logs.

## 10. Tạo OKE và Bastion

### 10.1 OKE Custom Create

1. **Developer Services → Kubernetes Clusters → Create Cluster → Custom Create**.
2. Name `aims-oke`, compartment `cmp-oe01-prod`, chọn Enhanced nếu cần các tính năng tương ứng.
3. Chọn Kubernetes version còn được OKE và các operators hỗ trợ; ghi chính xác vào inventory.
4. VCN `oe01-vcn` ở common-network. Endpoint private, subnet `oke-api-sn`, NSG API.
5. Networking = OCI VCN-native; pod subnet `oke-pods-sn`, NSG pods. Chọn giới hạn Pod/node phù hợp dung lượng IP.
6. Node pool `aims-workers`: 3 managed nodes, E4.Flex x86 4 OCPU/32 GB; OKE-supported image; boot 100 GB; private subnet workers; NSG workers. Chọn placement một AD, trải ba FD nếu capacity cho phép.
7. Load balancer subnet chọn `oke-lb-sn` nếu wizard yêu cầu. Không cho wizard tạo thêm public worker subnet/NAT ở Spoke.
8. Enable cần thiết CSI/VCN-native/CoreDNS; đợi node Ready. Nếu chỉ quota shape khác, đổi shape tương đương và bảo đảm image architecture của AIMS phù hợp.
9. Ghi cluster OCID, API IP; hoàn tất cluster-principal policy mục 5.

### 10.2 Bastion cho API private

1. **Identity & Security → Bastion → Create**: compartment `cmp-security`, tên `aimsBastion` (alphanumeric), target VCN `oe01-vcn`, subnet `oke-bastion-sn`.
2. CIDR allowlist chỉ public IP laptop `/32` hoặc dải mạng quản trị thực tế. TTL session ví dụ 3 giờ.
3. Target subnet dùng route Oracle services→Spoke SGW. Mở security rules endpoint Bastion→API 6443.
4. Tạo **SSH port forwarding session**: target API private IP, port 6443, upload public SSH key.
5. Đợi Active → menu session → **Copy SSH Command**. Điền private key và local port 16443; giữ tunnel chạy ở terminal riêng.

```bash
export AIMS_KUBECONFIG="$AIMS_WORKDIR/kubeconfig"
oci ce cluster create-kubeconfig \
  --cluster-id 'REPLACE_CLUSTER_OCID' --file "$AIMS_KUBECONFIG" \
  --region "$OCI_CLI_REGION" --token-version 2.0.0 --kube-endpoint PRIVATE_ENDPOINT
chmod 600 "$AIMS_KUBECONFIG"
# Dùng command chính xác OCI cung cấp; hình thức như sau:
ssh -i "$HOME/.ssh/REPLACE_KEY" -N \
  -L 127.0.0.1:16443:REPLACE_API_PRIVATE_IP:6443 \
  -o ExitOnForwardFailure=yes \
  REPLACE_SESSION_OCID@host.bastion.REPLACE_REGION.oci.oraclecloud.com
```

Trong terminal khác, dùng kubeconfig riêng, không ghi đè cấu hình cluster đang làm việc:

```bash
export KUBECONFIG="$AIMS_WORKDIR/kubeconfig"
AIMS_CLUSTER_ENTRY=$(kubectl config view -o jsonpath='{.clusters[0].name}')
kubectl config set-cluster "$AIMS_CLUSTER_ENTRY" \
  --server=https://127.0.0.1:16443 --tls-server-name=REPLACE_API_PRIVATE_IP
kubectl get nodes -o wide
kubectl get pods -n kube-system
```

Giữ CA trong kubeconfig; `tls-server-name` là IP/DNS endpoint gốc có trong certificate SAN. Không dùng `insecure-skip-tls-verify`. Nếu session auth hết hạn thì refresh OCI session; tunnel Active không có nghĩa OCI token còn hiệu lực. [OKE Bastion setup](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengsettingupbastion.htm)

**Checkpoint:** ba worker Ready, private IP, CoreDNS/CNI/CSI hoạt động, không có public worker/API endpoint.

## 11. Storage, namespace và ingress

### 11.1 Tổ chức Kubernetes

| Namespace | Nội dung |
|---|---|
| `aims` | frontend và 10 service |
| `data` | CloudNativePG Cluster |
| `cnpg-system` | CloudNativePG operator |
| `kafka` | Strimzi operator, brokers, topics, users |
| `ingress-system` | Traefik |
| `cicd` | Jenkins và agents |
| `argocd` | Argo CD |

Đây là cách tách namespace của runbook; tên DNS và vị trí secrets bên dưới theo bảng này. Không coi namespace là OE isolation mạnh tương đương tenancy.

```bash
for ns in aims data cnpg-system kafka ingress-system cicd argocd; do
  kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f -
done
kubectl label namespace aims \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted --overwrite
kubectl get storageclass
```

### 11.2 Persistent storage

Dùng `oci-bv` CSI cho dữ liệu lab; không dùng hostPath/local-path trên node. Có thể tạo lớp riêng bảo toàn volume khi xóa PVC:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: aims-bv-retain
provisioner: blockvolume.csi.oraclecloud.com
parameters:
  attachment-type: paravirtualized
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
```

Lưu vào `manifests/storage.yaml`, apply. PVC chưa có Pod có thể Pending do `WaitForFirstConsumer`, không phải mặc định lỗi. Nếu bật CMK cho PVC, thêm `kms-key-id` vào parameters và cấp quyền KMS phù hợp. [OKE Block Volume PVC](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcreatingpersistentvolumeclaim_topic-Provisioning_PVCs_on_BV.htm)

### 11.3 Traefik + Private OCI Load Balancer

Chọn Traefik làm ingress controller cho lab, Kubernetes Service loại LoadBalancer yêu cầu OCI **LB** private, không phải public LB hoặc NLB. Hub Public LB vẫn do Console quản lý.

```bash
helm repo add traefik https://traefik.github.io/charts
helm repo update
helm search repo traefik/traefik --versions
export AIMS_TRAEFIK_CHART_VERSION='41.5.0'
```

Tạo `manifests/traefik-values.yaml`, điền subnet/NSG OCID:

```yaml
deployment:
  replicas: 2
  healthchecksPort: 8000
providers:
  kubernetesIngress:
    enabled: true
    ingressClass: aims-internal
  kubernetesCRD:
    enabled: false
ingressClass:
  enabled: true
  isDefaultClass: false
  name: aims-internal
service:
  type: LoadBalancer
  annotations:
    oci.oraclecloud.com/load-balancer-type: lb
    service.beta.kubernetes.io/oci-load-balancer-internal: "true"
    service.beta.kubernetes.io/oci-load-balancer-subnet1: REPLACE_LB_SUBNET_OCID
    oci.oraclecloud.com/oci-network-security-groups: REPLACE_LB_NSG_OCID
    oci.oraclecloud.com/security-rule-management-mode: None
    service.beta.kubernetes.io/oci-load-balancer-shape: flexible
    service.beta.kubernetes.io/oci-load-balancer-shape-flex-min: "10"
    service.beta.kubernetes.io/oci-load-balancer-shape-flex-max: "100"
ports:
  web:
    port: 8000
    exposedPort: 80
    nodePort: 32080
    forwardedHeaders:
      trustedIPs:
        - 10.0.2.0/24
        - 10.1.2.0/24
  websecure:
    expose:
      default: false
additionalArguments:
  - --ping.entrypoint=web
resources:
  requests: {cpu: 100m, memory: 128Mi}
  limits: {cpu: 500m, memory: 512Mi}
podDisruptionBudget:
  enabled: true
  minAvailable: 1
accessLog:
  enabled: true
```

Values này đã được kiểm tra render với chart **41.5.0**, Kubernetes target **1.34.0**; đây là kiểm tra local, chưa phải kiểm thử trên OKE. Nếu đổi chart version, đọc schema tương ứng (các chart cũ có thể dùng `logs.access` thay `accessLog`). `deployment.healthchecksPort: 8000` giữ probes trên đúng port khi đổi ping entrypoint; `/ping` là health endpoint độc lập, không đi vào nghiệp vụ AIMS.

```bash
helm template aims-ingress traefik/traefik \
  --version "$AIMS_TRAEFIK_CHART_VERSION" -n ingress-system \
  -f "$AIMS_WORKDIR/manifests/traefik-values.yaml" > "$AIMS_WORKDIR/ingress-rendered.yaml"
helm upgrade --install aims-ingress traefik/traefik \
  --version "$AIMS_TRAEFIK_CHART_VERSION" -n ingress-system \
  -f "$AIMS_WORKDIR/manifests/traefik-values.yaml" --wait --timeout 10m
kubectl -n ingress-system get svc,pods -o wide
```

NSG workers cho Spoke LB→TCP/32080, health-check port theo Service/backend set thực tế. Verify Service chỉ có port dự kiến, LB private thuộc prod và subnet đúng `oke-lb-sn`. Cột EXTERNAL-IP của Service có thể hiển thị private IP — tên cột không có nghĩa LB public. Đọc annotation và Backend Sets để xác nhận controller tạo TCP/HTTP listener đúng thiết kế.

[Traefik chart](https://github.com/traefik/traefik-helm-chart/tree/master/traefik), [Traefik Ingress](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/ingress/)

## 12. Web smoke test, Public LB, DNS và WAF

### 12.1 Chứng minh hạ tầng bằng web mẫu trước

Tạo Deployment web trả về thông điệp lab trong namespace tạm `web-smoke`, kèm ClusterIP và Ingress class `aims-internal`. Image chọn từ registry tin cậy, chốt digest; ví dụ `traefik/whoami` với port 80, chạy trong namespace lab có Pod Security baseline thích hợp. Host dùng hostname AIMS; route `/` tới service mẫu. Chưa cần PostgreSQL/Kafka để kiểm tra network.

```bash
kubectl create namespace web-smoke
kubectl -n web-smoke create deployment web-smoke \
  --image='REPLACE_SMOKE_IMAGE_BY_DIGEST' --replicas=2
kubectl -n web-smoke expose deployment web-smoke --port=80 --target-port=80
```

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-smoke
  namespace: web-smoke
spec:
  ingressClassName: aims-internal
  rules:
    - host: REPLACE_AIMS_HOSTNAME
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-smoke
                port: {number: 80}
```

Apply ingress rồi `kubectl port-forward -n ingress-system svc/aims-ingress-traefik 18080:80` (xác nhận tên Service từ `get svc`). `curl -H 'Host: REPLACE_AIMS_HOSTNAME' http://127.0.0.1:18080/` phải trả nội dung web mẫu. Đây chỉ kiểm tra ingress; chưa chứng minh Hub FW.

### 12.2 Hub Public Load Balancer

1. **Networking → Load Balancers → Create Load Balancer**; chọn OCI Flexible Load Balancer, public, compartment `cmp-network`, Hub VCN, `hub-publiclb-sn`, NSG hub LB.
2. Bandwidth min/max ví dụ 10/100 Mbps; ghi vào sizing. Dùng reserved public IP nếu cần địa chỉ DNS ổn định theo khả năng Console/region.
3. Tạo backend set `aims-spoke-backend`, policy round robin. Backend = **private IP của OCI Private LB**, port 80. Không dùng ClusterIP hoặc Pod IP vào bước này.
4. Health check HTTP port 80, path `/ping`, expected 200, interval 10 giây. Đây là Traefik ping, không phải health toàn ứng dụng.
5. Upload certificate công khai hợp lệ cho hostname: leaf cert, private key, chain đúng định dạng, hoặc dùng OCI Certificates đã có cert phù hợp. Tạo HTTPS listener 443, backend set trên, TLS tối thiểu 1.2.
6. Nếu mở listener 80, cấu hình redirect sang HTTPS; nếu chưa cấu hình redirect thì chỉ mở 443. Đừng để HTTP trở thành lối đi không được bảo vệ.
7. Backend phải Healthy. Nếu không, kiểm tra mục 8 cả chiều về, FW logs, NSG, NodePort và `/ping`.

Hai LB tạo nhiều lớp proxy. Xác minh `Host`, `X-Forwarded-For`, `X-Forwarded-Proto` tới ứng dụng; chỉ tin forwarded headers từ chuỗi proxy đã biết. Ứng dụng cần nhận biết HTTPS gốc để tạo secure cookie/redirect đúng. Không bật tin forwarded header từ mọi IP.

### 12.3 Regional WAF

1. **Identity & Security → Web Application Firewall → Policies → Create WAF Policy**, chọn policy regional, compartment security, name `aims-regional-waf`.
2. Tạo/associate **Web Application Firewall resource** liên kết policy với Hub Public LB. Kiểm tra permissions xuyên compartment và trạng thái association; chỉ tạo policy chưa bảo vệ LB.
3. Bật request protection SQL injection/XSS theo capabilities có sẵn. Bắt đầu logging/check rồi chuyển rule thử nghiệm sang block/return HTTP response khi không gây false positive cho web mẫu.
4. Tạo rate-limit rule theo client IP; ngưỡng lab chọn theo kịch bản kiểm thử, ghi rõ window và response 429.
5. Bật access/request logging theo cấu hình WAF. Không mặc định mọi tính năng bot của Edge policy có ở regional policy.
6. DNS A record hostname→Public LB IPv4 (hoặc dùng record phù hợp địa chỉ LB). **Không có CNAME endpoint Edge WAF trong baseline này.**

[Regional và Edge WAF](https://docs.oracle.com/en-us/iaas/Content/WAF/Concepts/overview.htm)

```bash
curl --resolve 'REPLACE_HOST:443:REPLACE_PUBLIC_LB_IP' https://REPLACE_HOST/
curl https://REPLACE_HOST/
# Chỉ thử hostname lab của mình, sau khi bật rule SQLi tương ứng:
curl --get --data-urlencode "id=1' OR '1'='1" https://REPLACE_HOST/
```

**Checkpoint:** DNS+TLS hợp lệ, web bình thường 200, request test bị rule đã cấu hình chặn và có log. WAF có thể chặn trước FW nên request bị WAF chặn không nhất thiết xuất hiện trong FW backend log. Dùng request bình thường để chứng minh FW path.

## 13. PostgreSQL

### 13.1 Cài operator và cluster

```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update
helm search repo cnpg/cloudnative-pg --versions
export AIMS_CNPG_CHART_VERSION='REPLACE_TESTED_CHART_VERSION'
helm upgrade --install cnpg cnpg/cloudnative-pg \
  --version "$AIMS_CNPG_CHART_VERSION" -n cnpg-system --wait
```

Tạo `manifests/postgres.yaml`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: aims-postgres
  namespace: data
spec:
  instances: 3
  storage:
    storageClass: aims-bv-retain
    size: 50Gi
  resources:
    requests: {cpu: 500m, memory: 2Gi}
    limits: {cpu: "2", memory: 4Gi}
  affinity:
    enablePodAntiAffinity: true
    podAntiAffinityType: required
    topologyKey: kubernetes.io/hostname
  bootstrap:
    initdb:
      database: bootstrap_app
      owner: bootstrap_app
```

```bash
kubectl apply -f "$AIMS_WORKDIR/manifests/postgres.yaml"
kubectl -n data wait cluster/aims-postgres --for=condition=Ready --timeout=15m
kubectl -n data get pods,pvc,svc
```

Chốt PostgreSQL image/version được CNPG hỗ trợ trong manifest triển khai thật; lưu operator appVersion và image digest đã chạy. Ba instance không đồng nghĩa synchronous commit; nếu cần RPO gần zero khi primary mất, cấu hình synchronous replication và đánh giá tác động availability/latency. [CNPG replication](https://cloudnative-pg.io/documentation/current/replication/)

### 13.2 Ownership dữ liệu

| Service | DB/user |
|---|---|
| auth | aims_auth |
| catalog | aims_catalog |
| cart | aims_cart |
| order | aims_order |
| payment | aims_payment |
| inventory | aims_inventory |
| notification | aims_notification |
| search-recommendation | aims_search |
| security-telemetry | aims_security |

Gateway không có DB. Tạo role login riêng, không SUPERUSER/CREATEDB/CREATEROLE; tạo database tương ứng owner đúng role. `REVOKE CONNECT ... FROM PUBLIC` trên từng DB, grant CONNECT chỉ owner và role vận hành phù hợp; không chỉ tạo chín database nhưng để mọi user truy cập mọi database.

Cách manual: tìm primary bằng `kubectl -n data get cluster aims-postgres -o jsonpath='{.status.currentPrimary}'`, mở `psql` qua `kubectl exec -it <primary> -- psql -U postgres`. Tạo role/database và dùng `\password aims_order` để nhập password tương tác, không ghi plaintext password trong file SQL/Git. Ví dụ lặp cho mỗi DB:

```sql
CREATE ROLE aims_order LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password aims_order
CREATE DATABASE aims_order OWNER aims_order;
REVOKE CONNECT ON DATABASE aims_order FROM PUBLIC;
GRANT CONNECT ON DATABASE aims_order TO aims_order;
```

Database search bật `pg_trgm`, `unaccent` bằng migration quản trị nếu extension tồn tại trong image đã chọn. Tạo Secret riêng trong `aims` từ file env tạm mode 600; password URI phải được URL-encode. Host ghi `aims-postgres-rw.data.svc.cluster.local:5432`, TLS `sslmode=verify-full` và mount CA PostgreSQL tương ứng vào Pod. `-rw` theo primary hiện tại, không hardcode IP Pod.

```bash
kubectl -n aims create secret generic order-service-runtime \
  --from-env-file="$AIMS_WORKDIR/order-service.private.env"
```

Sau import, lưu secret trong nơi quản lý an toàn và xóa file tạm theo quy trình máy lab. Mỗi migration job sử dụng credential của service; chỉ tác vụ bootstrap mới dùng quyền quản trị. [CNPG security](https://cloudnative-pg.io/documentation/current/security/)

## 14. Kafka KRaft

### 14.1 Cài Strimzi

```bash
helm repo add strimzi https://strimzi.io/charts/
helm repo update
helm search repo strimzi/strimzi-kafka-operator --versions
export AIMS_STRIMZI_CHART_VERSION='REPLACE_TESTED_V1_API_CHART_VERSION'
helm upgrade --install strimzi strimzi/strimzi-kafka-operator \
  --version "$AIMS_STRIMZI_CHART_VERSION" -n kafka --wait
kubectl get crd kafkas.kafka.strimzi.io \
  -o jsonpath='{.spec.versions[*].name}'
```

Các CR dưới dùng `kafka.strimzi.io/v1`; chỉ apply khi CRD có served version tương ứng. Operator và Kafka resources đều ở namespace `kafka`; không cần watch namespace `aims` vì apps chỉ kết nối broker. Chọn Kafka version được release operator hỗ trợ và điền giá trị thật; không dùng `main` của upstream làm version lock. [Strimzi deployment](https://strimzi.io/docs/operators/latest/deploying.html)

```yaml
apiVersion: kafka.strimzi.io/v1
kind: KafkaNodePool
metadata:
  name: combined
  namespace: kafka
  labels: {strimzi.io/cluster: aims-kafka}
spec:
  replicas: 3
  roles: [controller, broker]
  storage:
    type: jbod
    volumes:
      - id: 0
        type: persistent-claim
        size: 100Gi
        class: aims-bv-retain
        deleteClaim: false
        kraftMetadata: shared
  resources:
    requests: {cpu: "1", memory: 3Gi}
    limits: {cpu: "2", memory: 5Gi}
  template:
    pod:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - topologyKey: kubernetes.io/hostname
              labelSelector:
                matchLabels: {strimzi.io/cluster: aims-kafka, strimzi.io/pool-name: combined}
---
apiVersion: kafka.strimzi.io/v1
kind: Kafka
metadata:
  name: aims-kafka
  namespace: kafka
spec:
  kafka:
    version: REPLACE_SUPPORTED_KAFKA_VERSION
    listeners:
      - name: tls
        port: 9093
        type: internal
        tls: true
        authentication: {type: tls}
    authorization: {type: simple}
    config:
      default.replication.factor: 3
      min.insync.replicas: 2
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
      unclean.leader.election.enable: false
      auto.create.topics.enable: false
      log.retention.hours: 168
  entityOperator:
    topicOperator: {}
    userOperator: {}
```

Lưu `manifests/kafka.yaml`, apply rồi wait Ready. Combined roles là đánh đổi lab ba worker; production có thể tách controller và broker. Kiểm tra mỗi broker ở node khác, ba PVC Bound.

### 14.2 Topics và ACL

Runbook dùng topic names dưới làm contract mẫu. Khi triển khai AIMS, thống nhất với AsyncAPI đã chốt; không tự đổi tên topic đang dùng mà bỏ producer/consumer cũ.

| Topic | Producer | Consumer |
|---|---|---|
| aims.catalog.product-changed.v1 | catalog | search-recommendation |
| aims.order.created.v1 | order | inventory, telemetry |
| aims.inventory.reserved.v1 | inventory | order |
| aims.inventory.rejected.v1 | inventory | order |
| aims.payment.requested.v1 | order | payment |
| aims.payment.completed.v1 | payment | order |
| aims.payment.failed.v1 | payment | order |
| aims.inventory.release-requested.v1 | order | inventory |
| aims.notification.requested.v1 | order | notification |
| aims.security.telemetry.v1 | gateway/services | security-telemetry |

Order là orchestrator: payment chỉ thực thi khi nhận `payment.requested`, không đồng thời thanh toán khi nhận `inventory.reserved`. Notification chỉ nhận command của orchestrator cho cùng tác vụ để tránh hai trigger trùng.

```yaml
apiVersion: kafka.strimzi.io/v1
kind: KafkaTopic
metadata:
  name: aims.order.created.v1
  namespace: kafka
  labels: {strimzi.io/cluster: aims-kafka}
spec:
  partitions: 3
  replicas: 3
  config:
    min.insync.replicas: 2
    retention.ms: 604800000
---
apiVersion: kafka.strimzi.io/v1
kind: KafkaUser
metadata:
  name: inventory-service
  namespace: kafka
  labels: {strimzi.io/cluster: aims-kafka}
spec:
  authentication: {type: tls}
  authorization:
    type: simple
    acls:
      - resource: {type: topic, name: aims.order.created.v1, patternType: literal}
        operations: [Read, Describe]
      - resource: {type: topic, name: aims.inventory.release-requested.v1, patternType: literal}
        operations: [Read, Describe]
      - resource: {type: group, name: aims.inventory-service, patternType: prefix}
        operations: [Read]
      - resource: {type: topic, name: aims.inventory., patternType: prefix}
        operations: [Write, Describe]
      - resource: {type: cluster}
        operations: [IdempotentWrite]
```

Nhân bản KafkaTopic cho các topic contract, retry/DLQ. KafkaUser mỗi service chỉ có quyền đọc/ghi đúng topic và consumer group; không chia sẻ một user toàn quyền cho mọi service. Với retry topic, cấp ACL bổ sung đúng worker.

Strimzi tạo TLS Secret trong `kafka`; sao chép **chỉ data/type** của user tương ứng và CA sang namespace `aims`, không sao chép ownerReferences/UID. Ví dụ:

```bash
kubectl -n kafka get secret inventory-service -o json | \
  jq '{apiVersion:"v1",kind:"Secret",metadata:{name:"inventory-kafka-tls",namespace:"aims"},type:.type,data:.data}' | \
  kubectl apply -f -
kubectl -n kafka get secret aims-kafka-cluster-ca-cert -o json | \
  jq '{apiVersion:"v1",kind:"Secret",metadata:{name:"aims-kafka-ca",namespace:"aims"},type:.type,data:.data}' | \
  kubectl apply -f -
```

Đây là copy manual: khi Strimzi rotate certificate phải refresh bản copy và restart/reload client; ghi expiry vào vận hành. Client bootstrap = `aims-kafka-kafka-bootstrap.kafka.svc.cluster.local:9093`, mount CA/client cert/key, producer `acks=all`, idempotence enabled; consumer commit sau transaction.

### 14.3 Saga và giới hạn delivery

Mỗi service ghi domain data và outbox cùng transaction. Publisher có thể publish lại sau crash nên consumer lưu `eventId` cùng domain update để deduplicate. Đối với cổng thanh toán ngoài, cần idempotency key tại provider; DB dedup đơn thuần không loại được mọi khoảng trống giữa gọi provider và commit DB.

Partition key theo order ID; nhiều publisher `SKIP LOCKED` có thể làm đảo thứ tự publish cùng aggregate nếu không có sequencing/ownership. Giữ một publisher cho aggregate hoặc serialize theo aggregate và kiểm tra version event. Retry topic có thể làm thay đổi thứ tự nên consumer phải xử lý trạng thái/version hợp lệ.

Kafka không có delayed queue built-in: retry worker dùng `nextAttemptAt`, giới hạn lần thử, DLQ và quy trình replay có audit. Không giữ transaction DB mở để sleep chờ retry. [Kafka delivery semantics](https://kafka.apache.org/documentation/#semantics)

## 15. Ứng dụng AIMS

### 15.1 Đầu vào triển khai

Cho từng service: image digest, CPU architecture, port, health/readiness endpoint, Secret riêng, migration command, Kafka topics/ACL và API contract. Không ràng buộc tên file chart đang được phát triển; tạo một bộ manifests/profile triển khai khớp các đầu vào này.

| Workload | Vai trò |
|---|---|
| frontend | Web UI, dùng cùng origin `/api` |
| api-gateway | Entry nghiệp vụ, JWT/routing |
| auth | Users, password hash, refresh token, roles |
| catalog | Product/category/price/media |
| cart | Giỏ hàng lưu PostgreSQL |
| order | Order và saga state |
| payment | Payment attempts/idempotency/refund |
| inventory | Stock/reservation/release |
| notification | Notification và delivery attempts |
| search-recommendation | PostgreSQL search projection/gợi ý |
| security-telemetry | Audit/detection ứng dụng, không chặn critical path |

Hai replica stateless/service, Service ClusterIP, PDB và topology spread theo hostname. Chạy non-root, drop capabilities, read-only root filesystem, tmp volume; không dùng quyền OCI/kubeconfig trong Pod nghiệp vụ nếu không cần.

### 15.2 Image và secrets

GHCR private cần imagePullSecret trong namespace Pod. Dùng `kubectl create secret docker-registry` với credential read-packages được nhập an toàn; Jenkins push credential riêng. Không đưa token vào ví dụ copy/paste lịch sử shell. Public images không cần pull secret. Tạo secrets runtime qua file mode 600 hoặc secret manager được quản trị cho lab.

Deployment mẫu service stateless, thay image và endpoint theo contract đã chốt:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
  namespace: aims
spec:
  replicas: 2
  selector:
    matchLabels: {app: api-gateway}
  template:
    metadata:
      labels: {app: api-gateway, aims-role: application}
    spec:
      automountServiceAccountToken: false
      imagePullSecrets: [{name: ghcr-pull}]
      securityContext:
        runAsNonRoot: true
        seccompProfile: {type: RuntimeDefault}
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels: {app: api-gateway}
      containers:
        - name: app
          image: ghcr.io/REPLACE_OWNER/aims-api-gateway@sha256:REPLACE_DIGEST
          ports: [{name: http, containerPort: 8000}]
          envFrom: [{secretRef: {name: api-gateway-runtime}}]
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
      volumes: [{name: tmp, emptyDir: {}}]
---
apiVersion: v1
kind: Service
metadata:
  name: api-gateway
  namespace: aims
spec:
  selector: {app: api-gateway}
  ports: [{name: http, port: 8000, targetPort: http}]
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: {name: api-gateway, namespace: aims}
spec:
  minAvailable: 1
  selector:
    matchLabels: {app: api-gateway}
```

### 15.3 Route web

Tạo frontend Deployment/Service port theo ứng dụng (mẫu 3000). Hoàn tất migration từng DB trước khi chuyển traffic. Thay web-smoke Ingress bằng Ingress AIMS; không giữ hai Ingress cùng host/path cạnh tranh.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: aims-web
  namespace: aims
spec:
  ingressClassName: aims-internal
  rules:
    - host: REPLACE_AIMS_HOSTNAME
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service: {name: api-gateway, port: {number: 8000}}
          - path: /
            pathType: Prefix
            backend:
              service: {name: aims-frontend, port: {number: 3000}}
```

Giữ prefix `/api` hoặc rewrite theo gateway contract, chỉ chọn một phương án. Cấu hình allowed hosts, CSRF trusted origins, secure cookies, redirect URL và payment callback bằng hostname HTTPS thật. Dùng payment sandbox trong lab.

### 15.4 NetworkPolicy

Sau khi policy engine đã được kiểm chứng, áp default-deny **ingress** trong `aims`, rồi allow Traefik→frontend/gateway, gateway→HTTP service cần thiết. Các service khác không nhận traffic trực tiếp từ ingress. Thêm egress deny có allow DNS, PostgreSQL 5432, Kafka 9093 và provider cần dùng ở bước hardening tiếp theo; không áp egress deny-all trước khi có đầy đủ dependency rules.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: default-deny-ingress, namespace: aims}
spec:
  podSelector: {}
  policyTypes: [Ingress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: ingress-to-web, namespace: aims}
spec:
  podSelector:
    matchExpressions:
      - key: app
        operator: In
        values: [api-gateway, aims-frontend]
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels: {kubernetes.io/metadata.name: ingress-system}
      ports:
        - {protocol: TCP, port: 8000}
        - {protocol: TCP, port: 3000}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: gateway-to-business, namespace: aims}
spec:
  podSelector:
    matchLabels: {aims-role: business}
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels: {app: api-gateway}
      ports: [{protocol: TCP, port: 8000}]
```

Gắn `aims-role: business` cho services tương ứng. Nếu contract có service→service HTTP, thêm rule đúng cặp; Kafka không cần mở ingress HTTP giữa chúng. Namespace data/kafka cần allow operator, replication, health probes và client; không copy default-deny aims sang đó mà thiếu rule điều khiển.

## 16. Jenkins và Argo CD

### 16.1 Jenkins manual setup

```bash
helm repo add jenkins https://charts.jenkins.io
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
export AIMS_JENKINS_CHART_VERSION='REPLACE_TESTED_CHART_VERSION'
export AIMS_ARGOCD_CHART_VERSION='REPLACE_TESTED_CHART_VERSION'
helm upgrade --install jenkins jenkins/jenkins \
  --version "$AIMS_JENKINS_CHART_VERSION" -n cicd \
  --set controller.serviceType=ClusterIP \
  --set persistence.storageClass=aims-bv-retain --set persistence.size=20Gi
helm upgrade --install argocd argo/argo-cd \
  --version "$AIMS_ARGOCD_CHART_VERSION" -n argocd \
  --set server.service.type=ClusterIP
```

Truy cập UI qua `kubectl port-forward`, sau khi tunnel Bastion mở. Lấy initial admin password từ secret đúng chart trên terminal cá nhân, đổi password và không lưu vào evidence.

```bash
kubectl -n cicd port-forward svc/jenkins 18081:8080
# Terminal khác:
kubectl -n argocd port-forward svc/argocd-server 18443:443
```

Jenkins **Manage Jenkins → Clouds → Kubernetes**: controller dùng in-cluster API để tạo ephemeral agents trong `cicd`; RBAC chỉ agent resources cần dùng. Controller có quyền này không có nghĩa build job được quyền deploy `aims`. Executors trên controller = 0, job concurrency = 1, đặt CPU/memory limit cho agents.

Credentials: source read, GHCR push, GitOps write, Cosign key pair nếu chọn key-based signing. Token Git có phạm vi repository; hạn chế nhánh bằng repository rulesets/branch protections hoặc dùng repo GitOps riêng, không giả định token có scope riêng một branch. Jenkins private dùng Poll SCM hoặc chạy job manual trong lab; không mở public webhook/admin UI chỉ để tự trigger.

### 16.2 Chuỗi CI

```text
checkout → test → build → scan → SBOM → push image → lấy digest
→ sign/attest digest trên registry → verify → cập nhật GitOps digest
```

Chọn builder tương thích Pod Security của namespace build; không mount Docker socket host. Nếu BuildKit cần cấu hình user namespace/privilege khác, dùng agent build được cô lập với quyền phù hợp và ghi ngoại lệ. Không đổi bảo mật namespace ứng dụng để làm build chạy.

Ký registry artifact sau khi push: Cosign thông thường ký `registry/image@sha256:...` đã tồn tại. Có thể dùng Jenkins key-based hoặc GitHub Actions keyless, nhưng admission policy phải tin đúng signer đã chọn. Kyverno là phần mở rộng nếu muốn enforcement; không coi nó đã có sẵn chỉ vì có bước Cosign.

### 16.3 Argo CD

Chốt nhánh triển khai `gitops-oci`; đường dẫn `deploy/oci/aims` trong ví dụ là **đầu vào cần tạo**, chứa các manifests/profile của kiến trúc đích. Không trỏ Application tới path chưa tồn tại.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata: {name: aims-oci, namespace: argocd}
spec:
  sourceRepos: [https://github.com/tndat-dev/An-Internet-Media-Store.git]
  destinations:
    - namespace: aims
      server: https://kubernetes.default.svc
  namespaceResourceWhitelist:
    - group: '*'
      kind: '*'
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata: {name: aims-oci, namespace: argocd}
spec:
  project: aims-oci
  source:
    repoURL: https://github.com/tndat-dev/An-Internet-Media-Store.git
    targetRevision: gitops-oci
    path: deploy/oci/aims
  destination:
    server: https://kubernetes.default.svc
    namespace: aims
  syncPolicy:
    syncOptions: [CreateNamespace=false, PruneLast=true]
```

Với GitOps private repo: **Settings → Repositories → Connect repo** bằng deploy key read-only. AppProject này quản lý ứng dụng namespace aims; operators/data/ingress bootstrap bằng Helm/manual không nằm trong Application này. Không đưa passwords vào manifests Git.

Lần đầu Sync manual, kiểm tra diff, Healthy và migration. Khi ổn mới bật automated selfHeal; bật prune sau khi xác minh path chỉ chứa resource muốn Argo quản lý. Từ lúc bàn giao, Jenkins chỉ cập nhật GitOps, Argo là actor deploy workload ứng dụng. Không dùng `kubectl apply` cạnh tranh với Argo cho cùng resource.

Rollback: revert commit digest trên `gitops-oci`, Sync, xác nhận image quay về. Migration DB phải backward-compatible; rollback image không tự rollback schema/data. [Argo CD declarative setup](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/), [Jenkins chart](https://github.com/jenkinsci/helm-charts)

## 17. Backup và vận hành

### 17.1 Backup PostgreSQL manual để nghiệm thu lab

Backup lưu ra bucket ngoài cluster. Cách tối thiểu dùng logical backup từng DB qua primary, đưa file về máy thao tác rồi upload OCI; không phải PITR. Với dữ liệu lớn/chạy lâu dài, cấu hình CNPG backup plugin + WAL archive đã kiểm chứng tương thích OCI Object Storage, retention và restore.

```bash
umask 077
AIMS_PRIMARY=$(kubectl -n data get cluster aims-postgres -o jsonpath='{.status.currentPrimary}')
AIMS_BACKUP_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
kubectl -n data exec "$AIMS_PRIMARY" -- \
  pg_dump -U postgres -Fc aims_order > "$AIMS_WORKDIR/aims_order-$AIMS_BACKUP_STAMP.dump"
oci os object put --bucket-name 'REPLACE_BACKUP_BUCKET' \
  --namespace-name 'REPLACE_OBJECT_STORAGE_NAMESPACE' \
  --file "$AIMS_WORKDIR/aims_order-$AIMS_BACKUP_STAMP.dump" \
  --name "postgres/aims_order-$AIMS_BACKUP_STAMP.dump"
```

Lặp cho chín DB và backup roles bằng `pg_dumpall --globals-only` trong file hạn chế quyền. Backup logical riêng từng DB không tạo snapshot nhất quán toàn bộ saga giữa chín DB; cần quy trình tạm dừng ghi/đối soát khi khôi phục toàn hệ thống.

Restore drill: download backup, tạo `aims_order_restore`, dùng `pg_restore --no-owner --no-acl` vào DB thử qua primary, so sánh row count và kiểm tra nghiệp vụ. Không restore đè DB đang chạy để kiểm thử. Ghi thời gian bắt đầu/kết thúc và backup timestamp để tính RTO/RPO đo được.

```bash
kubectl -n data exec "$AIMS_PRIMARY" -- \
  psql -U postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE aims_order_restore;'
kubectl -n data exec -i "$AIMS_PRIMARY" -- \
  pg_restore -U postgres --exit-on-error --no-owner --no-acl -d aims_order_restore \
  < "$AIMS_WORKDIR/aims_order-$AIMS_BACKUP_STAMP.dump"
```

Không xem ba replica Kafka là backup chống xóa topic. Giữ topic/user config trong Git, xác định retention và khả năng tái dựng projection; nếu yêu cầu DR event history, thiết kế replication/archive riêng. Jenkins PVC backup chứa credential phải được mã hóa và hạn chế quyền đọc.

### 17.2 Theo dõi tối thiểu

| Theo dõi | Cách làm |
|---|---|
| Network path | FW traffic/threat logs, LB backend health, VCN Flow Logs |
| Public web | HTTPS synthetic request, HTTP status và latency |
| Kubernetes | Pod restarts, Pending, node pressure, requests/allocatable |
| Kafka | ISR, offline partitions, consumer lag, dung lượng PVC |
| PostgreSQL | Primary/replica health, replication lag, disk, backup gần nhất |
| Bảo mật | WAF block logs, Cloud Guard problems, Security Zone rejection |
| Chứng chỉ | Domain cert, Kafka client/CA, PostgreSQL CA và lịch rotation |
| Chi phí | Budget alerts, firewall/LB uptime, Block Volume còn giữ |

Đặt log retention ví dụ 7–14 ngày cho lab. Dự trữ dung lượng và tài nguyên để khi một worker mất, các workload còn quorum chạy được trên hai node còn lại. PDB bảo vệ voluntary disruption, không đảm bảo chống mất nguồn VM/AD.

## 18. Nghiệm thu và xử lý lỗi

### 18.1 Checklist theo gate

| Gate | Thao tác | Kết quả cần lưu |
|---|---|---|
| G1 IAM | Identity OE sửa Hub resource | Bị từ chối, không do thiếu login |
| G2 SZ | Tạo public subnet dưới OE | API bị Security Zone từ chối |
| G3 OKE | `kubectl get nodes -o wide` | Đúng 3 Ready, private IP |
| G4 Storage | CNPG/Kafka pods dùng PVC | PVC Bound, volumes đúng compartment, replicas khác node |
| G5 Inbound | Client ngoài Internet gọi web mẫu | 200 + TLS hợp lệ + Hub FW backend log |
| G6 Egress | Pod HTTPS tới GHCR/GitHub, rồi tạm Drop egress rule lab | Allowed trước, blocked sau; có FW log, khôi phục rule |
| G7 WAF | Request SQLi/rate-limit theo rule đã bật | Bị chặn + log đúng rule ID |
| G8 Cloud Guard | Bucket rỗng public trong security-test | Problem đúng resource sau detector scan; chuyển lại private/xóa |
| G9 Isolation | Pod thử không được phép gọi service nội bộ | Kết nối bị NetworkPolicy chặn |
| G10 AIMS | Browse/login/cart/checkout sandbox | Order hoàn thành, inventory/payment/notification đúng |
| G11 Saga | Payment thất bại, duplicate event, crash consumer | Release stock, không trả tiền/notify lặp; DLQ khi hết retry |
| G12 GitOps | Đổi digest rồi revert | Argo Synced/Healthy, image đúng hai lần |
| G13 Restore | Restore backup vào DB thử | Nội dung đúng, RTO/RPO được đo |
| G14 Một node lỗi | Drain một worker sau khi xác nhận budget/quorum | Dịch vụ duy trì theo tiêu chí lab, phục hồi và uncordon |

G6 ảnh hưởng egress của lab; không sửa policy firewall dùng chung với resource ngoài lab. G8 không dùng bucket có dữ liệu; không hứa problem xuất hiện trong số phút cố định vì detector có chu kỳ. G14 có thể làm replica thứ ba Kafka/CNPG Pending do anti-affinity; mục tiêu quorum trên hai node, không ép ba replica chung hai node.

### 18.2 OE02 tùy chọn

Tạo compartment OE02/spoke `10.2.0.0/16` và một VM hoặc Pod thử private, không cần OKE thứ hai. Gắn cùng DRG theo mục 8. Baseline FW Drop OE01↔OE02. Thử TCP vào một listener thực sự đang mở ở OE02: bị Drop có log. Thêm rule Allow hẹp cho đúng nguồn/đích/port, thử lại thành công, rồi rollback rule. Chỉ ping thất bại không đủ chứng minh firewall cách ly.

### 18.3 Troubleshooting theo triệu chứng

| Triệu chứng | Kiểm tra theo thứ tự |
|---|---|
| Node không Ready | Quota/capacity → boot image → SGW/443 → API rules 6443/12250 → CNI/IP availability |
| kubectl timeout | Session Active → SSH tunnel local port → Bastion allowlist → API NSG → token/CA |
| LB pending | Service events → cluster principal quyền subnet/NSG/LB → Security Zone → quota |
| Public LB backend Unhealthy | `/ping` private LB → NodePort 32080 → NSG → LB subnet route→FW → return DRG ingress→FW |
| Internet egress chỉ đi được một chiều | Hub attachment VCN table → FW default→NAT → NAT return table→FW |
| WAF policy có nhưng không block | Association với LB → rule enabled/action → request match → logs |
| Pod ImagePullBackOff | DNS/443 qua NAT → registry credential → digest tồn tại → image architecture |
| Pod Pending PVC | WaitForFirstConsumer → CSI events → AD attachment → quota/storage/CMK permissions |
| Kafka TLS/authorization lỗi | Broker DNS → CA/cert/key mount → expiry → ACL topic/group → namespace Secret copy |
| Argo không deploy commit | targetRevision và path → repo auth → manifests/schema → sync policy |
| Web login redirect HTTP/CSRF | Forwarded proto/Host → trusted proxy → public URL/allowed origins/cookies |
| Cloud Guard không có problem | Target hiệu lực sau SZ → recipe/rule → region → thời điểm scan/resource đã bị preventive chặn |

Lưu evidence theo gate vào thư mục riêng: ảnh Console, resource OCID đã che phần cần thiết, command output không chứa secret, timestamp UTC, kết quả expected/actual. Không ghi “đã pass” nếu chưa chạy phép thử.

## 19. Dọn dẹp

Thực hiện sau khi đã giữ backup/evidence cần thiết; không dùng script xóa toàn tenancy hoặc parent dùng chung.

1. Dừng Jenkins trigger, tắt auto-sync của Application, quyết định giữ/xóa workload Argo quản lý. Xóa Application không có resources-finalizer có thể để lại workload; kiểm tra thay vì giả định cascade.
2. Gỡ WAF association/public listener nếu muốn ngừng web, xóa DNS record lab.
3. Xóa workload AIMS/web-smoke, uninstall Traefik và **chờ cloud controller xóa Private LB** khi cluster còn hoạt động.
4. Backup rồi xóa CNPG Cluster/Kafka CR khi operators còn chạy; `deleteClaim:false` và StorageClass Retain có thể giữ PVC/PV/Block Volumes. Ghi volume còn giữ và xóa riêng nếu chắc không cần.
5. Uninstall Jenkins/Argo/operators, xóa node pool rồi OKE cluster; kiểm tra boot volumes/CSI volumes/LB còn sót.
6. Xóa Public LB, WAF resource/policy lab, Bastion sessions/resource, firewall và policy sau khi không còn attachment sử dụng.
7. Xóa DRG routes/attachments, gateways, subnets/VCN; kiểm tra private endpoints/VNIC chặn xóa.
8. Giữ hoặc xóa backup bucket theo yêu cầu. Key/Vault chỉ schedule deletion sau khi mọi dữ liệu cần key đã hết thời hạn giữ.
9. Gỡ Security Zones và Cloud Guard targets/recipes của lab theo dependency; xác minh phạm vi parent không bị thay đổi ngoài ý muốn.
10. Xóa compartments từ lá lên `tndat-lz-cmp`; không xóa/sửa `mb-home-cmp` hoặc policy của người khác. Kiểm tra Cost Analysis sau cleanup cho volume/IP/resource còn giữ.

## 20. Nguồn và cách sử dụng sơ đồ

Nguồn được liên kết ngay tại các bước liên quan. Các trang `master`, `latest` có thể thay đổi; lúc triển khai ghi commit/version vào inventory. Thiết kế lab bổ sung Traefik, namespace layout, Spoke SGW, Security Zone baseline và sizing; đây là quyết định triển khai riêng dựa trên mục tiêu AIMS.

- [OCI Open LZ](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities)
- [Multi-OE Generic v1 design](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/blob/master/blueprints/multi-oe/generic_v1/design/readme.md)
- [Hub models](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/tree/master/addons/oci-hub-models)
- [OCI graphics for architecture diagrams](https://docs.oracle.com/en-us/iaas/Content/General/Reference/graphicsfordiagrams.htm)
- [Oracle OCI Draw.io library ZIP](https://docs.oracle.com/iaas/Content/Resources/Assets/OCI-Style-Guide-for-Drawio.zip)

Mở `OCI_AIMS_ARCHITECTURE.drawio` trong draw.io Snap bằng File → Open From → Device hoặc:

```bash
drawio /home/tndat/An-Internet-Media-Store/docs/oci/OCI_AIMS_ARCHITECTURE.drawio
```

Trang 1 biểu diễn ownership và thành phần; trang 2 biểu diễn các luồng/route; trang 3 biểu diễn OKE, dữ liệu và CI/CD. Icon OCI được nhúng trong file để diagram có thể mở trên máy khác mà không phụ thuộc đường dẫn library. Kafka, PostgreSQL, Jenkins và Argo CD là workload phần mềm, không bị gắn nhãn nhầm thành OCI Streaming/OCI Database/OCI DevOps.

### Ghi nhận kiểm tra artifact

- Markdown: các khối YAML đã parse và khối Bash đã kiểm tra cú pháp; đây không phải chạy lệnh trên OCI.
- Traefik: render local bằng Helm 3.19.0, chart 41.5.0, Kubernetes target 1.34.0; Service chỉ expose port 80/NodePort 32080, probes `/ping` port 8000.
- KafkaNodePool, Kafka, KafkaTopic và KafkaUser mẫu đã kiểm tra với CRD schema Strimzi 1.2.0 (`v1`); Kafka version vẫn phải điền theo release operator thực tế.
- Draw.io: ba trang XML editable, icon stencil OCI nhúng sẵn; đã xuất PDF bằng draw.io Snap.
- Các trạng thái/quyền/quota/version trong tenancy và kiểm thử end-to-end phải được xác nhận khi thực hiện runbook.
