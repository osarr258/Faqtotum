/**
 * Auxora Design System — Tokens
 * Matte black / off-white / warm grey / champagne gold, 4pt grid.
 * All colours drive both light and dark modes.
 */
export const palette = {
  ink:      "#0B0B0D",      // Primary matte black
  paper:    "#F8F8F5",      // Off white
  paperAlt: "#EFEEE8",
  grey:     "#7F8288",
  gold:     "#C8A96B",
  goldSoft: "#E7D6B0",
  line:     "rgba(11,11,13,0.08)",
  lineDark: "rgba(248,248,245,0.08)",
  success:  "#3E8F63",
  danger:   "#B0463C",
  amber:    "#C99A3D",
};

export const light = {
  bg:         palette.paper,
  bgElevated: "#FFFFFF",
  bgAlt:      palette.paperAlt,
  fg:         palette.ink,
  fgMuted:    "rgba(11,11,13,0.55)",
  fgSubtle:   "rgba(11,11,13,0.35)",
  border:     palette.line,
  overlay:    "rgba(11,11,13,0.55)",
  brand:      palette.gold,
  brandInk:   palette.ink,
  success:    palette.success,
  danger:     palette.danger,
  scheme:     "light" as const,
};

export const dark = {
  bg:         palette.ink,
  bgElevated: "#151517",
  bgAlt:      "#1B1B1E",
  fg:         palette.paper,
  fgMuted:    "rgba(248,248,245,0.60)",
  fgSubtle:   "rgba(248,248,245,0.35)",
  border:     palette.lineDark,
  overlay:    "rgba(0,0,0,0.65)",
  brand:      palette.gold,
  brandInk:   palette.ink,
  success:    "#5FB088",
  danger:     "#D0645A",
  scheme:     "dark" as const,
};

export type Theme = typeof light;

/** 4pt spacing grid — the ONLY spacing values used in the app. */
export const space = {
  xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48, huge: 64,
};

export const radius = {
  sm: 8, md: 14, lg: 20, xl: 28, pill: 999,
};

export const type = {
  // Editorial hierarchy — large & confident.
  display: { size: 56, line: 60, weight: "700" as const, tracking: -1.4 },
  hero:    { size: 40, line: 46, weight: "700" as const, tracking: -1.0 },
  title:   { size: 28, line: 34, weight: "700" as const, tracking: -0.5 },
  h2:      { size: 22, line: 28, weight: "600" as const, tracking: -0.2 },
  h3:      { size: 18, line: 24, weight: "600" as const, tracking: -0.1 },
  body:    { size: 16, line: 24, weight: "500" as const, tracking: 0 },
  meta:    { size: 13, line: 18, weight: "500" as const, tracking: 0.2 },
  caption: { size: 11, line: 14, weight: "600" as const, tracking: 0.6 },
};

export const motion = {
  fast:  180,
  base:  260,
  slow:  420,
  epic:  680,
  ease:  [0.16, 1, 0.3, 1] as const,   // OutExpo
  easeIn:  [0.7, 0, 0.84, 0] as const, // InExpo
};

export const shadow = {
  card: {
    shadowColor: palette.ink,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 24,
    elevation: 4,
  },
  float: {
    shadowColor: palette.ink,
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.12,
    shadowRadius: 32,
    elevation: 10,
  },
};
