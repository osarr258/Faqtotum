/**
 * DepositPaymentSheet — WEB fallback (no Stripe RN SDK on web).
 * Uses the mock flow directly via backend confirm endpoint.
 */
import React, { useEffect, useRef, useState } from "react";
import { View, StyleSheet, Pressable, Alert, ActivityIndicator, Modal } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeIn, FadeInUp } from "react-native-reanimated";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";

const COLORS = {
  bg: "#0B0B0B", bgSoft: "#141416", white: "#FFFFFF", accent: "#C8A96B",
  secondary: "#B8B8B8", muted: "#6E6E73", border: "#1F1F22",
};

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
  const piIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setLoading(true);
    (async () => {
      try {
        const endpoint = finalPayment
          ? `/interventions/${interventionId}/final/create`
          : `/interventions/${interventionId}/deposit/create`;
        const r = await api<{ payment_intent_id: string; amount_cents: number }>(
          endpoint,
          { method: "POST", body: {} }
        );
        piIdRef.current = r.payment_intent_id;
        setAmount(r.amount_cents);
      } catch (e: any) {
        Alert.alert("Erreur", e?.message || "Impossible d'initialiser le paiement.");
        onCancel();
      } finally {
        setLoading(false);
      }
    })();
  }, [visible, interventionId, finalPayment]);

  const confirmPayment = async () => {
    setProcessing(true);
    await new Promise((r) => setTimeout(r, 1400));
    try {
      const endpoint = finalPayment
        ? `/interventions/${interventionId}/final/confirm`
        : `/interventions/${interventionId}/deposit/confirm`;
      await api(endpoint, { method: "POST", body: { payment_intent_id: piIdRef.current } });
      onSuccess();
    } catch (e: any) {
      Alert.alert("Erreur", e?.message);
    } finally { setProcessing(false); }
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
              <Txt weight="extrabold" size="lg" style={{ color: COLORS.white }}>
                {finalPayment ? "Payer le solde" : "Confirmer l'intervention"}
              </Txt>
              <Txt size="sm" style={{ color: COLORS.muted, marginTop: 2 }}>
                {finalPayment ? "Régler le solde final de l'intervention" : "Petit acompte pour sécuriser la prise en charge"}
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
                <Txt size="sm" style={{ color: COLORS.muted, textAlign: "center" }}>
                  {finalPayment ? "Montant du solde" : "Montant de l'acompte"}
                </Txt>
                <Txt weight="extrabold" style={styles.amount}>{amountEur} €</Txt>
                <Txt size="sm" style={{ color: COLORS.muted, textAlign: "center", marginTop: 4 }}>
                  {finalPayment ? "Libère le paiement vers l'artisan après validation" : "Déduit de la facture finale"}
                </Txt>
              </Animated.View>

              {artisanName && (
                <View style={styles.line}>
                  <Ionicons name="person" size={14} color={COLORS.muted} />
                  <Txt size="sm" style={{ color: COLORS.secondary, marginLeft: 6 }}>{artisanName}</Txt>
                </View>
              )}

              <View style={{ paddingHorizontal: 20, marginTop: 20, gap: 10 }}>
                <Pressable
                  testID="pay-apple"
                  onPress={confirmPayment}
                  disabled={processing}
                  style={({ pressed }) => [styles.applePay, (processing || pressed) && { opacity: 0.85 }]}
                >
                  {processing ? <ActivityIndicator color={COLORS.white} /> : (
                    <View style={{ flexDirection: "row", alignItems: "center" }}>
                      <Ionicons name="logo-apple" size={18} color={COLORS.white} />
                      <Txt weight="bold" style={{ color: COLORS.white, marginLeft: 6 }}>Pay</Txt>
                    </View>
                  )}
                </Pressable>

                <Pressable
                  testID="pay-card"
                  onPress={confirmPayment}
                  disabled={processing}
                  style={({ pressed }) => [styles.card, (processing || pressed) && { opacity: 0.85 }]}
                >
                  {processing ? <ActivityIndicator color={COLORS.bg} /> : (
                    <View style={{ flexDirection: "row", alignItems: "center" }}>
                      <Ionicons name="card" size={18} color={COLORS.bg} />
                      <Txt weight="bold" style={{ color: COLORS.bg, marginLeft: 8 }}>Payer par carte  {amountEur} €</Txt>
                    </View>
                  )}
                </Pressable>

                <View style={styles.mockNotice}>
                  <Ionicons name="information-circle-outline" size={14} color={COLORS.muted} />
                  <Txt size="sm" style={{ color: COLORS.muted, marginLeft: 6, flex: 1 }}>
                    Aperçu web — Apple Pay & Stripe réels s&apos;activent uniquement sur build iOS/Android.
                  </Txt>
                </View>

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

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.65)", justifyContent: "flex-end" },
  sheet: { backgroundColor: COLORS.bg, borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingTop: 8, paddingBottom: 32, borderTopWidth: 1, borderColor: COLORS.border },
  handleBar: { width: 40, height: 4, borderRadius: 2, backgroundColor: COLORS.border, alignSelf: "center", marginBottom: 16 },
  headerRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 20 },
  iconWrap: { width: 40, height: 40, borderRadius: 12, backgroundColor: "rgba(200,169,107,0.15)", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "rgba(200,169,107,0.3)" },
  close: { width: 32, height: 32, borderRadius: 16, backgroundColor: COLORS.bgSoft, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: COLORS.border },
  amountCard: { marginTop: 20, marginHorizontal: 20, padding: 20, backgroundColor: COLORS.bgSoft, borderRadius: 20, borderWidth: 1, borderColor: COLORS.border, alignItems: "center" },
  amount: { color: COLORS.white, fontSize: 44, marginTop: 6, letterSpacing: -1 },
  line: { marginTop: 12, flexDirection: "row", alignItems: "center", justifyContent: "center" },
  applePay: { backgroundColor: "#000", borderWidth: 1, borderColor: "#333", borderRadius: 14, paddingVertical: 16, alignItems: "center", justifyContent: "center" },
  card: { backgroundColor: COLORS.accent, borderRadius: 14, paddingVertical: 16, alignItems: "center", justifyContent: "center", shadowColor: COLORS.accent, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.3, shadowRadius: 12, elevation: 4 },
  mockNotice: { flexDirection: "row", alignItems: "flex-start", padding: 10, backgroundColor: "rgba(200,169,107,0.06)", borderRadius: 10, borderWidth: 1, borderColor: "rgba(200,169,107,0.15)", marginTop: 4 },
  legalRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: 10 },
});
