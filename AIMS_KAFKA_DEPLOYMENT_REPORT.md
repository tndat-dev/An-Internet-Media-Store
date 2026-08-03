# BÁO CÁO KAFKA KRAFT TRONG DỰ ÁN AIMS

**Phạm vi:** Kafka làm event backbone cho business event và security telemetry  
**Nền tảng:** Strimzi Kafka Operator, Kafka 4.3.0, KRaft  
**Namespace:** `production`  
**Ngày chốt:** 01/08/2026

Namespace `production` hiện Enforce PSA `restricted:latest`. Ba broker KRaft
vẫn Ready sau lần reconcile chart v0.3/CKS; TLS user, ACL, RF=3 và min ISR=2
không thay đổi. Kafka pod tiếp tục trải đúng ba worker.

## 1. Mục tiêu

Kafka được dùng làm event log chung cho hai miền:

- business event: order, payment, inventory, catalog và notification;
- security telemetry: Tetragon event, application audit và output mô hình
  LSTM/Isolation Forest.

Kafka không dùng làm task queue payment/notification. Task cần ack, retry và DLQ
được chuyển qua RabbitMQ; Kafka giữ event có retention và replay.

## 2. Lý thuyết Kafka

### 2.1 Event log

Kafka lưu record theo thứ tự append-only. Record không bị xóa ngay sau khi
consumer đọc; retention cho phép consumer mới hoặc job điều tra replay lịch sử.
Đây là khác biệt chính với queue truyền thống.

### 2.2 Topic, partition và offset

Topic là logical stream; partition là đơn vị song song và thứ tự. Kafka chỉ đảm
bảo thứ tự trong một partition. Producer chọn key để các event cùng aggregate,
ví dụ `order_id`, đi vào cùng partition. Consumer group chia partition giữa
consumer; offset ghi vị trí đã xử lý.

Sáu partition cho mỗi topic tạo tối đa sáu lane xử lý song song. Tăng partition
sau này được nhưng không giảm trực tiếp và có thể thay mapping key.

### 2.3 Replication, leader, follower và ISR

Mỗi partition có một leader và follower. Producer/consumer làm việc với leader;
follower replicate log. ISR là tập replica đang theo kịp. Với replication factor
3 và `min.insync.replicas=2`, producer dùng `acks=all` vẫn ghi khi một broker lỗi,
nhưng dừng ghi khi chỉ còn một ISR để tránh mất dữ liệu.

### 2.4 KRaft

KRaft thay ZooKeeper bằng Raft metadata quorum tích hợp. Controller quorum lưu
metadata topic, partition, ACL và broker registration. AIMS dùng 3 pod dual-role
`broker,controller`, phù hợp cụm nhỏ. Production lớn nên tách controller khỏi
broker để failure domain rõ hơn.

Ba controller chịu lỗi một controller. Không dùng hai controller vì quorum hai
không chịu được mất một node.

### 2.5 Delivery semantics

- at-most-once: commit offset trước xử lý, có thể mất event;
- at-least-once: xử lý rồi commit, có thể lặp event;
- exactly-once trong Kafka: dùng idempotent producer/transaction, nhưng không tự
  biến side effect ở PostgreSQL hoặc payment gateway thành exactly-once.

AIMS nên thiết kế at-least-once + idempotency key/outbox. Consumer lưu event ID
đã xử lý hoặc dùng unique constraint theo aggregate.

### 2.6 Retention và compaction

Business topic hiện giữ 7 ngày; security topic giữ 14 ngày. `delete` retention
phù hợp event history hữu hạn. Topic trạng thái mới nhất có thể dùng `compact`,
nhưng phải hiểu tombstone và khóa record.

### 2.7 Consumer group và rebalance

Các replica cùng service dùng một group prefix `aims-...`; mỗi partition chỉ
được gán cho một member trong group. Khi pod scale/restart, group rebalance.
Consumer cần graceful shutdown, cooperative assignor và thời gian xử lý phù hợp
`max.poll.interval.ms`.

