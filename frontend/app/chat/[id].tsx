import { useEffect, useRef, useState, useCallback } from "react";
import { View, StyleSheet, FlatList, Pressable, TextInput, Platform } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

type Message = { message_id: string; sender_id: string; sender_name: string; text: string; created_at: string };

export default function Chat() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<{ messages: Message[] }>(`/conversations/${id}`);
      setMessages(data.messages);
    } catch {}
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load]);

  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setText("");
    setSending(true);
    try {
      const msg = await api<Message>(`/conversations/${id}/messages`, { method: "POST", body: { text: t } });
      setMessages((prev) => [...prev, msg]);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
    } catch {} finally { setSending(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }} numberOfLines={1}>{name || "Conversation"}</Txt>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "translate-with-padding"}
        keyboardVerticalOffset={0}
      >
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.message_id}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          renderItem={({ item }) => {
            const mine = item.sender_id === user?.user_id;
            return (
              <View testID={`message-${item.message_id}`} style={[styles.bubbleRow, { justifyContent: mine ? "flex-end" : "flex-start" }]}>
                <View style={[styles.bubble, mine ? styles.mine : styles.theirs]}>
                  <Txt color={mine ? colors.onSurfaceInverse : colors.onSurface}>{item.text}</Txt>
                </View>
              </View>
            );
          }}
        />
        <View style={[styles.inputBar, { paddingBottom: insets.bottom + spacing.sm }]}>
          <TextInput
            testID="chat-input"
            value={text}
            onChangeText={setText}
            placeholder="Votre message…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            multiline
          />
          <Pressable testID="send-button" onPress={send} disabled={sending || !text.trim()} style={[styles.sendBtn, { opacity: text.trim() ? 1 : 0.4 }]}>
            <Ionicons name="arrow-up" size={22} color={colors.onSurfaceInverse} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  bubbleRow: { flexDirection: "row" },
  bubble: { maxWidth: "78%", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.lg },
  mine: { backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  theirs: { backgroundColor: colors.surfaceSecondary, borderBottomLeftRadius: 4 },
  inputBar: { flexDirection: "row", alignItems: "flex-end", paddingHorizontal: spacing.lg, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider, gap: spacing.sm },
  input: { flex: 1, maxHeight: 120, minHeight: 44, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.sm, fontFamily: font.medium, fontSize: fontSize.base, color: colors.onSurface },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
});
