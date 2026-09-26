# Runbook Terraform: dựng OCI Operating Entity từ đầu

Tài liệu này hướng dẫn một người chưa từng dùng Terraform dựng **phần nền Landing Zone của OE01** trên OCI. Mã nguồn đã được thử nghiệm bằng một OE02 tạm thời trong tenancy `svtechcloud`: tạo đủ tài nguyên, kiểm tra trạng thái, chạy lại plan không có drift rồi destroy.

> **Ranh giới quan trọng:** OE01 hiện tại của dự án AIMS đang chạy thật. Không chạy cấu hình `oe01.tfvars` vào tenancy hiện tại vì tên và CIDR sẽ trùng tài nguyên đang có. File OE01 là mẫu cho một lần dựng mới hoàn toàn hoặc cho quá trình import có kế hoạch. Bài kiểm thử dùng `oe02-tf-test`, state riêng và CIDR `10.2.0.0/16`.

## 1. Terraform là gì?

Terraform là công cụ Infrastructure as Code. Thay vì bấm từng tài nguyên trong OCI Console, ta mô tả trạng thái mong muốn bằng các file `.tf`, xem trước thay đổi rồi cho Terraform gọi OCI API.

Các khái niệm cần nhớ:

| Khái niệm | Ý nghĩa trong bài này |
|---|---|
| Provider | Plugin `oracle/oci` giúp Terraform gọi OCI API. |
| Resource | Tài nguyên Terraform sở hữu, ví dụ VCN, subnet hoặc compartment. |
| Data source | Dữ liệu chỉ đọc, ví dụ danh sách OCI Services và Security Zone recipe của Oracle. |
| Variable | Giá trị khác nhau theo môi trường: tenancy OCID, CIDR, DRG OCID. |
| Output | OCID được xuất sau apply để dùng cho OKE hoặc workload. |
| State | File ánh xạ resource trong code với OCID thật. Mất state có thể làm Terraform không còn biết tài nguyên nào do nó quản lý. |
| Plan | Bản xem trước Terraform định tạo, sửa hoặc xóa gì. |
| Apply | Áp dụng đúng plan lên OCI. |
| Destroy | Xóa các resource đang có trong state đó. |
| Drift | Cấu hình thật trên OCI bị thay đổi ngoài Terraform nên khác code/state. |
| Idempotence | Apply xong chạy lại plan phải báo `No changes`. |

Terraform không tự hiểu tài nguyên đã tạo thủ công là của nó. Không chỉ đổi tên file thành `oe01` rồi chạy vào hệ thống đang có. Với hạ tầng có sẵn, phải dùng `terraform import` và review từng resource.

Tài liệu chính thức:

- [Install Terraform CLI](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)
- [OCI Terraform Provider](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/)
- [OCI Provider setup tutorial](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/tutorials/tf-provider.htm)
- [Oracle OCI Landing Zone Operating Entities](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities)
- [Oracle Hub Models](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/tree/master/addons/oci-hub-models)

## 2. Kiến trúc mà code tạo

Một lần apply tạo các thành phần sau:

1. Cây compartment:
   - `cmp-oe01`
   - `cmp-oe01-common`
   - `cmp-oe01-common-infra`
   - `cmp-oe01-common-network`
   - `cmp-oe01-development`
   - `cmp-oe01-sensitive-data`
2. IAM group `grp-oe01-admins` và policy chỉ cho phép quản trị trong OE01.
3. Một spoke VCN `/16` trong `common-network`.
4. Năm private subnet cho OKE API, worker, load balancer, bastion và pod.
5. NAT Gateway cục bộ của OE và Service Gateway.
6. Route tới Hub VCN qua DRG; default internet egress đi qua NAT Gateway của chính OE.
7. DRG attachment vào DRG dùng chung và đúng một route trả về CIDR của OE trong DRG route table phía Hub.
8. Security List nền và các NSG dành cho API, worker, pod và load balancer.
9. VCN Flow Logs cho năm subnet, retention 30 ngày.
10. Maximum Security Zone trong compartment `sensitive-data`.

