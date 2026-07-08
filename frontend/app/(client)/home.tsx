import { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { Txt, Button, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing, shadow } from "@/src/theme";

type Property = {
  property_id: string;
  name: string;
  type: string;
  address?: string;
  photos?: string[];
  surface?: number;
  year_built?: number;
  equipment_count?: number;
  document_count?: number;
  reminder_count?: number;
};

const TYPE_LABEL: Record<string, string> = {
  apartment: "Appartement",
  house: "Maison",
  office: "Bureau",
  commercial: "Commerce",
  vacation: "Résidence secondaire",
};

const TYPE_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  apartment: "business",
  house: "home",
  office: "briefcase",
  commercial: "storefront",
  vacation: "sunny",
};

export default function MyHomeList() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const props = await api<Property[]>("/properties");
      setItems(props);
    } catch {}
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const openCreate = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    router.push("/property/create");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] * 2 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Txt color={colors.muted} size="sm">Votre écosystème</Txt>
            <Txt weight="extrabold" size="3xl">Ma Maison</Txt>
          </View>
          <Pressable
            testID="add-property-header-btn"
            onPress={openCreate}
            style={styles.addBtn}
            android_ripple={{ color: "rgba(255,255,255,0.08)", borderless: true }}
          >
            <Ionicons name="add" size={22} color={colors.onSurface} />
          </Pressable>
        </View>

        {!loading && items.length === 0 && (
          <View style={{ paddingTop: spacing.xl }}>
            <View style={styles.heroEmpty}>
              <LinearGradient
                colors={["#221A0A", "#0B0B0F"]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={StyleSheet.absoluteFillObject as any}
              />
              <View style={styles.heroIconWrap}>
                <Ionicons name="home" size={32} color={colors.brand} />
              </View>
              <Txt weight="extrabold" size="2xl" style={{ marginTop: spacing.lg, textAlign: "center" }}>
                Créez votre premier bien
              </Txt>
              <Txt color={colors.muted} style={{ textAlign: "center", marginTop: spacing.sm, paddingHorizontal: spacing.xl, lineHeight: 22 }}>
                Chaque intervention, garantie, document et équipement sera automatiquement rattaché à votre habitat.
              </Txt>
              <Button
                testID="empty-add-property-btn"
                title="Ajouter un bien"
                icon="add-circle"
                onPress={openCreate}
                style={{ marginTop: spacing.xl, paddingHorizontal: spacing["2xl"] }}
              />
            </View>

            <View style={{ marginTop: spacing.xl, marginHorizontal: spacing.lg }}>
              <Txt color={colors.muted} size="sm" weight="semibold" style={{ marginBottom: spacing.md, letterSpacing: 0.5 }}>
                POURQUOI CRÉER UN BIEN ?
              </Txt>
              {[
                { icon: "documents" as const, title: "Passeport numérique", subtitle: "Toutes vos factures et garanties centralisées." },
                { icon: "construct" as const, title: "Équipements suivis", subtitle: "Chaudière, VMC, panneaux… avec dates d'entretien." },
                { icon: "sparkles" as const, title: "IA prédictive (bientôt)", subtitle: "Anticipation des maintenances et risques." },
              ].map((f) => (
                <View key={f.title} style={styles.featureRow}>
                  <View style={styles.featureIcon}>
                    <Ionicons name={f.icon} size={18} color={colors.brand} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Txt weight="bold">{f.title}</Txt>
                    <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>{f.subtitle}</Txt>
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {items.length > 0 && (
          <View style={{ paddingHorizontal: spacing.lg, gap: spacing.lg }}>
            {items.map((p) => {
              const cover = p.photos && p.photos.length > 0 ? p.photos[0] : null;
              return (
                <Pressable
                  key={p.property_id}
                  testID={`property-card-${p.property_id}`}
                  onPress={() => {
                    Haptics.selectionAsync().catch(() => {});
                    router.push({ pathname: "/property/[id]", params: { id: p.property_id } });
                  }}
                  style={({ pressed }) => [styles.card, shadow.card, { transform: [{ scale: pressed ? 0.985 : 1 }] }]}
                >
                  <View style={styles.cover}>
                    {cover ? (
                      <Image source={{ uri: cover }} style={{ width: "100%", height: "100%" }} contentFit="cover" transition={200} />
                    ) : (
                      <LinearGradient colors={["#2A2216", "#0B0B0F"]} style={StyleSheet.absoluteFillObject as any} />
                    )}
                    <LinearGradient
                      colors={["rgba(0,0,0,0)", "rgba(11,11,15,0.9)"]}
                      style={StyleSheet.absoluteFillObject as any}
                    />
                    <View style={styles.typeChip}>
                      <Ionicons name={TYPE_ICON[p.type] || "home"} size={12} color={colors.brand} />
                      <Txt size="sm" weight="semibold" color={colors.brand} style={{ marginLeft: 4 }}>
                        {TYPE_LABEL[p.type] || p.type}
                      </Txt>
                    </View>
                    <View style={styles.coverBottom}>
                      <Txt weight="extrabold" size="xl" style={{ color: "#fff" }}>{p.name}</Txt>
                      {!!p.address && (
                        <Txt size="sm" color="#D4D4DA" style={{ marginTop: 2 }} numberOfLines={1}>{p.address}</Txt>
                      )}
                    </View>
                  </View>
                  <View style={styles.cardStats}>
                    <Stat icon="cog" label="Équipements" value={p.equipment_count ?? 0} />
                    <View style={styles.statDivider} />
                    <Stat icon="document-text" label="Documents" value={p.document_count ?? 0} />
                    <View style={styles.statDivider} />
                    <Stat icon="notifications" label="Rappels" value={p.reminder_count ?? 0} highlight={(p.reminder_count ?? 0) > 0} />
                  </View>
                </Pressable>
              );
            })}
            <Pressable
              testID="add-property-list-btn"
              onPress={openCreate}
              style={styles.addRow}
              android_ripple={{ color: "rgba(212,175,106,0.08)" }}
            >
              <Ionicons name="add-circle-outline" size={22} color={colors.brand} />
              <Txt weight="bold" color={colors.brand} style={{ marginLeft: spacing.sm }}>Ajouter un bien</Txt>
            </Pressable>
          </View>
        )}

        {loading && items.length === 0 && (
          <View style={{ paddingTop: spacing["3xl"] }}>
            <EmptyState icon="home" title="Chargement…" subtitle="Récupération de vos biens" />
          </View>
        )}
      </ScrollView>
    </View>
  );
}

function Stat({ icon, label, value, highlight }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: number; highlight?: boolean }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Ionicons name={icon} size={14} color={highlight ? colors.brand : colors.muted} />
        <Txt weight="extrabold" size="lg" style={{ marginLeft: 4 }} color={highlight ? colors.brand : colors.onSurface}>{value}</Txt>
      </View>
      <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.lg },
  addBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  heroEmpty: {
    marginHorizontal: spacing.lg,
    borderRadius: radius.lg,
    paddingVertical: spacing["2xl"],
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.border,
  },
  heroIconWrap: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: colors.brand + "1F",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.brand + "44",
  },
  featureRow: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    marginBottom: spacing.sm,
    borderWidth: 1, borderColor: colors.border,
  },
  featureIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.brand + "1A",
    alignItems: "center", justifyContent: "center",
    marginRight: spacing.md,
  },
  card: {
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    overflow: "hidden",
  },
  cover: { height: 200, position: "relative", justifyContent: "flex-end" },
  typeChip: {
    position: "absolute", top: spacing.md, left: spacing.md,
    flexDirection: "row", alignItems: "center",
    backgroundColor: "rgba(11,11,15,0.65)",
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.brand + "44",
  },
  coverBottom: { padding: spacing.lg },
  cardStats: {
    flexDirection: "row",
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  statDivider: { width: 1, backgroundColor: colors.border, marginVertical: 4 },
  addRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    paddingVertical: spacing.lg,
    borderWidth: 1, borderColor: colors.brand + "55",
    borderStyle: "dashed",
    borderRadius: radius.lg,
    backgroundColor: colors.brand + "0A",
  },
});
