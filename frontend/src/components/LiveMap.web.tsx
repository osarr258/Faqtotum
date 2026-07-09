/**
 * LiveMap web fallback — stylized dark map with dots.
 */
import React from "react";
import { StyleSheet, View, Dimensions } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/ui";

type Artisan = {
  artisan_id: string;
  name: string;
  current_lat: number;
  current_lng: number;
  trade_name: string;
  eta_min: number;
  rating: number;
  available_now?: boolean;
};

const COLORS = { accent: "#C8A96B", bg: "#0B0B0B", white: "#FFFFFF", muted: "#6E6E73" };
const { width: SW, height: SH } = Dimensions.get("window");

export default function LiveMap({
  center,
  radius,
  artisans,
  onSelect,
  selectedId,
}: {
  center: { lat: number; lng: number };
  radius: number;
  artisans: Artisan[];
  onSelect?: (a: Artisan) => void;
  selectedId?: string | null;
}) {
  // Project lat/lng offsets into a normalized 0..1 square, then to view coords
  const project = (lat: number, lng: number) => {
    const dLat = radius / 55;
    const dLng = radius / 40;
    const nx = 0.5 + (lng - center.lng) / (dLng * 2);
    const ny = 0.5 - (lat - center.lat) / (dLat * 2);
    return { x: Math.max(0, Math.min(1, nx)) * SW, y: Math.max(0, Math.min(1, ny)) * (SH * 0.55) };
  };

  const meProj = project(center.lat, center.lng);
  const radiusPx = Math.min(SW, SH * 0.55) * 0.42; // visual radius

  return (
    <View style={StyleSheet.absoluteFill}>
      <LinearGradient
        colors={["#131318", "#0B0B0B", "#080809"]}
        style={StyleSheet.absoluteFill}
      />
      {/* Grid lines */}
      <View pointerEvents="none" style={StyleSheet.absoluteFill}>
        {Array.from({ length: 12 }, (_, i) => (
          <View
            key={`h${i}`}
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: (i * SH * 0.55) / 12,
              height: 1,
              backgroundColor: "rgba(200,169,107,0.05)",
            }}
          />
        ))}
        {Array.from({ length: 10 }, (_, i) => (
          <View
            key={`v${i}`}
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: (i * SW) / 10,
              width: 1,
              backgroundColor: "rgba(200,169,107,0.05)",
            }}
          />
        ))}
      </View>

      {/* Radius circle */}
      <View
        pointerEvents="none"
        style={{
          position: "absolute",
          left: meProj.x - radiusPx,
          top: meProj.y - radiusPx,
          width: radiusPx * 2,
          height: radiusPx * 2,
          borderRadius: radiusPx,
          borderWidth: 2,
          borderColor: "rgba(200,169,107,0.35)",
          backgroundColor: "rgba(200,169,107,0.05)",
        }}
      />

      {/* Client */}
      <View
        pointerEvents="none"
        style={{
          position: "absolute",
          left: meProj.x - 14,
          top: meProj.y - 14,
          width: 28, height: 28, borderRadius: 14,
          backgroundColor: "rgba(59,130,246,0.25)",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: "#3B82F6", borderWidth: 2, borderColor: "#FFF" }} />
      </View>

      {/* Artisans */}
      {artisans.map((a) => {
        const p = project(a.current_lat, a.current_lng);
        const selected = selectedId === a.artisan_id;
        return (
          <View
            key={a.artisan_id}
            onTouchStart={() => onSelect?.(a)}
            style={{ position: "absolute", left: p.x - 17, top: p.y - 22, alignItems: "center" }}
          >
            <View
              style={[
                {
                  width: 34, height: 34, borderRadius: 17,
                  backgroundColor: selected ? "#FFF" : COLORS.accent,
                  borderWidth: 2, borderColor: selected ? COLORS.accent : "#FFF",
                  alignItems: "center", justifyContent: "center",
                },
                selected && { transform: [{ scale: 1.2 }] },
              ]}
            >
              <Ionicons name="construct" size={14} color={COLORS.bg} />
              {a.available_now && (
                <View style={{ position: "absolute", top: -2, right: -2, width: 10, height: 10, borderRadius: 5, backgroundColor: "#34D399", borderWidth: 2, borderColor: "#FFF" }} />
              )}
            </View>
            <View style={{ marginTop: 2, backgroundColor: "rgba(11,11,11,0.85)", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
              <Txt size="sm" weight="bold" style={{ color: COLORS.white, fontSize: 10 }}>
                {a.eta_min}min
              </Txt>
            </View>
          </View>
        );
      })}

      {/* Attribution */}
      <View style={{ position: "absolute", right: 12, bottom: 12 }}>
        <Txt size="sm" style={{ color: COLORS.muted, fontSize: 10 }}>Aperçu — carte réelle sur mobile</Txt>
      </View>
    </View>
  );
}