DRG và Hub VCN là tài nguyên dùng chung. Terraform root này chỉ nhận OCID của chúng và không sở hữu chúng. Vì vậy destroy OE không thể xóa DRG, Hub VCN hoặc Public Load Balancer.

Cloud Guard đã được bật ở cấp tenancy `svtechcloud`, nên `create_cloud_guard_target` mặc định là `false`; OE kế thừa target tenancy. Security Zone vẫn được tạo riêng để chặn thao tác vi phạm recipe trong `sensitive-data`.

WAF không nằm trong root OE này. WAF phải gắn với public endpoint ở Hub và nên thuộc shared-services state. OKE và AIMS cũng là workload layer, nên dùng state riêng sau khi OE foundation ổn định.

Network Firewall đã được loại khỏi data path ngày 2026-09-25. Mỗi OE dùng NAT Gateway cục bộ cho egress, còn DRG dùng cho lưu lượng Hub/spoke. Thiết kế này tránh tuyến NAT Hub trả ngược về DRG, loại tuyến mà OCI không cho phép nếu không có private-IP middlebox.

## 3. Cấu trúc mã nguồn

Thư mục làm việc:

```text
infra/terraform/oci-oe-foundation/
├── versions.tf
├── providers.tf
├── variables.tf
├── locals.tf
├── compartments.tf
├── iam.tf
├── network.tf
├── security.tf
├── observability.tf
├── outputs.tf
└── environments/
    ├── oe01.tfvars.example
    ├── oe01.backend.hcl.example
    ├── oe02-test.tfvars.example
    └── oe02-test.backend.hcl.example
```

`versions.tf` khóa Terraform `>= 1.16, < 2.0` và OCI provider `8.29.0`. File `.terraform.lock.hcl` phải được commit để các máy dùng cùng provider.

## 4. Điều kiện trước khi bắt đầu

Máy thao tác cần có:

- Linux x86-64 hoặc điều chỉnh gói cài đúng hệ điều hành.
- `curl`, `unzip`, `sha256sum`, Git và OCI CLI.
- OCI API key profile hoạt động trong `~/.oci/config`.
- Quyền tạo compartment, group, policy, network, Logging, Security Zone và DRG attachment.
- CIDR OE không trùng Hub hay OE khác.
- OCID của Landing Zone parent compartment, DRG và hai DRG route table.

Kiểm tra OCI CLI trước:

```bash
oci --version
oci iam region-subscription list --all --output table
oci iam compartment get \
  --compartment-id ocid1.compartment.oc1..REPLACE_ME \
  --output table
```

Nếu lệnh OCI trả `NotAuthenticated`, sửa profile OCI trước khi dùng Terraform. Terraform provider trong bài dùng cùng profile đó.

## 5. Cài Terraform CLI không cần quyền root

Ví dụ dưới đây cài Terraform 1.16.4 vào `~/.local/bin` và kiểm tra checksum chính thức:

```bash
tf_ver=1.16.4
tf_os=linux
tf_arch=amd64
install_dir="$HOME/.local/bin"
download_dir="$HOME/Downloads/terraform-${tf_ver}"

mkdir -p "$install_dir" "$download_dir"

curl -fsSLo "$download_dir/terraform.zip" \
  "https://releases.hashicorp.com/terraform/${tf_ver}/terraform_${tf_ver}_${tf_os}_${tf_arch}.zip"

curl -fsSLo "$download_dir/SHA256SUMS" \
  "https://releases.hashicorp.com/terraform/${tf_ver}/terraform_${tf_ver}_SHA256SUMS"

expected=$(awk -v file="terraform_${tf_ver}_${tf_os}_${tf_arch}.zip" \
  '$2 == file {print $1}' "$download_dir/SHA256SUMS")
actual=$(sha256sum "$download_dir/terraform.zip" | awk '{print $1}')

test -n "$expected"
test "$expected" = "$actual"

unzip -oq "$download_dir/terraform.zip" -d "$install_dir"
chmod 0755 "$install_dir/terraform"
export PATH="$HOME/.local/bin:$PATH"

terraform version
```

