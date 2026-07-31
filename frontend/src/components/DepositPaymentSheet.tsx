/**
 * Deposit Payment Sheet — Apple Pay + Card via Stripe.
 * Falls back to a beautiful mock UI when Stripe is in mock mode
 * (STRIPE_API_KEY = sk_test_emergent).
 */
import React, { useEffect, useRef, useState } from "react";
import { View, StyleSheet, Pressable, Alert, ActivityIndicator, Platform, Modal } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import Animated, { FadeIn, FadeInUp } from "react-native-reanimated";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";

const COLORS = {
  bg: "#0B0B0B",
  bgSoft: "#141416",
  white: "#FFFFFF",
  accent: "#C8A96B",
  secondary: "#B8B8B8",
  muted: "#6E6E73",
  border: "#1F1F22",
  success: "#34D399",
};

// Try to load Stripe SDK — will fail gracefully on web
let stripeSdk: any = null;
try {
  stripeSdk = require("@stripe/stripe-react-native");
} catch { /* not available on web */ }

type Props = {
  interventionId: string;
  onSuccess: () => void;
  onCancel: () => void;
  artisanName?: string;
  visible: boolean;
  finalPayment?: boolean;
};

export default function DepositPaymentSheet({ interventionId, onSuccess, onCancel, artisanName, visible, finalPayment }: Props) {
  const [amount, setAmount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [method, setMethod] = useState<"apple_pay" | "card" | null>(null);
  const clientSecretRef = useRef<string | null>(null);
  const piIdRef = useRef<string | null>(null);
  const isMockRef = useRef<boolean>(false);

  // Init intent when modal opens
  useEffect(() => {
    if (!visible) return;
    setLoading(true);
    (async () => {
      try {
        const endpoint = finalPayment
          ? `/interventions/${interventionId}/final/create`
          : `/interventions/${interventionId}/deposit/create`;
        const r = await api<{ client_secret: string; payment_intent_id: string; amount_cents: number; mock: boolean }>(
          endpoint,
          { method: "POST", body: {} }
        );
        clientSecretRef.current = r.client_secret;
        piIdRef.current = r.payment_intent_id;
        isMockRef.current = !!r.mock;
        setAmount(r.amount_cents);
      } catch (e: any) {
        Alert.alert("Erreur", e?.message || "Impossible d'initialiser le paiement.");
        onCancel();
      } finally {
        setLoading(false);
      }
    })();
  }, [visible, interventionId, finalPayment]);

  const confirmMock = async () => {
    // Mock flow: simulate 1.5s processing, then hit confirm endpoint
    setProcessing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {});
    await new Promise((r) => setTimeout(r, 1400));
    try {
      const endpoint = finalPayment
        ? `/interventions/${interventionId}/final/confirm`
        : `/interventions/${interventionId}/deposit/confirm`;
      await api(endpoint, { method: "POST", body: { payment_intent_id: piIdRef.current } });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      onSuccess();
    } catch (e: any) {
      Alert.alert("Erreur", e?.message);
    } finally {
      setProcessing(false);
    }
  };

  const confirmStripe = async (chosenMethod: "apple_pay" | "card") => {
    if (!stripeSdk || Platform.OS === "web") return confirmMock();
    setMethod(chosenMethod);
    setProcessing(true);
    try {
      const { initPaymentSheet, presentPaymentSheet } = stripeSdk;
      const initRes = await initPaymentSheet({
        merchantDisplayName: "Faqtotum",
        paymentIntentClientSecret: clientSecretRef.current!,
        applePay: chosenMethod === "apple_pay" ? { merchantCountryCode: "FR" } : undefined,
        style: "alwaysDark",
        appearance: { colors: { primary: COLORS.accent, background: COLORS.bg, componentBackground: COLORS.bgSoft } },
        allowsDelayedPaymentMethods: false,
        returnURL: "faqtotum://stripe-redirect",
        defaultBillingDetails: { name: "" },
      });
      if (initRes?.error) throw new Error(initRes.error.message);
      const presentRes = await presentPaymentSheet();
      if (presentRes?.error) {
        if (presentRes.error.code === "Canceled") { setProcessing(false); return; }
        throw new Error(presentRes.error.message);
      }
      // Success
      const endpoint = finalPayment
        ? `/interventions/${interventionId}/final/confirm`
        : `/interventions/${interventionId}/deposit/confirm`;
      await api(endpoint, { method: "POST", body: { payment_intent_id: piIdRef.current } });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      onSuccess();
    } catch (e: any) {
      Alert.alert("Erreur de paiement", e?.message || "Impossible de finaliser le paiement.");
    } finally {
      setProcessing(false);
    }
  };

  const doPay = (m: "apple_pay" | "card") => {
    if (isMockRef.current) return confirmMock();
    return confirmStripe(m);
  };

  const amountEur = amount ? (amount / 100).toFixed(2) : "—";

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onCancel}>
      <View style={styles.backdrop}>
        <Animated.View entering={FadeInUp.duration(320)} style={styles.sheet}>
          <View style={styles.handleBar} />

          <View style={styles.headerRow}>
            <View style={styles.iconWrap}>
              <Ionicons name="shield-checkmark" size={22} color={COLORS.accent} />
            </View>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Txt weight="extrabold" size="lg" style={{ color: COLORS.white }}>Confirmer l&apos;intervention</Txt>
              <Txt size="sm" style={{ color: COLORS.muted, marginTop: 2 }}>
                Petit acompte pour sécuriser la prise en charge
              </Txt>
            </View>
            <Pressable onPress={onCancel} hitSlop={12} style={styles.close}>
              <Ionicons name="close" size={18} color={COLORS.white} />
            </Pressable>
          </View>

          {loading ? (
            <ActivityIndicator color={COLORS.accent} style={{ marginVertical: 30 }} />
          ) : (
            <>
              <Animated.View entering={FadeIn.delay(100)} style={styles.amountCard}>
                <Txt size="sm" style={{ color: COLORS.muted, textAlign: "center" }}>Montant de l&apos;acompte</Txt>
                <Txt weight="extrabold" style={styles.amount}>{amountEur} €</Txt>
                <Txt size="sm" style={{ color: COLORS.muted, textAlign: "center", marginTop: 4 }}>
                  Déduit de la facture finale
                </Txt>
              </Animated.View>

              {artisanName && (
                <View style={styles.line}>
                  <Ionicons name="person" size={14} color={COLORS.muted} />
                  <Txt size="sm" style={{ color: COLORS.secondary, marginLeft: 6 }}>{artisanName}</Txt>
                </View>
              )}

              <View style={{ paddingHorizontal: 20, marginTop: 20, gap: 10 }}>
                {Platform.OS === "ios" && (
                  <PayButton
                    onPress={() => doPay("apple_pay")}
                    disabled={processing}
                    loading={processing && method === "apple_pay"}
                    style={styles.applePay}
                    textColor={COLORS.white}
                  >
                    <Ionicons name="logo-apple" size={18} color={COLORS.white} />
                    <Txt weight="bold" style={{ color: COLORS.white, marginLeft: 6 }}>Pay</Txt>
                  </PayButton>
                )}

                <PayButton
                  onPress={() => doPay("card")}
                  disabled={processing}
                  loading={processing && (method === "card" || isMockRef.current)}
                  style={styles.card}
                  textColor={COLORS.bg}
                >
                  <Ionicons name="card" size={18} color={COLORS.bg} />
                  <Txt weight="bold" style={{ color: COLORS.bg, marginLeft: 8 }}>
                    {isMockRef.current ? `Payer ${amountEur} €` : `Payer avec carte  ${amountEur} €`}
                  </Txt>
                </PayButton>

                {isMockRef.current && (
                  <View style={styles.mockNotice}>
                    <Ionicons name="information-circle-outline" size={14} color={COLORS.muted} />
                    <Txt size="sm" style={{ color: COLORS.muted, marginLeft: 6, flex: 1 }}>
                      Mode démo — Apple Pay & carte réelle s&apos;activent après connexion de vos vraies clés Stripe.
                    </Txt>
                  </View>
                )}

                <View style={styles.legalRow}>
                  <Ionicons name="lock-closed" size={12} color={COLORS.muted} />
                  <Txt size="sm" style={{ color: COLORS.muted, marginLeft: 6, flex: 1, lineHeight: 16 }}>
                    Paiement sécurisé Stripe. Remboursement automatique si annulation par l&apos;artisan.
                  </Txt>
                </View>
              </View>
            </>
          )}
        </Animated.View>
      </View>
    </Modal>
  );
}

