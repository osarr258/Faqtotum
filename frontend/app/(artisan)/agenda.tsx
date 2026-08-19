/**
 * Artisan Agenda — FAQTOTUM v1
 *
 * Vue semaine minimaliste :
 *   1. Header + navigation semaine (◀ 12–18 mai ▶)
 *   2. Bandeau 7 jours horizontal : jour+date+dot si occupé
 *   3. Détail du jour sélectionné (missions confirmées + créneaux)
 *   4. Ajout rapide de créneaux (date, heure, durée 60 min par défaut)
 *
 * Endpoints réutilisés (aucun backend touché) :
 *   GET  /bookings/received
 *   GET  /artisans/me/slots
 *   POST /artisans/me/slots
 *   DELETE /artisans/me/slots/{slot_id}
 */
import { useCallback, useMemo, useState } from "react";
import {
  View,
  StyleSheet,
  ScrollView,
  Pressable,
  TextInput,
  Alert,
  RefreshControl,
  ActivityIndicator,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing, font, fontSize } from "@/src/theme";

type Booking = {
  booking_id: string;
  client_name: string;
  trade_name?: string;
  date: string;
  slot: string;
  status: string;
};

type Slot = {
  slot_id: string;
  date: string;
  start_time: string;
  duration_min: number;
};