Để giữ PATH sau khi mở terminal mới:

```bash
printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
source "$HOME/.bashrc"
```

Kết quả mong đợi:

```text
Terraform v1.16.4
on linux_amd64
```

## 6. Chuẩn bị cấu hình OE01

Đi vào Terraform root:

```bash
cd /home/tndat/An-Internet-Media-Store/infra/terraform/oci-oe-foundation
```

Tạo file môi trường thật từ mẫu. Các file thật bị `.gitignore` loại bỏ vì có thể chứa thông tin tenancy:

```bash
cp environments/oe01.tfvars.example environments/oe01.tfvars
cp environments/oe01.backend.hcl.example environments/oe01.backend.hcl
mkdir -p state plans
```

Mở `environments/oe01.tfvars` và thay toàn bộ `REPLACE_ME`:

```hcl
tenancy_ocid                = "ocid1.tenancy.oc1..REPLACE_ME"
landing_zone_compartment_id = "ocid1.compartment.oc1..REPLACE_ME"
region                      = "ap-tokyo-1"
oci_profile                 = "DEFAULT"

oe_code                    = "oe01"
name_suffix                = ""
deployment_acknowledgement = "CREATE-OE01"
vcn_cidr                   = "10.1.0.0/16"
hub_vcn_cidr               = "10.0.0.0/16"

drg_id                 = "ocid1.drg.oc1.ap-tokyo-1.REPLACE_ME"
drg_route_table_id     = "ocid1.drgroutetable.oc1.ap-tokyo-1.REPLACE_WITH_FROM_SPOKE"
hub_drg_route_table_id = "ocid1.drgroutetable.oc1.ap-tokyo-1.REPLACE_WITH_FROM_HUB"
```

Ý nghĩa hai DRG route table:

- `drg_route_table_id`: bảng dùng khi traffic đi từ OE spoke vào DRG; thường chứa default route về Hub attachment.
- `hub_drg_route_table_id`: bảng dùng khi traffic đi từ Hub vào DRG; Terraform thêm route CIDR OE trỏ tới attachment vừa tạo.

Kiểm tra OCID và tên bảng:

```bash
oci network drg-route-table list \
  --drg-id ocid1.drg.oc1.ap-tokyo-1.REPLACE_ME \
  --all \
  --query 'data[].{name:"display-name",id:id,state:"lifecycle-state"}' \
  --output table
```

Chốt chống nhầm `deployment_acknowledgement` phải khớp chính xác `CREATE-` cộng prefix viết hoa. Terraform dừng trước khi tạo compartment nếu chuỗi này sai.

## 7. Format và kiểm tra code tĩnh

```bash
terraform fmt -recursive -check
terraform init -backend=false -input=false
terraform validate
```

Kết quả `terraform validate` phải là:

```text
Success! The configuration is valid.
```

`validate` chỉ kiểm tra cú pháp/schema. Nó chưa chứng minh tài khoản có quyền hoặc OCID tồn tại.

## 8. Khởi tạo backend riêng cho OE01

State trong lab nằm ở `state/oe01.tfstate`. `TF_DATA_DIR` cũng tách plugin/backend metadata khỏi môi trường khác:

```bash
TF_DATA_DIR=.terraform-oe01 terraform init \
  -reconfigure \
  -input=false \
  -backend-config=environments/oe01.backend.hcl
```

Không copy state OE02 thành state OE01. Không commit `state/`, `.terraform*`, file plan hoặc file `.tfvars` thật.