## 3. Thiết kế Kafka cho AIMS

### 3.1 Cluster

| Thuộc tính | Giá trị |
|---|---|
| CR | `Kafka/aims-kafka` |
| Operator | Strimzi 1.1.0 |
| Kafka | 4.3.0 |
| Metadata | KRaft `4.3-IV0` |
| NodePool | `dual-role` |
| Replica | 3 |
| Vai trò | broker + controller |
| Storage | 10 GiB Longhorn/broker |
| Anti-affinity | hostname, một broker/worker |
| Default RF | 3 |
| min ISR | 2 |
| Authorization | simple ACL |

Phân bố cuối:

| Pod | Node |
|---|---|
| `aims-kafka-dual-role-0` | `k8s-worker4.local` |
| `aims-kafka-dual-role-1` | `k8s-worker3.local` |
| `aims-kafka-dual-role-2` | `k8s-worker1.local` |

### 3.2 Topic

| Topic | Partition | RF | min ISR | Retention | Mục đích |
|---|---:|---:|---:|---:|---|
| `aims-business-events` | 6 | 3 | 2 | 7 ngày | domain event |
| `aims-security-telemetry` | 6 | 3 | 2 | 14 ngày | audit/runtime/ML |

Security telemetry có retention dài hơn để điều tra và huấn luyện/baseline.
Nếu lưu lượng lớn, raw event nên tier sang MinIO/OpenSearch lifecycle thay vì
tăng vô hạn Kafka retention.

### 3.3 KafkaUser và ACL

`KafkaUser/aims-services` dùng TLS authentication và simple authorization:

- Read/Write/Describe topic prefix `aims-`;
- Read/Describe consumer group prefix `aims-`.

Một user chung giúp bootstrap nhanh nhưng production nên tạo user riêng cho từng
service theo least privilege: producer chỉ Write, consumer chỉ Read đúng topic.

### 3.4 Event envelope đề xuất

```json
{
  "event_id": "uuid",
  "event_type": "order.created.v1",
  "occurred_at": "2026-08-01T04:00:00Z",
  "producer": "order-service",
  "correlation_id": "uuid",
  "aggregate_id": "order-id",
  "schema_version": 1,
  "data": {}
}
```

Kafka key nên là `aggregate_id`. Không đưa password, token, PAN hoặc dữ liệu nhạy
cảm thô vào event. PII cần mask/encrypt và có retention policy.

## 4. Manifest thực tế

Nguồn chính: `Programming/k8s/platform/10-data-messaging.yaml`.

Các điểm quan trọng của NodePool:

```yaml
apiVersion: kafka.strimzi.io/v1
kind: KafkaNodePool
spec:
  replicas: 3
  roles: [controller, broker]
  storage:
    type: persistent-claim
    size: 10Gi
    class: longhorn
    deleteClaim: false
  template:
    pod:
      securityContext:
        runAsNonRoot: true
        seccompProfile: {type: RuntimeDefault}
    kafkaContainer:
      securityContext:
        allowPrivilegeEscalation: false
        capabilities: {drop: [ALL]}
        runAsNonRoot: true
```

Kafka config:

```yaml
config:
  offsets.topic.replication.factor: 3
  transaction.state.log.replication.factor: 3
  transaction.state.log.min.isr: 2
  default.replication.factor: 3
  min.insync.replicas: 2
```

## 5. Kết nối ứng dụng

Bootstrap service:

```text
aims-kafka-kafka-bootstrap.production.svc.cluster.local:9092
```

Chart hiện khai báo plain listener nội bộ 9092 và TLS listener 9093. Mục tiêu
production là chuyển application sang TLS 9093 với certificate từ KafkaUser,
mount secret qua ESO/Secret volume và bỏ plain listener sau migration.

Producer khuyến nghị:

```properties
acks=all
enable.idempotence=true
compression.type=zstd
delivery.timeout.ms=120000
```

Consumer khuyến nghị:

