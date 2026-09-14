# Sơ đồ AIMS theo Oracle Multi-OE Generic v1

Ngày cập nhật: **14/09/2026**. Đây là kiến trúc đích của lab; không phải xác nhận tài nguyên đã được triển khai trên OCI.

Mở [bản draw.io có thể chỉnh sửa](OCI_AIMS_GENERIC_V1.drawio) hoặc [PDF bốn trang](OCI_AIMS_GENERIC_V1.pdf). File gốc người dùng cung cấp được giữ nguyên tại `/home/tndat/Downloads/OCI_Open_LZ_Multi-OE-Blueprint.drawio`.

## Nguồn và cách dựng

Bản vẽ sử dụng trực tiếp các lớp và hình từ file Oracle có **25 trang**, theo [tài liệu thiết kế Multi-OE Generic v1](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/blob/master/blueprints/multi-oe/generic_v1/design/readme.md). File local trùng SHA-256 với [file draw.io chính thức](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/blob/master/blueprints/multi-oe/generic_v1/design/OCI_Open_LZ_Multi-OE-Blueprint.drawio) đã tải để đối chiếu:

```text
c84121b156d0fba826f48cdca2edd97a743bc5f8c2657ac1f7b6d43753d75353
```

| Trang trong bản AIMS | Nội dung và nguồn |
|---|---|
| 01 — SEC · Tenancy L0–L2 | Chỉnh từ trang `SEC - Tenancy Structure` của Oracle; giữ bố cục shared security/network bên trái, các OE và môi trường bên phải. |
| 02 — NET · Generic v1 structure | Chỉnh từ trang `NET (1) - Structure`; giữ quan hệ OE common-network quản lý các VCN môi trường và phân vai central team/OE team. |
| 03 — NET · AIMS Hub B detail | Vẽ phần lab chi tiết bằng màu phân tầng của Oracle và các OCI stencil chỉnh sửa được; thể hiện Hub B, production VCN, CIDR và phạm vi sở hữu tài nguyên. |
| 04 — APP · AIMS microservices | Giữ nội dung trang ứng dụng trong `OCI_AIMS_ARCHITECTURE.drawio`, gồm OKE ba worker, Kafka, PostgreSQL và CI/CD. Đây là thiết kế ứng dụng của lab, không phải nội dung Oracle Generic v1. |

## Ánh xạ blueprint vào lab

| Thành phần trong mẫu | Áp dụng cho AIMS |
|---|---|
| Nhiều OE trong một tenancy | Triển khai OE01 trước. OE02, OE03 và các OE tiếp theo được đánh dấu `FUTURE OE`. |
| `cmp-oe01` | Tên compartment gốc OE trong runbook là `cmp-oe1`; tên các compartment con giữ tiền tố `cmp-oe01-`. |
| Shared network và security | `cmp-network` chứa mạng Hub; `cmp-security` quản lý các dịch vụ bảo mật chung. Bucket backup thuộc compartment con `cmp-backup`, Vault key thuộc `cmp-security`. |
| OE common-network | `cmp-oe01-common-network` sở hữu production VCN/subnet/SGW/NSG. |
| Production workload | `cmp-oe01-prod` sở hữu OKE, node pool, compute, volumes và Private LB sử dụng subnet của OE common-network. |
| VCN theo từng môi trường | Lab tạo `oe01-vcn` — `10.1.0.0/16` cho production. Các VCN common/dev/nonprod/sandbox trong trang 02 là phần dự kiến. |
| Hub tổng quát trong hình Oracle | Lab dùng **Hub B**, một OCI Network Firewall trong Hub `10.0.0.0/16`; xem [tài liệu Hub models](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/tree/master/addons/oci-hub-models) và quyết định triển khai trong runbook. |
| SGW ở các VCN trong mẫu | Baseline dùng SGW của production VCN cho Oracle Services Network. Hub SGW ở trang 02 được đánh dấu future. |
| On-premises, cloud khác | Chỉ giữ làm bối cảnh mở rộng của blueprint; chưa nằm trong phạm vi lab. |

Các nhãn L0/L1/L2 giữ theo **cấp logic trong hình Oracle**, không phải độ sâu thực tế sau khi thêm `mb-home-cmp` và `tndat-lz-cmp`. Cây compartment dùng khi triển khai nằm tại mục 3 của [runbook thủ công](OCI_AIMS_MANUAL_RUNBOOK.md). Không tạo thêm compartment từ namespace Kubernetes hoặc các khối nhóm trên sơ đồ.

## Cách đọc kết nối và bảo mật

- Web: Internet → IGW → Public LB gắn Regional WAF → Network Firewall → DRG → Private LB → Traefik → AIMS. Đây là lựa chọn Hub B của lab.
- Traffic backend trả về phải qua firewall; Internet egress của Spoke đi DRG → firewall → NAT. Bảng route hai chiều chi tiết nằm ở mục 8 runbook và trang routing trong [sơ đồ ba trang trước](OCI_AIMS_ARCHITECTURE.drawio).
- Oracle Services Network đi trực tiếp qua Spoke SGW, là ngoại lệ đối với kiểm tra qua Hub firewall. SGW không phục vụ Internet nói chung.
- Đường nét đứt xám nối worker subnet với khối OKE mô tả tài nguyên sử dụng subnet; không phải packet flow.
- Cloud Guard giám sát theo target; WAF gắn với Public LB. Security Zone `sz-oe01-private` áp dụng tại `cmp-oe1`, `sz-backup` tại `cmp-backup`; recipe cụ thể nằm ở mục 6.3 runbook. Hub chứa Public LB nằm ngoài zone private của OE.
- Trang ứng dụng mô tả kiến trúc đích; việc tách microservice và trạng thái sẵn sàng của từng service không được đánh giá trong lần cập nhật sơ đồ này.

## Ghi nhận bản quyền

Các phần dẫn xuất từ blueprint Oracle:

Copyright (c) 2018, 2026 Oracle and/or its affiliates. All rights reserved.

Licensed under **The Universal Permissive License (UPL), Version 1.0**. Xem [LICENSE.txt của dự án Oracle](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities/blob/master/LICENSE.txt).