Local state phù hợp cho lab một người. Với môi trường nhóm, chuyển sang OCI Resource Manager hoặc backend từ xa có mã hóa, versioning và locking trước khi nhiều người cùng apply.

## 9. Tạo và review plan

Luôn lưu plan ra file:

```bash
TF_DATA_DIR=.terraform-oe01 terraform plan \
  -input=false \
  -var-file=environments/oe01.tfvars \
  -out=plans/oe01.tfplan
```

Với OE mới hoàn toàn, summary phải chỉ có `to add`. Dừng nếu thấy:

- `to destroy` khác 0;
- `to change` trên shared DRG/Hub;
- tên chứa OE khác;
- CIDR không đúng;
- Terraform định tạo DRG, Hub VCN hoặc Public LB dùng chung.

Xem plan không màu để lưu bằng chứng:

```bash
TF_DATA_DIR=.terraform-oe01 terraform show -no-color plans/oe01.tfplan \
  | tee plans/oe01.tfplan.txt
```

File plan nhị phân có thể chứa dữ liệu nhạy cảm và bị `.gitignore`; không gửi công khai.

## 10. Apply đúng plan đã review

```bash
TF_DATA_DIR=.terraform-oe01 terraform apply \
  -input=false \
  plans/oe01.tfplan
```

Không chạy `terraform apply` không kèm plan file sau khi đã review. Apply không kèm file sẽ tạo plan mới tại thời điểm chạy.

Xem output:

```bash
TF_DATA_DIR=.terraform-oe01 terraform output
TF_DATA_DIR=.terraform-oe01 terraform output -json > /tmp/oe01-outputs.json
```

Output `network.subnet_ids` và `network.nsg_ids` là đầu vào cho state OKE sau này.

## 11. Kiểm tra sau apply

### 11.1 Idempotence

```bash
TF_DATA_DIR=.terraform-oe01 terraform plan \
  -input=false \
  -detailed-exitcode \
  -var-file=environments/oe01.tfvars
```

Exit code có ý nghĩa:

- `0`: không có thay đổi, đạt.
- `1`: lỗi.
- `2`: có thay đổi hoặc drift; phải review.

### 11.2 State

```bash
TF_DATA_DIR=.terraform-oe01 terraform state list | sort
```

Không sửa trực tiếp file state bằng editor.

### 11.3 VCN và DRG attachment

Lấy OCID từ output rồi kiểm tra:

```bash
vcn_id=$(TF_DATA_DIR=.terraform-oe01 terraform output -json \
  | jq -r '.network.value.vcn_id')

attachment_id=$(TF_DATA_DIR=.terraform-oe01 terraform output -json \
  | jq -r '.network.value.drg_attachment_id')

oci network vcn get \
  --vcn-id "$vcn_id" \
  --query 'data.{name:"display-name",state:"lifecycle-state",cidrs:"cidr-blocks"}' \
  --output table

oci network drg-attachment get \
  --drg-attachment-id "$attachment_id" \
  --query 'data.{name:"display-name",state:"lifecycle-state",route_table:"drg-route-table-id"}' \
  --output table
```

VCN phải `AVAILABLE`; attachment phải `ATTACHED`.

### 11.4 Security Zone

```bash
security_zone_id=$(TF_DATA_DIR=.terraform-oe01 terraform output -raw security_zone_id)

oci cloud-guard security-zone get \
  --security-zone-id "$security_zone_id" \
  --query 'data.{name:"display-name",state:"lifecycle-state",recipe:"security-zone-recipe-id"}' \
  --output table
```

State phải `ACTIVE`.

### 11.5 Flow logs

Vào OCI Console theo thứ tự:

1. **Observability & Management**.
2. **Logging**.
3. **Log Groups**.
4. Chọn compartment `cmp-oe01-common-network`.
5. Mở `log-oe01-network`.
6. Xác nhận năm log `flow-oe01-*` đều Enabled và retention 30 ngày.

