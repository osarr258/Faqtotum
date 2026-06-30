import { useState, useCallback } from "react";
import { View, StyleSheet, FlatList, Pressable, RefreshControl } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Avatar, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, spacing } from "@/src/theme";

type Conversation = { conversation_id: string; other_name: string; trade_name: string; last_message: string; last_at: string };

function timeLabel(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
  } catch { return ""; }
}

export default function ConversationsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setConvs(await api<Conversation[]>("/conversations")); } catch {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Txt weight="extrabold" size="2xl">Messages</Txt>
      </View>
      <FlatList
        data={convs}
        keyExtractor={(c) => c.conversation_id}
        contentContainerStyle={{ paddingBottom: spacing["3xl"], flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        ListEmptyComponent={<EmptyState icon="chatbubbles-outline" title="Aucune conversation" subtitle="Une conversation est créée automatiquement après une réservation." />}
        renderItem={({ item }) => (
          <Pressable
            testID={`conversation-${item.conversation_id}`}
            onPress={() => router.push({ pathname: "/chat/[id]", params: { id: item.conversation_id, name: item.other_name } })}
            style={({ pressed }) => [styles.row, { opacity: pressed ? 0.7 : 1 }]}
          >
            <Avatar name={item.other_name} size={52} />
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Txt weight="bold" size="base" style={{ flex: 1 }} numberOfLines={1}>{item.other_name}</Txt>
                <Txt size="sm" color={colors.muted}>{timeLabel(item.last_at)}</Txt>
              </View>
              <Txt size="sm" color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>{item.last_message || item.trade_name}</Txt>
            </View>
          </Pressable>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
});