const DAY_LABELS = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"];
const MONTH_LABELS = [
  "janv.", "févr.", "mars", "avr.", "mai", "juin",
  "juil.", "août", "sept.", "oct.", "nov.", "déc.",
];

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function startOfWeek(d: Date): Date {
  const copy = new Date(d);
  const dow = copy.getDay(); // 0=dim, 1=lun...
  const diff = dow === 0 ? -6 : 1 - dow; // Lundi comme début
  copy.setDate(copy.getDate() + diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function addDays(d: Date, n: number): Date {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

function formatRange(start: Date, end: Date): string {
  const sameMonth = start.getMonth() === end.getMonth();
  if (sameMonth) {
    return `${start.getDate()}–${end.getDate()} ${MONTH_LABELS[end.getMonth()]}`;
  }
  return `${start.getDate()} ${MONTH_LABELS[start.getMonth()]} – ${end.getDate()} ${MONTH_LABELS[end.getMonth()]}`;
}

export default function ArtisanAgenda() {
  const insets = useSafeAreaInsets();
  const [weekStart, setWeekStart] = useState<Date>(() => startOfWeek(new Date()));
  const [selectedIso, setSelectedIso] = useState<string>(() => toIsoDate(new Date()));
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [newTime, setNewTime] = useState("");
  const [addingSlot, setAddingSlot] = useState(false);

  const weekDays = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  }, [weekStart]);

  const load = useCallback(async () => {
    try {
      const [bk, sl] = await Promise.all([
        api<Booking[]>("/bookings/received").catch(() => []),
        api<{ slots: Slot[] }>("/artisans/me/slots").catch(() => ({ slots: [] })),
      ]);
      setBookings(bk || []);
      setSlots(sl?.slots || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  // Occupied days in the current week (active bookings + slots).
  const busyByIso = useMemo(() => {
    const map: Record<string, { bookings: number; slots: number }> = {};
    for (const d of weekDays) {
      map[toIsoDate(d)] = { bookings: 0, slots: 0 };
    }
    for (const b of bookings) {
      if (
        map[b.date] &&
        (b.status === "accepted" ||
          b.status === "confirmed" ||
          b.status === "in_progress")
      ) {
        map[b.date].bookings += 1;
      }
    }
    for (const s of slots) {
      if (map[s.date]) map[s.date].slots += 1;
    }
    return map;
  }, [bookings, slots, weekDays]);

  const dayBookings = useMemo(
    () =>
      bookings.filter(
        (b) =>
          b.date === selectedIso &&
          (b.status === "accepted" ||
            b.status === "confirmed" ||
            b.status === "in_progress"),
      ),
    [bookings, selectedIso],
  );

  const daySlots = useMemo(
    () => slots.filter((s) => s.date === selectedIso),
    [slots, selectedIso],
  );

  const moveWeek = (delta: number) => {
    Haptics.selectionAsync().catch(() => {});
    setWeekStart((cur) => addDays(cur, 7 * delta));
  };

  const jumpToday = () => {
    Haptics.selectionAsync().catch(() => {});
    const now = new Date();
    setWeekStart(startOfWeek(now));
    setSelectedIso(toIsoDate(now));
  };

  const addSlot = async () => {
    if (!/^\d{2}:\d{2}$/.test(newTime)) {
      return Alert.alert("Format", "Utilisez le format HH:MM (ex : 09:30)");
    }
    setAddingSlot(true);
    try {
      await api("/artisans/me/slots", {
        method: "POST",
        body: {
          date: selectedIso,
          start_time: newTime,
          duration_min: 60,
        },
      });
      setNewTime("");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(
        () => {},
      );
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur";
      Alert.alert("Erreur", msg);
    } finally {
      setAddingSlot(false);
    }
  };

  const removeSlot = async (id: string) => {
    try {
      await api(`/artisans/me/slots/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur";
      Alert.alert("Erreur", msg);
    }
  };

  const today = toIsoDate(new Date());

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: insets.bottom + spacing["3xl"],
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.brand}
          />
        }
      >
        {/* --- Header ------------------------------------------------- */}
        <View style={styles.header}>
          <Txt size="sm" color={colors.muted}>
            Agenda
          </Txt>
          <View style={styles.headerRow}>
            <View style={{ flex: 1 }}>
              <Txt weight="extrabold" size="3xl" style={{ marginTop: 2 }}>
                {formatRange(weekStart, addDays(weekStart, 6))}
              </Txt>
            </View>
            <Pressable
              testID="today-btn"
              onPress={jumpToday}
              style={styles.todayBtn}
            >
              <Txt weight="bold" size="sm">
                {"Aujourd'hui"}
              </Txt>
            </Pressable>
          </View>
        </View>

        {/* --- Week strip -------------------------------------------- */}
        <View style={styles.weekNav}>
          <Pressable
            testID="week-prev"
            onPress={() => moveWeek(-1)}
            style={styles.navArrow}
          >
            <Ionicons name="chevron-back" size={20} color={colors.onSurface} />
          </Pressable>
          <View style={styles.weekStrip}>
            {weekDays.map((d) => {
              const iso = toIsoDate(d);
              const isSelected = iso === selectedIso;
              const isToday = iso === today;
              const busy = busyByIso[iso];
              const hasBookings = busy && busy.bookings > 0;
              const hasSlots = busy && busy.slots > 0;
              return (
                <Pressable
                  key={iso}
                  testID={`day-${iso}`}
                  onPress={() => {
                    Haptics.selectionAsync().catch(() => {});
                    setSelectedIso(iso);
                  }}
                  style={[styles.dayCell, isSelected && styles.dayCellSelected]}
                >
                  <Txt
                    size="sm"
                    color={isSelected ? colors.textInverse : colors.muted}
                    style={{ marginBottom: 2 }}
                  >
                    {DAY_LABELS[d.getDay()]}
                  </Txt>
                  <Txt
                    weight="extrabold"
                    color={isSelected ? colors.textInverse : colors.onSurface}
                  >
                    {d.getDate()}
                  </Txt>
                  <View style={styles.dayDots}>
                    {hasBookings ? (
                      <View
                        style={[
                          styles.dot,
                          {
                            backgroundColor: isSelected
                              ? colors.textInverse
                              : colors.brand,
                          },
                        ]}
                      />
                    ) : null}
                    {hasSlots ? (
                      <View
                        style={[
                          styles.dot,
                          {
                            backgroundColor: isSelected
                              ? colors.textInverse
                              : colors.muted,
                            marginLeft: 3,
                          },
                        ]}
                      />
                    ) : null}
                  </View>
                  {isToday && !isSelected ? (
                    <View style={styles.todayUnderline} />
                  ) : null}
                </Pressable>
              );
            })}
          </View>
          <Pressable
            testID="week-next"
            onPress={() => moveWeek(1)}
            style={styles.navArrow}
          >
            <Ionicons name="chevron-forward" size={20} color={colors.onSurface} />
          </Pressable>
        </View>

        {/* --- Day detail -------------------------------------------- */}
        {loading ? (
          <View style={{ paddingTop: 40 }}>
            <ActivityIndicator color={colors.brand} />
          </View>
        ) : (
          <View style={{ paddingHorizontal: spacing.lg }}>
            {/* Missions confirmées ce jour */}
            <View style={styles.sectionHead}>
              <Txt weight="bold" size="lg">
                Missions
              </Txt>
              {dayBookings.length > 0 && (
                <Txt size="sm" color={colors.muted} style={{ marginLeft: 8 }}>
                  {dayBookings.length}
                </Txt>
              )}
            </View>
            {dayBookings.length === 0 ? (
              <View style={styles.emptyRow}>
                <Ionicons
                  name="briefcase-outline"
                  size={18}
                  color={colors.muted}
                />
                <Txt
                  size="sm"
                  color={colors.muted}
                  style={{ marginLeft: spacing.sm }}
                >
                  Aucune mission confirmée
                </Txt>
              </View>
            ) : (
              dayBookings.map((b) => (
                <View key={b.booking_id} style={styles.rowCard}>
                  <View style={styles.timeBox}>
                    <Txt weight="extrabold">
                      {(b.slot || "").split("-")[0] || "—"}
                    </Txt>
                  </View>
                  <View style={{ flex: 1, marginLeft: spacing.md }}>
                    <Txt weight="bold">{b.client_name}</Txt>
                    {b.trade_name ? (
                      <Txt size="sm" color={colors.muted}>
                        {b.trade_name}
                      </Txt>
                    ) : null}
                  </View>
                </View>
              ))
            )}

            {/* Créneaux ouverts */}
            <View style={[styles.sectionHead, { marginTop: spacing.xl }]}>
              <Txt weight="bold" size="lg">
                Créneaux ouverts
              </Txt>
              {daySlots.length > 0 && (
                <Txt size="sm" color={colors.muted} style={{ marginLeft: 8 }}>
                  {daySlots.length}
                </Txt>
              )}
            </View>

            {/* Add slot */}
            <View style={styles.addRow}>
              <View style={styles.inputWrap}>
                <Ionicons
                  name="time-outline"
                  size={16}
                  color={colors.muted}
                />
                <TextInput
                  testID="slot-time-input"
                  value={newTime}
                  onChangeText={setNewTime}
                  placeholder="HH:MM"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  keyboardType="numeric"
                  maxLength={5}
                />
              </View>
              <Pressable
                testID="add-slot"
                onPress={addSlot}
                disabled={addingSlot}
                style={({ pressed }) => [
                  styles.addBtn,
                  (addingSlot || pressed) && { opacity: 0.75 },
                ]}
              >
                <Ionicons name="add" size={18} color={colors.textInverse} />
                <Txt weight="bold" size="sm" color={colors.textInverse}>
                  Ajouter
                </Txt>
              </Pressable>
            </View>

            {daySlots.length === 0 ? (
              <View style={styles.emptyRow}>
                <Ionicons
                  name="calendar-outline"
                  size={18}
                  color={colors.muted}
                />
                <Txt
                  size="sm"
                  color={colors.muted}
                  style={{ marginLeft: spacing.sm }}
                >
                  Aucun créneau ouvert pour ce jour
                </Txt>
              </View>
            ) : (
              daySlots.map((s) => (
                <View key={s.slot_id} style={styles.rowCard}>
                  <View style={styles.timeBox}>
                    <Txt weight="extrabold">{s.start_time}</Txt>
                  </View>
                  <View style={{ flex: 1, marginLeft: spacing.md }}>
                    <Txt weight="bold">Créneau disponible</Txt>
                    <Txt size="sm" color={colors.muted}>
                      Durée {s.duration_min} min
                    </Txt>
                  </View>
                  <Pressable
                    testID={`del-slot-${s.slot_id}`}
                    onPress={() => removeSlot(s.slot_id)}
                    hitSlop={10}
                  >
                    <Ionicons
                      name="trash-outline"
                      size={18}
                      color={colors.muted}
                    />
                  </Pressable>
                </View>
              ))
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  header: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "flex-end",
  },
  todayBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  weekNav: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    marginBottom: spacing.lg,
  },
  navArrow: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  weekStrip: {
    flex: 1,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  dayCell: {
    flex: 1,
    alignItems: "center",
    paddingVertical: 8,
    marginHorizontal: 2,
    borderRadius: radius.md,
    minHeight: 62,
  },
  dayCellSelected: {
    backgroundColor: colors.brand,
  },
  dayDots: {
    marginTop: 4,
    flexDirection: "row",
    alignItems: "center",
    height: 6,
  },
  dot: {
    width: 4,
    height: 4,
    borderRadius: 2,
  },
  todayUnderline: {
    marginTop: 2,
    width: 14,
    height: 2,
    borderRadius: 1,
    backgroundColor: colors.brand,
  },
  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.md,
  },
  rowCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
  },
  timeBox: {
    width: 64,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  emptyRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    marginBottom: spacing.md,
  },
  addRow: {
    flexDirection: "row",
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  inputWrap: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    gap: 6,
    height: 46,
  },
  input: {
    flex: 1,
    fontFamily: font.medium,
    fontSize: fontSize.base,
    color: colors.onSurface,
  },
  addBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: spacing.lg,
    height: 46,
    borderRadius: radius.md,
    backgroundColor: colors.brand,
    justifyContent: "center",
  },
});
