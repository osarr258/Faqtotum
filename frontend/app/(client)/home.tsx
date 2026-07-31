/**
 * Faqtotum V2 — Home Profile (Apple Health inspired).
 * Hero picture, health score dial, large cards.
 */
import React, { useState, useCallback } from "react";
import { View, ScrollView, StyleSheet, Pressable, Dimensions } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import Svg, { Circle } from "react-native-svg";
import { Text, Card, Row, useTheme, space, radius, palette } from "@/src/design";
import { hap } from "@/src/design/haptics";
import { api } from "@/src/api";

const HERO_H = 380;

type Property = {
  property_id: string; name: string; type: string; city?: string; postal_code?: string;
  photos?: string[]; cover_color?: string; health_score?: number;
  surface?: number; rooms?: number; dpe_grade?: string;
};

type Insights = {
  equipment_count?: number;
  document_count?: number;
  upcoming_maintenance?: number;
  money_invested_cents?: number;
};

function HealthDial({ score, size = 148, stroke = 10 }: { score: number; size?: number; stroke?: number }) {
  const t = useTheme();
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(100, score)) / 100);
  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
      <Svg width={size} height={size}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={t.border} strokeWidth={stroke} fill="none" />
        <Circle
          cx={size / 2} cy={size / 2} r={r}
          stroke={palette.gold} strokeWidth={stroke} fill="none"
          strokeDasharray={c} strokeDashoffset={off}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <View style={{ position: "absolute", alignItems: "center" }}>
        <Text variant="hero" style={{ letterSpacing: -1.5 }}>{score}</Text>
        <Text variant="caption" tone="fgMuted">SUR 100</Text>
      </View>
    </View>
  );
}

function MetricTile({ icon, label, value, onPress }: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
  onPress?: () => void;
}) {
  const t = useTheme();
  return (
    <Pressable onPress={() => { hap.tap(); onPress?.(); }} style={{ flex: 1 }}>
      <View style={{
        backgroundColor: t.bgAlt,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: t.border,
        padding: space.lg,
        gap: space.sm,
        minHeight: 108,
      }}>
        <View style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: t.bgElevated, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: t.border }}>
          <Ionicons name={icon} size={18} color={t.fg} />
        </View>
        <Text variant="caption" tone="fgMuted">{label.toUpperCase()}</Text>
        <Text variant="h3">{value}</Text>
      </View>
    </Pressable>
  );
}

