// Rendered dynamically: the PayPal page uses useSearchParams() without a Suspense
// boundary, which cannot be statically prerendered (Next 16). force-dynamic skips SSG.
export const dynamic = "force-dynamic";

export { default } from "@/features/payment/paypal/page";
