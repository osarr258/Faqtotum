import { useState, useEffect } from "react";
import { View, StyleSheet, Modal, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import { colors, radius, spacing } from "@/src/theme";

export type Filters = { maxRate?: number; minRating?: number; available?: boolean; sort?: string; nearMe?: boolean };

const RATE_OPTS = [{ l: "Tous", v: undefined }, { l: "≤ 40€", v: 40 }, { l: "≤ 50€", v: 50 }, { l: "≤ 60€", v: 60 }];
const RATING_OPTS = [{ l: "Tous", v: undefined }, { l: "4★+", v: 4 }, { l: "4.5★+", v: 4.5 }];
const SORT_OPTS = [{ l: "Mieux notés", v: "rating" }, { l: "Prix ↑", v: "rate_asc" }, { l: "Prix ↓", v: "rate_desc" }, { l: "Plus proches", v: "distance" }];

export default function FiltersModal({ visible, value, onApply, onClose }: {
  visible: boolean;
  value: Filters;
  onApply: (f: Filters) => void;
  onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [f, setF] = useState<Filters>(value);
  useEffect(() => { setF(value); }, [value, visible]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.bg} onPress={onClose} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.handle} />
        <Txt weight="extrabold" size="xl" style={{ marginBottom: spacing.lg }}>Filtres</Txt>
        <ScrollView showsVerticalScrollIndicator={false}>
          <Section title="Tarif horaire">
            {RATE_OPTS.map((o) => <Chip key={o.l} label={o.l} active={f.maxRate === o.v} onPress={() => setF({ ...f, maxRate: o.v })} testID={`filter-rate-${o.l}`} />)}
          </Section>
          <Section title="Note minimum">
            {RATING_OPTS.map((o) => <Chip key={o.l} label={o.l} active={f.minRating === o.v} onPress={() => setF({ ...f, minRating: o.v })} testID={`filter-rating-${o.l}`} />)}
          </Section>
          <Section title="Trier par">
            {SORT_OPTS.map((o) => <Chip key={o.v} label={o.l} active={(f.sort || "rating") === o.v} onPress={() => setF({ ...f, sort: o.v })} testID={`filter-sort-${o.v}`} />)}
          </Section>
          <Section title="Disponibilité">
            <Chip label="Disponibles uniquement" active={!!f.available} onPress={() => setF({ ...f, available: f.available ? undefined : true })} testID="filter-available" />
          </Section>
          <Section title="Proximité">
            <Chip label="Près de moi" active={!!f.nearMe} onPress={() => setF({ ...f, nearMe: !f.nearMe })} testID="filter-nearme" />
          </Section>
        </ScrollView>
        <View style={{ flexDirection: "row", gap: spacing.md, marginTop: spacing.md }}>
          <Button testID="filter-reset" title="Réinitialiser" variant="secondary" onPress={() => setF({})} style={{ flex: 1 }} />
          <Button testID="filter-apply" title="Appliquer" onPress={() => onApply(f)} style={{ flex: 1 }} />
        </View>
      </View>
    </Modal>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ marginBottom: spacing.lg }}>
      <Txt weight="semibold" size="sm" color={colors.onSurfaceSecondary} style={{ marginBottom: spacing.sm }}>{title}</Txt>
      <View style={styles.chips}>{children}</View>
    </View>
  );
}

function Chip({ label, active, onPress, testID }: { label: string; active: boolean; onPress: () => void; testID: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.chip, { backgroundColor: active ? colors.brand : colors.surfaceSecondary }]}>
      <Txt weight="semibold" size="sm" color={active ? colors.onSurfaceInverse : colors.onSurface}>{label}</Txt>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, maxHeight: "80%" },
  handle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: spacing.lg },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { height: 38, paddingHorizontal: spacing.lg, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
});
