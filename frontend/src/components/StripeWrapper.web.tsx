/**
 * StripeWrapper — WEB no-op (Stripe RN SDK not supported on web).
 */
import React from "react";
export default function StripeWrapper({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
