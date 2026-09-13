import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const baseUrl = (__ENV.AIMS_BASE_URL || "http://10.1.16.234:31088").replace(/\/$/, "");
const runId = __ENV.RUN_ID || `${Date.now()}`;
const checkoutEnabled = (__ENV.ENABLE_CHECKOUT || "false").toLowerCase() === "true";

const businessFailures = new Rate("aims_business_failures");
const checkoutDuration = new Trend("aims_checkout_duration", true);

const scenarios = {
  browse: {
    executor: "ramping-vus",
    exec: "browse",
    startVUs: 0,
    stages: [
      { duration: __ENV.RAMP_UP || "10s", target: Number(__ENV.VUS || 10) },
      { duration: __ENV.HOLD || "30s", target: Number(__ENV.VUS || 10) },
      { duration: __ENV.RAMP_DOWN || "10s", target: 0 },
    ],
    gracefulRampDown: "10s",
  },
};

if (checkoutEnabled) {
  scenarios.checkout = {
    executor: "per-vu-iterations",
    exec: "checkout",
    vus: Number(__ENV.CHECKOUT_VUS || 1),
    iterations: Number(__ENV.CHECKOUT_ITERATIONS || 1),
    maxDuration: "2m",
    startTime: "5s",
  };
}

export const options = {
  scenarios,
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1500", "p(99)<2500"],
    aims_business_failures: ["rate<0.01"],
    aims_checkout_duration: ["p(95)<10000"],
  },
};

function jsonHeaders(extra = {}) {
  return { headers: { "Content-Type": "application/json", ...extra } };
}

function expect(response, expected, label) {
  const passed = check(response, { [`${label}: HTTP ${expected}`]: (r) => r.status === expected });
  businessFailures.add(!passed, { step: label });
  return passed;
}

export function browse() {
  group("browse catalog and search", () => {
    const products = http.get(`${baseUrl}/api/products/?page_size=20`, { tags: { name: "GET /api/products/" } });
    expect(products, 200, "catalog list");

    const search = http.get(`${baseUrl}/api/search/?q=book&limit=10`, { tags: { name: "GET /api/search/" } });
    expect(search, 200, "search");

    const token = `k6-read-${runId}-${__VU}-${__ITER}`;
    const cart = http.get(`${baseUrl}/api/cart/`, {
      headers: { "X-Cart-Token": token },
      tags: { name: "GET /api/cart/ empty" },
    });
    expect(cart, 200, "empty cart read");
  });
  sleep(Math.random() * 1.5 + 0.5);
}

export function checkout() {
  const started = Date.now();
  const token = `k6-checkout-${runId}-${__VU}-${__ITER}`;

  group("checkout and asynchronous event chain", () => {
    const catalog = http.get(`${baseUrl}/api/products/?page_size=20`, { tags: { name: "GET /api/products/ checkout" } });
    if (!expect(catalog, 200, "checkout catalog")) return;
    const products = catalog.json("results") || [];
    const product = products.find((item) => item.status === "ACTIVE") || products[0];
    if (!product) {
      businessFailures.add(true, { step: "select product" });
      return;
    }
    const productId = product.product_id || product.productId || product.id;

    const stock = http.get(`${baseUrl}/api/inventory/${productId}`, { tags: { name: "GET /api/inventory/:id" } });
    if (stock.status === 404 || Number(stock.json("available") || 0) < 1) {
      const adjusted = http.post(
        `${baseUrl}/api/inventory/${productId}/adjust`,
        JSON.stringify({ delta: 1 }),
        { ...jsonHeaders(), tags: { name: "POST /api/inventory/:id/adjust" } },
      );
      expect(adjusted, 200, "inventory seed");
    } else {
      expect(stock, 200, "inventory read");
    }

    const cartHeaders = { "X-Cart-Token": token };
    const added = http.post(
      `${baseUrl}/api/cart/items/`,
      JSON.stringify({ productId, quantity: 1 }),
      { ...jsonHeaders(cartHeaders), tags: { name: "POST /api/cart/items/" } },
    );
    if (!expect(added, 200, "cart add")) return;
    const itemId = added.json("items.0.cartItemId");

    const draft = http.post(`${baseUrl}/api/orders/draft/`, null, {
      headers: cartHeaders,
      tags: { name: "POST /api/orders/draft/" },
    });
    if (!expect(draft, 201, "order draft")) return;
    const orderId = draft.json("orderId");
    const cancelToken = draft.json("cancelToken");
    const amount = draft.json("totalAmount");

    const delivery = http.post(
      `${baseUrl}/api/orders/${orderId}/delivery/`,
      JSON.stringify({
        customerName: "AIMS Load Test",
        phoneNumber: "0900000000",
        email: "load-test@aims.invalid",
        deliveryProvince: "Ha Noi",
        deliveryAddress: `k6-${runId}`,
        deliveryMethod: "STANDARD",
        deliveryInstructions: "synthetic production simulation",
      }),
      { ...jsonHeaders(), tags: { name: "POST /api/orders/:id/delivery/" } },
    );
    expect(delivery, 200, "order delivery");

    const confirmed = http.post(
      `${baseUrl}/api/orders/`,
      JSON.stringify({ orderId }),
      { ...jsonHeaders(), tags: { name: "POST /api/orders/ confirm" } },
    );
    expect(confirmed, 200, "order confirm and Kafka outbox");

    sleep(3);
    const payment = http.post(
      `${baseUrl}/api/payments/complete/`,
      JSON.stringify({ orderId, amount, currency: "VND", provider: "K6-SIMULATION" }),
      { ...jsonHeaders(), tags: { name: "POST /api/payments/complete/" } },
    );
    expect(payment, 202, "payment complete and notification event");

    sleep(3);
    const notification = http.get(`${baseUrl}/api/notifications/healthz`, {
      tags: { name: "GET /api/notifications/healthz" },
    });
    const notificationHealthy = expect(notification, 200, "notification health");
    if (notificationHealthy) {
      const brokersReady = notification.json("kafkaReady") === true && notification.json("rabbitReady") === true;
      check(notification, { "notification Kafka and RabbitMQ consumers are ready": () => brokersReady });
      businessFailures.add(!brokersReady, { step: "notification broker readiness" });
    }

    if (itemId) {
      http.del(`${baseUrl}/api/cart/items/${itemId}/`, null, {
        headers: cartHeaders,
        tags: { name: "DELETE /api/cart/items/:id/" },
      });
    }
    if (cancelToken) {
      http.post(`${baseUrl}/api/orders/${cancelToken}/cancel/`, null, {
        tags: { name: "POST /api/orders/:token/cancel/" },
      });
    }
  });

  checkoutDuration.add(Date.now() - started);
}
