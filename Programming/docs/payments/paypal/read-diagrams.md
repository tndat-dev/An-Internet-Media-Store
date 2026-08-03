# Cách Đọc Diagram Cho PayPal Payment Flow

## 1. Bản đồ đọc nhanh

Nếu bạn muốn hiểu nhanh toàn bộ use case, hãy đọc theo thứ tự sau:

1. Use case spec để biết actor, mục tiêu, tiền điều kiện và hậu điều kiện.
2. Activity diagram để thấy nhánh rẽ của luồng nghiệp vụ.
3. Sequence diagram để thấy thứ tự gọi giữa frontend, backend và PayPal.
4. Communication diagram để hiểu các đối tượng nào nói chuyện với nhau.
5. Analysis class diagram và detailed design class diagram để thấy cấu trúc lớp, DTO, service và gateway.

## 2. Mỗi diagram trả lời câu hỏi gì

### Use case spec

- Actor nào tham gia.
- Người dùng làm gì trước khi bắt đầu thanh toán.
- Luồng chính và các luồng lỗi.
- Điều kiện kết thúc thành công hoặc thất bại.

Đây là nơi bạn xác nhận nghĩa nghiệp vụ của "Pay Order by Credit Card". Trong dự án này, cụm từ "credit card" thực chất là card thanh toán qua PayPal checkout.

### Activity diagram

- Các bước nghiệp vụ diễn ra theo trình tự nào.
- Điểm quyết định: approve, cancel, error.
- Trạng thái của luồng thanh toán đi từ tạo payment sang capture và hoàn tất đơn hàng.

Hãy dùng diagram này để đọc logic quy trình trước khi đọc code.

### Sequence diagram

- Ai gọi ai, theo đúng thứ tự runtime.
- Request nào đi từ frontend sang backend.
- Khi nào PayPal JS SDK mở checkout.
- Khi nào backend gọi PayPal REST API.
- Khi nào order được chuyển sang `PENDING_PROCESSING`.

Đây là diagram quan trọng nhất nếu bạn muốn map từ màn hình sang code.

### Communication diagram

- Cùng một luồng như sequence diagram, nhưng nhấn mạnh quan hệ giữa đối tượng.
- Giúp bạn thấy ranh giới trách nhiệm: component, API module, view, service, gateway, entity.

### Class diagram

- Lớp nào là DTO, lớp nào là service, lớp nào là gateway, lớp nào là entity.
- Lớp nào chỉ giữ dữ liệu.
- Lớp nào chứa state transition.
- Lớp nào là điểm tích hợp với hệ thống ngoài.

Đây là diagram để hiểu cấu trúc tĩnh của code, không phải thứ tự chạy.

## 2.1 Mapping diagram sang code thật

- Use case spec -> mô tả nghiệp vụ ở mức yêu cầu; đối chiếu với `docs/project-full-context.md` và `docs/api/api-endpoints.md`.
- Activity diagram -> phù hợp nhất để hiểu nhánh approve / cancel / failure.
- Sequence diagram -> map trực tiếp sang `PayPalPaymentButton.tsx`, `paymentApi.ts`, `views.py`, `services.py`, `gateways/paypal.py`, `completion_service.py`.
- Communication diagram -> giúp nhìn boundary trách nhiệm giữa component, module, view, service, gateway và entity.
- Analysis class diagram / detailed design class diagram -> đối chiếu với `models.py`, `serializers.py`, `services.py`, `provider_registry.py` và `gateways/base.py`.

## 3. Cách đọc luồng PayPal trong diagram

### Bước 1: Chọn phương thức thanh toán

Người dùng vào Payment Method screen và chọn Card / PayPal. Đây là nhánh đi vào trang PayPal payment.

### Bước 2: Tạo PayPal order

Frontend gọi `initiatePayPalPayment(...)`. Backend tạo transaction ở trạng thái `PENDING` và trả `approval_url`.

Trong class diagram, bước này đi qua các nút sau:

- `PayPalPaymentButton`
- `paymentApi`
- `PayPalPaymentView`
- `PaymentService`
- `PayPalGateway`
- `PaymentTransaction`

### Bước 3: Người dùng approve trong PayPal checkout

PayPal JS SDK mở giao diện checkout. Tại đây người dùng nhập thông tin thẻ hoặc đăng nhập PayPal. Dữ liệu thẻ không đi vào AIMS.

Điểm cần ghi nhớ khi đọc sequence diagram là `PPSdk` thuộc PayPal, không thuộc AIMS. Nó chỉ là external participant.

### Bước 4: Capture payment

Sau khi approve, frontend gọi `capturePayPalPayment(...)`. Backend capture order trên PayPal REST API và nhận `capture_id`.

Ở detailed design class diagram, đây là đoạn nối từ `PayPalCaptureView` sang `PaymentService`, rồi sang `PayPalGateway.capture_payment(...)`.

### Bước 5: Hoàn tất đơn hàng

Backend cập nhật `PaymentTransaction` sang `SUCCESS`, rồi gọi seam hoàn tất order để chuyển đơn sang `PENDING_PROCESSING`.

Trong sequence diagram, mũi tên từ `Lifecycle -> Fulfill -> Order` là bước quan trọng nhất về nghiệp vụ hậu thanh toán.

### Bước 6: Hiển thị kết quả

Frontend điều hướng sang Order Result screen và đọc trạng thái giao dịch từ endpoint status.

Điểm này nối diagram với `CheckoutSuccessPage` và `PaymentResult` ở frontend.

## 4. Điểm cần chú ý khi đọc diagram

- `PaymentTransaction` là mốc dữ liệu trung tâm của toàn bộ flow.
- `PaymentService` chỉ orchestration, còn `PayPalGateway` mới chạm vào PayPal REST API.
- `PaymentProviderRegistry` là nơi chọn gateway theo capability.
- `PaymentCompletionService` là seam hoàn tất thanh toán và kích hoạt xử lý order.
- Nếu thấy tên "Card" trong UI, hãy hiểu đó là PayPal-hosted checkout, không phải form thẻ do AIMS tự xử lý.
- Sequence diagram và class diagram đều đang thể hiện một fact quan trọng: PayPal approval và PayPal capture là hai bước khác nhau, không nên gộp khi đọc runtime.
- `VietQRStatusView` xuất hiện trong box views ở sequence diagram chỉ là endpoint status dùng lại; nó không làm thay đổi bản chất của flow PayPal.

## 5. Cách tự kiểm tra rằng mình đã đọc đúng diagram

Bạn đọc đúng nếu trả lời được 5 câu này:

1. Ai là actor ngoài cùng của flow? Customer.
2. Frontend component nào mở PayPal checkout? `PayPalPaymentButton`.
3. Backend endpoint nào tạo PayPal order? `POST /api/payments/paypal/initiate/`.
4. Class nào chạm PayPal REST API? `PayPalGateway`.
5. Sau capture thành công, order đi sang trạng thái nào? `PENDING_PROCESSING`.

## 6. Tài liệu diagram nên mở cùng lúc

- `[Use case spec](../../../../RequirementAnalysis/UCSpec/pdf/PayOrderByCreditCard_updated.pdf)`
- `[Activity diagram](../../../../RequirementAnalysis/ActivityDiagram/images/PayOrderByCreditCard.png)`
- `[Sequence diagram](../../../../ArchitecturalDesign/SequenceDiagram/images/PayOrderByCreditCard.png)`
- `[Communication diagram](../../../../ArchitecturalDesign/CommunicationDiagram/images/PayOrderByCreditCard.png)`
- `[Analysis class diagram](../../../../ArchitecturalDesign/AnalysisClassDiagram/IndividualUC/PayOrderByCreditCard.png)`
- `[Detailed design class diagram source](../../../../PayOrderByCreditCard%20(1).puml)`
- `[Sequence diagram source](../../../../PayOrderByCreditCard.puml)`