```properties
enable.auto.commit=false
isolation.level=read_committed
partition.assignment.strategy=CooperativeStickyAssignor
```

Chỉ commit offset sau khi side effect thành công. Với PostgreSQL, dùng
transactional outbox để tránh tình trạng DB commit nhưng Kafka publish thất bại.

## 6. Security

### 6.1 Network và mTLS

Namespace chạy Istio Ambient STRICT. NetworkPolicy Strimzi phải cho phép HBONE
15008 để ztunnel/waypoint đến broker. Cilium vẫn default-deny traffic không được
khai báo.

### 6.2 Authentication/authorization

- broker interconnect nằm trong cluster;
- application identity dùng KafkaUser certificate;
- ACL giới hạn topic/group;
- Secret không commit Git;
- certificate rotation do Strimzi quản lý.

### 6.3 Runtime

Broker chạy non-root UID 1001, seccomp RuntimeDefault, tắt privilege escalation
và drop ALL capabilities. Storage directory phải giữ UID/GID tương thích sau
volume move; nếu không broker không thể tạo `meta.properties`.

## 7. Vận hành

### 7.1 Kiểm tra health

```bash
kubectl -n production get kafka aims-kafka
kubectl -n production get kafkanodepool dual-role
kubectl -n production get pod -l strimzi.io/name=aims-kafka-kafka -o wide
kubectl -n production get kafkatopic,kafkauser
```

Tiêu chí:

- Kafka `Ready=True`;
- 3/3 broker Ready trên ba worker khác nhau;
- topic và user Ready;
- không có under-replicated partition.

### 7.2 Xem metadata/topic

```bash
kubectl -n production exec aims-kafka-dual-role-0 -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe

kubectl -n production exec aims-kafka-dual-role-0 -- \
  bin/kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --status
```

### 7.3 Produce/consume smoke test

Dùng test topic hoặc key không ảnh hưởng nghiệp vụ:

```bash
kubectl -n production exec -it aims-kafka-dual-role-0 -- \
  bin/kafka-console-producer.sh \
  --bootstrap-server aims-kafka-kafka-bootstrap:9092 \
  --topic aims-business-events

kubectl -n production exec -it aims-kafka-dual-role-1 -- \
  bin/kafka-console-consumer.sh \
  --bootstrap-server aims-kafka-kafka-bootstrap:9092 \
  --topic aims-business-events --from-beginning --max-messages 1
```

Trong production, dùng KafkaUser TLS config thay vì localhost/plain.

### 7.4 Kết quả kiểm chứng TLS/ACL/KRaft ngày 01/08/2026

Listener TLS 9093 đã bật `authentication.type: tls`. Script
`Programming/k8s/scripts/kafka-tls-smoke.sh` mount CA cluster và certificate của
`KafkaUser/aims-services`, sau đó list topic, produce và consume bằng đúng
application identity. Kết quả:

```text
PASS Kafka TLS produce/consume: aims-smoke-20260801T051939Z
```

Sau đợt hardening/Gateway/audit và cân bằng tài nguyên, smoke test được chạy lại
để loại trừ regression:

```text
PASS Kafka TLS produce/consume: aims-smoke-20260801T092018Z
```

Admin check độc lập xác nhận:

- `aims-business-events`: 6 partition, RF=3;
- `aims-security-telemetry`: 6 partition, RF=3;
- mọi partition có ISR `0,1,2`, không có under-replicated partition;
- KRaft leader broker/controller 0, leader epoch 10;
- high watermark 485834, follower lag tối đa 0;
- voters là 0/1/2, đủ quorum ba thành viên.

Hai topic đã được tạo lại sau sự cố metadata với topic ID mới; đây là lý do
không dùng topic ID làm business identity. Topic name/schema/event ID mới là
contract ổn định của ứng dụng.

### 7.5 Lag và alert

Metric cần alert:

