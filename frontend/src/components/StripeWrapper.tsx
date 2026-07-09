/**
 * StripeWrapper — native provider. Passes children through with Stripe context.
 */
import React from "react";
import { StripeProvider } from "@stripe/stripe-react-native";

const STRIPE_PK = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY || "";

export default function StripeWrapper({ children }: { children: React.ReactNode }) {
  return (
    <StripeProvider
      publishableKey={STRIPE_PK}
      merchantIdentifier="merchant.com.auxora.app"
    >
      {children}
    </StripeProvider>
  );
}
