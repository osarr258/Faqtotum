/**
 * Faqtotum V2 — AI Home (default tab).
 * ChatGPT-style: 80% of the screen is a conversation, floating input,
 * intelligent suggestions, AI-as-navigation (intent → route).
 */
import React, { useRef, useState } from "react";
import {
  View, ScrollView, Pressable, KeyboardAvoidingView, Platform, TextInput,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { Text, Chip, useTheme, space, radius, palette } from "@/src/design";
import { hap } from "@/src/design/haptics";

type Msg = { id: string; from: "user" | "ai"; text: string };

/** Basic intent router — the moment the user types something, we detect the
 *  intent and can push them to the right screen. Keep it deterministic and
 *  cheap: a small keyword table wins 90% of the value. */
const INTENTS: { pattern: RegExp; route: string; hint: string }[] = [
  { pattern: /facture|invoice|paiement|payer/i, route: "/profile/payment-methods", hint: "Ouvre les paiements" },
  { pattern: /plombier|fuite|robinet|chauffe-eau/i, route: "/map?trade=plombier", hint: "Cherche un plombier" },
  { pattern: /électric|electricien|panne|disjonct/i, route: "/map?trade=electricien", hint: "Cherche un électricien" },
  { pattern: /maison|logement|bien/i, route: "/(client)/home", hint: "Ouvre ma maison" },
  { pattern: /dépens|budget|conso/i, route: "/(client)/home", hint: "Ouvre le budget" },
  { pattern: /rappel|entretien|maintenance/i, route: "/(client)/home", hint: "Rappels & entretien" },
];

const SUGGESTIONS = [
  { icon: "water-outline", label: "J'ai une fuite" },
  { icon: "flash-outline", label: "Panne électrique" },
  { icon: "thermometer-outline", label: "Chauffage en panne" },
  { icon: "home-outline", label: "Montrer ma maison" },
  { icon: "receipt-outline", label: "Mes factures" },
  { icon: "calendar-outline", label: "Prochains entretiens" },
] as const;

export default function AiHome() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const scrollRef = useRef<ScrollView>(null);

  const send = (text: string) => {
    if (!text.trim()) return;
    hap.soft();
    const userMsg: Msg = { id: `u${Date.now()}`, from: "user", text };
    setMsgs((m) => [...m, userMsg]);
    setQ("");
    // Intent detection — route immediately if we recognize one.
    const intent = INTENTS.find((i) => i.pattern.test(text));
    setTimeout(() => {
      const aiText = intent
        ? `${intent.hint}… je t'y emmène.`
        : "Je note. Peux-tu me donner un peu plus de détails ?";
      setMsgs((m) => [...m, { id: `a${Date.now()}`, from: "ai", text: aiText }]);
      if (intent) {
        setTimeout(() => { hap.ok(); router.push(intent.route as any); }, 650);
      }
      requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
    }, 220);
  };

  const empty = msgs.length === 0;

  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <StatusBar style={t.scheme === "dark" ? "light" : "dark"} />

      {/* Header */}
      <View style={{ paddingTop: insets.top + space.md, paddingHorizontal: space.xl, paddingBottom: space.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <View>
          <Text variant="caption" tone="fgMuted" style={{ letterSpacing: 4 }}>FAQTOTUM</Text>
          <Text variant="h2" style={{ marginTop: 2 }}>Bonjour</Text>
        </View>
        <Pressable onPress={() => { hap.tap(); router.push("/(client)/profile"); }} hitSlop={8}>
          <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: t.bgAlt, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: t.border }}>
            <Ionicons name="person-outline" size={18} color={t.fg} />
          </View>
        </Pressable>
      </View>

      {/* Conversation — or hero prompt when empty */}
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: space.xl, paddingBottom: 200 }}
        showsVerticalScrollIndicator={false}
      >
        {empty ? (
          <View style={{ marginTop: space.huge }}>
            <Text variant="display" style={{ letterSpacing: -2 }}>Que puis‑je faire</Text>
            <Text variant="display" tone="fgMuted" style={{ letterSpacing: -2 }}>pour votre maison ?</Text>
            <Text variant="body" tone="fgMuted" style={{ marginTop: space.lg, maxWidth: 320 }}>
              Décrivez un souci, parlez, ou envoyez une photo. Faqtotum comprend et agit.
            </Text>
          </View>
        ) : (
          <View style={{ gap: space.md }}>
            {msgs.map((m) => (
              <View
                key={m.id}
                style={{
                  alignSelf: m.from === "user" ? "flex-end" : "flex-start",
                  maxWidth: "85%",
                  backgroundColor: m.from === "user" ? t.fg : t.bgAlt,
                  paddingHorizontal: space.lg,
                  paddingVertical: space.md,
                  borderRadius: radius.lg,
                  borderBottomRightRadius: m.from === "user" ? radius.sm : radius.lg,
                  borderBottomLeftRadius: m.from === "ai" ? radius.sm : radius.lg,
                  borderWidth: m.from === "ai" ? 1 : 0,
                  borderColor: t.border,
                }}
              >
                <Text style={{ color: m.from === "user" ? t.bg : t.fg }}>{m.text}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Suggestion chips */}
      {empty && (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: insets.bottom + 140 }}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: space.xl, gap: space.sm }}>
            {SUGGESTIONS.map((s) => (
              <Chip key={s.label} label={s.label} icon={s.icon as any} onPress={() => send(s.label)} />
            ))}
          </ScrollView>
        </View>
      )}

      {/* Floating input bar */}
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
        style={{ position: "absolute", left: 0, right: 0, bottom: insets.bottom + 72 }}
      >
        <View style={{
          marginHorizontal: space.xl,
          backgroundColor: t.bgElevated,
          borderRadius: 28,
          borderWidth: 1,
          borderColor: t.border,
          paddingHorizontal: space.md,
          paddingVertical: space.sm,
          flexDirection: "row",
          alignItems: "center",
          gap: space.sm,
          shadowColor: palette.ink, shadowOpacity: 0.10, shadowRadius: 24, shadowOffset: { width: 0, height: 12 }, elevation: 8,
        }}>
          <Pressable onPress={() => hap.tap()} hitSlop={8} style={{ width: 36, height: 36, alignItems: "center", justifyContent: "center", borderRadius: 999 }}>
            <Ionicons name="add" size={22} color={t.fg} />
          </Pressable>
          <TextInput
            placeholder="Demandez à Faqtotum…"
            placeholderTextColor={t.fgSubtle}
            value={q}
            onChangeText={setQ}
            onSubmitEditing={() => send(q)}
            returnKeyType="send"
            style={{
              flex: 1, color: t.fg,
              fontSize: 16, fontFamily: "Jakarta500",
              paddingVertical: Platform.OS === "ios" ? 10 : 6,
            }}
          />
          {q.trim().length > 0 ? (
            <Pressable onPress={() => send(q)} hitSlop={8} style={{ width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 999, backgroundColor: t.fg }}>
              <Ionicons name="arrow-up" size={20} color={t.bg} />
            </Pressable>
          ) : (
            <Pressable onPress={() => hap.firm()} hitSlop={8} style={{ width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 999, backgroundColor: t.fg }}>
              <Ionicons name="mic" size={20} color={t.bg} />
            </Pressable>
          )}
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}