- under-replicated/offline partitions > 0;
- active controller != 1;
- ISR shrink tăng;
- consumer lag tăng liên tục;
- request latency/error rate;
- filesystem > 80%;
- controller/broker pod restart.

Consumer lag phản ánh độ trễ xử lý, không chỉ broker health. Security pipeline có
thể chấp nhận lag khác payment/order, nên alert threshold theo service.

## 8. Sự cố thực tế và phục hồi

### 8.1 Triệu chứng

`aims-kafka-dual-role-2` CrashLoopBackOff. Log:

```text
Error while writing meta.properties file ...
java.nio.file.AccessDeniedException: /var/lib/kafka/data/kafka-log2
```

### 8.2 Nguyên nhân

Sau khi topology node/PVC thay đổi, thư mục broker volume không còn ownership
phù hợp UID 1001. SecurityContext mới non-root hoạt động đúng và từ chối ghi;
đây không phải lỗi KRaft quorum hay Cilium.

### 8.3 Quy trình xử lý

1. xác nhận hai broker còn lại giữ quorum;
2. tạo snapshot Longhorn `pre-permission-fix-kafka-20260801`;
3. tạm pause reconciliation và dừng Strimzi operator trong maintenance ngắn;
4. recreate broker trên worker hợp lệ với volume/ownership đúng;
5. bật lại operator, bỏ pause annotation;
6. xác nhận broker 3 Ready, Kafka `Ready=True`;
7. xác nhận phân bố một broker trên mỗi worker.

Không xóa PVC và không format toàn cluster. `deleteClaim: false` bảo vệ volume khi
NodePool bị thay đổi.

## 9. Backup và DR cho Kafka

Velero backup Kubernetes metadata/PVC file-level không thay thế Kafka-native DR.
Các lựa chọn production:

- MirrorMaker 2 sang cluster Kafka thứ hai;
- replicate event quan trọng sang object storage;
- GitOps lưu Topic/User/ACL CR;
- kiểm thử restore consumer offset và schema registry;
- định nghĩa RPO/RTO riêng business và security.

Snapshot block trong lúc broker đang ghi có thể crash-consistent nhưng không chắc
application-consistent. Khi restore một broker, KRaft/replica log phải reconcile;
không restore ba broker từ ba thời điểm khác nhau mà không có runbook.

## 10. Capacity planning

Ước lượng dung lượng tối thiểu:

```text
storage ≈ ingest_bytes_per_second × retention_seconds × replication_factor
          × overhead_factor
```

Ví dụ 1 MiB/s, 7 ngày, RF=3 đã xấp xỉ 1,8 TiB trước overhead. Vì vậy PVC 10 GiB
chỉ phù hợp demo/lab; cần đo ingest thực, compression ratio và tăng volume trước
khi chạy load thật.

Partition count quyết định throughput/parallelism nhưng tăng quá mức làm tăng
metadata, file handle, recovery time và controller load.

## 11. Việc cần hoàn thiện

1. chuyển cả chín application workload sang listener TLS 9093 (smoke test TLS
   đã pass) rồi bỏ plain listener;
2. tạo KafkaUser riêng cho từng microservice;
3. triển khai schema registry và compatibility policy;
4. transactional outbox cho order/payment/inventory;
5. exporter/dashboard consumer lag;
6. MirrorMaker 2/off-cluster DR;
7. tăng PVC theo đo đạc, không dùng 10 GiB cho production thật;
8. cân nhắc tách 3 controller và 3+ broker khi tải tăng.

## 12. Kết luận

Kafka KRaft đã được triển khai bằng Strimzi, không cần ZooKeeper, có ba quorum
member, RF=3, min ISR=2, ACL và hardening runtime. Cụm đã trải qua một lỗi thực
tế do quyền volume và được phục hồi an toàn sau snapshot mà không xóa dữ liệu.
Thiết kế đáp ứng mục tiêu event backbone của AIMS ở mức production-like; bước
quan trọng tiếp theo là TLS-only, per-service identity, schema governance,
outbox và DR sang Kafka cluster độc lập.