function PayButton({ children, onPress, disabled, loading, style, textColor }: any) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        style,
        disabled && { opacity: 0.5 },
        pressed && { transform: [{ scale: 0.98 }] },
      ]}
    >
      {loading ? <ActivityIndicator color={textColor} /> : <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "center" }}>{children}</View>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.65)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: COLORS.bg,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingTop: 8,
    paddingBottom: 32,
    borderTopWidth: 1,
    borderColor: COLORS.border,
  },
  handleBar: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: COLORS.border,
    alignSelf: "center",
    marginBottom: 16,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 20,
  },
  iconWrap: {
    width: 40, height: 40, borderRadius: 12,
    backgroundColor: "rgba(200,169,107,0.15)",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: "rgba(200,169,107,0.3)",
  },
  close: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: COLORS.bgSoft,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: COLORS.border,
  },
  amountCard: {
    marginTop: 20,
    marginHorizontal: 20,
    padding: 20,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 20,
    borderWidth: 1, borderColor: COLORS.border,
    alignItems: "center",
  },
  amount: {
    color: COLORS.white,
    fontSize: 44,
    marginTop: 6,
    letterSpacing: -1,
  },
  line: {
    marginTop: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },
  applePay: {
    backgroundColor: "#000",
    borderWidth: 1,
    borderColor: "#333",
    borderRadius: 14,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },
  card: {
    backgroundColor: COLORS.accent,
    borderRadius: 14,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 4,
  },
  mockNotice: {
    flexDirection: "row",
    alignItems: "flex-start",
    padding: 10,
    backgroundColor: "rgba(200,169,107,0.06)",
    borderRadius: 10,
    borderWidth: 1, borderColor: "rgba(200,169,107,0.15)",
    marginTop: 4,
  },
  legalRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 10,
  },
});
