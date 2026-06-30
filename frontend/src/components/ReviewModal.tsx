import { useState } from "react";
import { View, StyleSheet, Modal, Pressable, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

export default function ReviewModal({ visible, bookingId, targetName, onClose, onSubmitted }: {
  visible: boolean;
  bookingId: string | null;
  targetName: string;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!bookingId) return;
    if (rating < 1) { setError("Sélectionnez une note."); return; }
    setError(""); setLoading(true);
    try {
      await api("/reviews", { method: "POST", body: { booking_id: bookingId, rating, comment } });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setRating(0); setComment("");
      onSubmitted();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.bg} onPress={onClose} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.handle} />
        <Txt weight="extrabold" size="xl">Laisser un avis</Txt>
        <Txt color={colors.muted} style={{ marginTop: spacing.xs, marginBottom: spacing.lg }}>Notez votre expérience avec {targetName}.</Txt>
        <View style={styles.stars}>
          {[1, 2, 3, 4, 5].map((n) => (
            <Pressable key={n} testID={`star-${n}`} onPress={() => { Haptics.selectionAsync().catch(() => {}); setRating(n); }} hitSlop={6}>
              <Ionicons name={n <= rating ? "star" : "star-outline"} size={40} color={n <= rating ? colors.star : colors.borderStrong} />
            </Pressable>
          ))}
        </View>
        <TextInput
          testID="review-comment"
          value={comment}
          onChangeText={setComment}
          placeholder="Partagez votre expérience (optionnel)…"
          placeholderTextColor={colors.muted}
          multiline
          style={styles.input}
        />
        {error ? <Txt color={colors.error} size="sm" style={{ marginBottom: spacing.sm }}>{error}</Txt> : null}
        <Button testID="submit-review-button" title="Publier mon avis" loading={loading} onPress={submit} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg },
  handle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: spacing.lg },
  stars: { flexDirection: "row", justifyContent: "center", gap: spacing.sm, marginBottom: spacing.lg },
  input: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, minHeight: 80, textAlignVertical: "top", fontFamily: font.medium, fontSize: fontSize.base, color: colors.onSurface, marginBottom: spacing.lg },
});