export default function HomeProfile() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [prop, setProp] = useState<Property | null>(null);
  const [insights, setInsights] = useState<Insights>({});

  const load = useCallback(async () => {
    try {
      const list = await api<{ items: Property[] }>("/properties");
      const first = list?.items?.[0] || null;
      setProp(first);
      if (first) {
        try {
          const ins = await api<Insights>(`/properties/${first.property_id}/insights`);
          setInsights(ins || {});
        } catch {}
      }
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const heroImage = prop?.photos?.[0];
  const health = prop?.health_score ?? 94;

  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <StatusBar style="light" />

      {!prop ? (
        <ScrollView contentContainerStyle={{ padding: space.xl, paddingTop: insets.top + space.huge }}>
          <Text variant="caption" tone="fgMuted" style={{ letterSpacing: 4 }}>FAQTOTUM</Text>
          <Text variant="display" style={{ marginTop: space.md, letterSpacing: -2 }}>Ma maison</Text>
          <Text variant="body" tone="fgMuted" style={{ marginTop: space.md, maxWidth: 320 }}>
            {"Ajoutez votre bien pour que Faqtotum s'en occupe."}
          </Text>
          <Pressable
            onPress={() => { hap.firm(); router.push("/property/create"); }}
            style={{
              marginTop: space.xxl, height: 56, borderRadius: 999,
              backgroundColor: t.fg, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: space.sm,
            }}
          >
            <Ionicons name="add" size={20} color={t.bg} />
            <Text variant="h3" style={{ color: t.bg }}>Ajouter un bien</Text>
          </Pressable>
        </ScrollView>
      ) : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 200 }}>
          {/* HERO */}
          <View style={{ height: HERO_H }}>
            {heroImage ? (
              <Image source={{ uri: heroImage }} style={StyleSheet.absoluteFillObject as any} contentFit="cover" />
            ) : (
              <View style={[StyleSheet.absoluteFillObject, { backgroundColor: prop.cover_color || palette.ink }] as any} />
            )}
            <LinearGradient
              colors={["rgba(11,11,13,0.20)", "rgba(11,11,13,0.10)", t.bg]}
              locations={[0, 0.4, 1]}
              style={StyleSheet.absoluteFillObject as any}
            />
            <View style={{ position: "absolute", top: insets.top + space.md, left: space.xl, right: space.xl, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <Text variant="caption" style={{ color: "rgba(255,255,255,0.75)", letterSpacing: 4 }}>MA MAISON</Text>
              <Pressable onPress={() => { hap.tap(); router.push({ pathname: "/property/create", params: { id: prop.property_id } }); }} hitSlop={8}
                style={{ width: 36, height: 36, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.16)", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "rgba(255,255,255,0.24)" }}>
                <Ionicons name="create-outline" size={18} color={palette.paper} />
              </Pressable>
            </View>
            <View style={{ position: "absolute", bottom: space.xxl, left: space.xl, right: space.xl }}>
              <Text variant="hero" style={{ color: palette.paper }}>{prop.name}</Text>
              {(!!prop.city || !!prop.postal_code) && (
                <Text variant="body" style={{ color: "rgba(248,248,245,0.75)", marginTop: space.xs }}>
                  {[prop.postal_code, prop.city].filter(Boolean).join("  ·  ")}
                </Text>
              )}
            </View>
          </View>

          {/* HEALTH SCORE */}
          <View style={{ paddingHorizontal: space.xl, marginTop: -40 }}>
            <Card padded elevated style={{ flexDirection: "row", alignItems: "center", gap: space.lg }}>
              <HealthDial score={health} />
              <View style={{ flex: 1 }}>
                <Text variant="caption" tone="fgMuted">SCORE DE SANTÉ</Text>
                <Text variant="h2" style={{ marginTop: 2 }}>{health >= 90 ? "Excellent" : health >= 70 ? "Bon" : "À surveiller"}</Text>
                <Text variant="meta" tone="fgMuted" style={{ marginTop: 4 }}>Mise à jour aujourd'hui</Text>
              </View>
            </Card>
          </View>

          {/* METRIC TILES */}
          <View style={{ paddingHorizontal: space.xl, marginTop: space.xl, gap: space.md }}>
            <Row gap={space.md}>
              <MetricTile icon="cog-outline" label="Équipements" value={String(insights.equipment_count ?? 0)} onPress={() => router.push(`/property/${prop.property_id}/equipment`)} />
              <MetricTile icon="document-text-outline" label="Documents" value={String(insights.document_count ?? 0)} onPress={() => router.push(`/property/${prop.property_id}/documents`)} />
            </Row>
            <Row gap={space.md}>
              <MetricTile icon="notifications-outline" label="Rappels" value={String(insights.upcoming_maintenance ?? 0)} onPress={() => router.push(`/property/${prop.property_id}/reminders`)} />
              <MetricTile icon="stats-chart-outline" label="Budget" value={insights.money_invested_cents ? `${Math.round((insights.money_invested_cents || 0) / 100)}\u00a0€` : "—"} onPress={() => router.push(`/property/${prop.property_id}/budget`)} />
            </Row>
          </View>

          {/* SECTIONS */}
          <View style={{ paddingHorizontal: space.xl, marginTop: space.xxl, gap: space.md }}>
            {[
              { icon: "git-branch-outline", label: "Historique", route: `/property/${prop.property_id}/timeline` },
              { icon: "flash-outline", label: "Consommation & énergie", route: `/property/${prop.property_id}/budget` },
              { icon: "shield-checkmark-outline", label: "Garanties & assurance", route: `/property/${prop.property_id}/documents` },
              { icon: "calendar-outline", label: "Prochaines interventions", route: `/property/${prop.property_id}/reminders` },
            ].map((row) => (
              <Pressable key={row.label} onPress={() => { hap.tap(); router.push(row.route as any); }}>
                <View style={{
                  backgroundColor: t.bgAlt,
                  borderRadius: radius.lg,
                  borderWidth: 1, borderColor: t.border,
                  padding: space.lg,
                  flexDirection: "row", alignItems: "center", gap: space.md,
                }}>
                  <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: t.bgElevated, borderWidth: 1, borderColor: t.border, alignItems: "center", justifyContent: "center" }}>
                    <Ionicons name={row.icon as any} size={18} color={t.fg} />
                  </View>
                  <Text variant="h3" style={{ flex: 1 }}>{row.label}</Text>
                  <Ionicons name="chevron-forward" size={20} color={t.fgSubtle} />
                </View>
              </Pressable>
            ))}
          </View>
        </ScrollView>
      )}
    </View>
  );
}