Flow log không có record nếu subnet chưa có VNIC/traffic; trạng thái Enabled vẫn chứng minh cấu hình log đã được tạo đúng.

## 12. Triển khai OKE sau OE foundation

Không đặt OKE vào cùng state OE foundation. Tạo root riêng, ví dụ `infra/terraform/oci-oke`, rồi truyền các output sau:

- `compartment_ids.development` cho cluster/node pool;
- `network.subnet_ids.api` cho private Kubernetes API endpoint;
- `network.subnet_ids.workers` cho node pool;
- `network.subnet_ids.pods` cho VCN-native pod networking;
- `network.subnet_ids.lb` cho internal load balancer;
- các NSG tương ứng.

Cách tách state này cho phép nâng cấp hoặc thay OKE mà không đặt cây compartment và VCN vào destroy plan của workload.

## 13. Thao tác hằng ngày

Trước mọi thay đổi:

```bash
git pull
cd /home/tndat/An-Internet-Media-Store/infra/terraform/oci-oe-foundation
terraform fmt -recursive -check
terraform validate
TF_DATA_DIR=.terraform-oe01 terraform plan \
  -input=false \
  -var-file=environments/oe01.tfvars
```

Không sửa tài nguyên Terraform quản lý trên Console. Nếu buộc phải sửa khẩn cấp, ghi lại thay đổi và chạy plan để phát hiện drift.

Không dùng `-target` trong quy trình thường ngày. `-target` có thể tạo trạng thái một phần và chỉ phù hợp khi khắc phục sự cố có phân tích cụ thể.

## 14. Destroy một OE test

Không dùng phần này cho OE01 đang phục vụ AIMS.

Tạo destroy plan:

```bash
TF_DATA_DIR=.terraform-oe02-test terraform plan \
  -destroy \
  -input=false \
  -var-file=environments/oe02-test.tfvars \
  -out=plans/oe02-test-destroy.tfplan
```

Review summary và tên resource. Plan test đã được chấp nhận khi có `41 to destroy`, không chứa `oe01` và không chứa shared Hub resource.

Apply destroy plan:

```bash
TF_DATA_DIR=.terraform-oe02-test terraform apply \
  -input=false \
  plans/oe02-test-destroy.tfplan
```

OCI xóa compartment theo cơ chế bất đồng bộ, nên bước này có thể lâu hơn xóa VCN. Không dừng Terraform giữa chừng.

Sau destroy:

```bash
TF_DATA_DIR=.terraform-oe02-test terraform state list
```

State phải không còn resource được quản lý. Data source không tạo tài nguyên và không xuất hiện sau khi state được làm sạch.

## 15. Kết quả kiểm thử OE02 ngày 2026-09-25

Môi trường kiểm thử:

- Terraform CLI `1.16.4`, checksum đã xác minh.
- OCI provider `8.29.0`.
- Region `ap-tokyo-1`.
- Prefix `oe02-tf-test`.
- VCN `10.2.0.0/16`.
- Shared DRG được tham chiếu bằng OCID, không thuộc state test.

Kết quả:

| Kiểm tra | Kết quả |
|---|---|
| `terraform fmt` | Đạt |
| `terraform validate` | Đạt |
| Plan trước apply | `41 add, 0 change, 0 destroy` |
| Apply | `41 added, 0 changed, 0 destroyed` |
| Plan sau apply | `No changes`, exit code `0` |
| VCN | `AVAILABLE` |
| DRG attachment | `ATTACHED` |
| DRG route `10.2.0.0/16` | Không conflict |
| Maximum Security Zone | `ACTIVE` |
| Năm VCN flow log | `ACTIVE`, Enabled, retention 30 ngày |
| AIMS trong OE01 trong lúc test | HTTP `200` |
| Destroy plan | `41 delete`, không có OE01/Hub resource |
| Destroy cuối cùng | Hoàn tất; toàn bộ 41 resource OE02 test đã được loại khỏi state |
| State sau destroy | Rỗng; không còn resource Terraform-owned của `cmp-oe02-tf-test` |

## 16. Xử lý lỗi thường gặp

### `NotAuthenticated`

```bash
oci iam region-subscription list --profile DEFAULT --all
```

Kiểm tra user OCID, tenancy OCID, fingerprint, private key path và quyền file private key trong `~/.oci/config`.

### `NotAuthorizedOrNotFound`

OCID có thể đúng nhưng profile không có quyền đọc/tạo resource. Xác nhận policy của tài khoản chạy Terraform tại tenancy và Landing Zone parent.

### `InvalidParameter` khi tạo route

Kiểm tra loại route table và next hop. OCI không cho route table gắn với NAT Gateway trỏ thẳng tới DRG; đó là lý do mỗi OE dùng NAT Gateway cục bộ trong kiến trúc hiện tại.

### Security Zone recipe null

Code tự chọn Oracle-owned recipe có tên chứa `maximum`. Nếu tenancy/region không trả recipe đó, lấy recipe OCID hợp lệ rồi đặt trực tiếp:

```hcl
security_zone_recipe_id = "ocid1.securityzonessecurityrecipe.oc1..REPLACE_ME"
```

### Apply lỗi giữa chừng

Không xóa state. Chạy lại:

```bash
TF_DATA_DIR=.terraform-oe01 terraform plan \
  -input=false \
  -var-file=environments/oe01.tfvars
```

Terraform refresh state và chỉ đề xuất phần còn thiếu. Sửa nguyên nhân, review plan mới rồi apply.

### Compartment destroy lâu

Kiểm tra lifecycle:

```bash
oci iam compartment get \
  --compartment-id ocid1.compartment.oc1..REPLACE_ME \
  --query 'data.{name:name,state:"lifecycle-state"}' \
  --output table
```

`DELETING` là trạng thái bình thường trong lúc IAM control plane hoàn tất. Chỉ điều tra thêm nếu Terraform hết timeout hoặc OCI trả lỗi cụ thể.

Mỗi tầng compartment có thể mất khoảng 5–6 phút. Terraform phải xóa theo thứ tự `sensitive-data → development → OE root`, vì vậy không dừng tiến trình chỉ vì không thấy output mới ngoài dòng `Still destroying`.

Nếu Security Zone đã bị xóa nhưng compartment trở lại `ACTIVE`, kiểm tra target chuẩn mà OCI tự tạo sau khi xóa zone:

```bash
COMPARTMENT_ID="ocid1.compartment.oc1..REPLACE_ME"

oci cloud-guard target list \
  --compartment-id "$COMPARTMENT_ID" \
  --all \
  --query 'data.items[].{id:id,name:"display-name",state:"lifecycle-state"}' \
  --output table
```

Nếu target chỉ thuộc OE test và không còn cần thiết, xóa nó trước khi chạy lại `terraform destroy`:

```bash
TARGET_ID="ocid1.cloudguardtarget.oc1.ap-tokyo-1.REPLACE_ME"

oci cloud-guard target delete \
  --target-id "$TARGET_ID" \
  --force \
  --wait-for-state DELETED
```

Trong lần kiểm thử, OCI trả ETag cũ ngay sau khi Security Zone chuyển thành target chuẩn. Cập nhật tên target một lần để OCI phát sinh ETag mới, rồi xóa lại:

```bash
oci cloud-guard target update \
  --target-id "$TARGET_ID" \
  --display-name "Cloud Guard Target - pending cleanup" \
  --force \
  --wait-for-state ACTIVE

oci cloud-guard target delete \
  --target-id "$TARGET_ID" \
  --force \
  --wait-for-state DELETED
```

Chỉ thực hiện với target thuộc compartment OE test. Không xóa target cấp tenancy hoặc target đang bảo vệ OE01/Hub.
