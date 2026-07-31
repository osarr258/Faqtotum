/**
 * Faqtotum Design System — Tokens
 * Minimalist Apple x Stripe inspired: pure black, pure white, light grey.
 * No decorative colours. Contrast, whitespace, typography do the work.
 * All tokens drive both light and dark modes. 4pt grid.
 */
export const palette = {
  // Neutrals — the entire brand lives here.
  ink:         "#000000",      // Pure black (primary text, primary brand)
  inkSoft:     "#1D1D1F",      // Apple charcoal (elevated dark surfaces)
  paper:       "#FFFFFF",      // Pure white
  paperAlt:    "#F5F5F7",      // Apple light grey (secondary surface)
  paperMuted:  "#FAFAFA",      // Ultra-light background
  grey:        "#86868B",      // Apple secondary label
  greyDeep:    "#6E6E73",      // Apple tertiary label
  greyLine:    "#D2D2D7",      // Apple separator
  line:        "rgba(0,0,0,0.08)",
  lineDark:    "rgba(255,255,255,0.10)",

  // Semantic — kept minimal and system-standard.
  success:     "#30D158",
  danger:      "#FF3B30",
  amber:       "#FF9F0A",

  // Legacy aliases — kept for backwards compatibility with older screens
  // that still reference `gold` / `goldSoft`. They now resolve to
  // minimalist neutrals so the visual identity remains consistent.
  gold:        "#86868B",      // was champagne — now medium grey
  goldSoft:    "#D2D2D7",      // was soft champagne — now light grey
};

export const light = {
  bg:         palette.paper,
  bgElevated: palette.paper,
  bgAlt:      palette.paperAlt,
  fg:         palette.ink,
  fgMuted:    "rgba(0,0,0,0.60)",
  fgSubtle:   "rgba(0,0,0,0.38)",
  border:     palette.line,
  overlay:    "rgba(0,0,0,0.55)",
  brand:      palette.ink,       // Primary brand = pure black
  brandInk:   palette.paper,
  success:    palette.success,
  danger:     palette.danger,
  scheme:     "light" as const,
};

export const dark = {
  bg:         palette.ink,
  bgElevated: "#1C1C1E",         // Apple dark elevated
  bgAlt:      "#2C2C2E",         // Apple dark secondary
  fg:         palette.paper,
  fgMuted:    "rgba(255,255,255,0.65)",
  fgSubtle:   "rgba(255,255,255,0.42)",
  border:     palette.lineDark,
  overlay:    "rgba(0,0,0,0.72)",
  brand:      palette.paper,     // Inverted on dark
  brandInk:   palette.ink,
  success:    "#32D74B",
  danger:     "#FF453A",
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
  // Editorial hierarchy — Apple-style: large, tight tracking, confident.
  display: { size: 56, line: 60, weight: "700" as const, tracking: -1.8 },
  hero:    { size: 40, line: 46, weight: "700" as const, tracking: -1.2 },
  title:   { size: 28, line: 34, weight: "700" as const, tracking: -0.6 },
  h2:      { size: 22, line: 28, weight: "600" as const, tracking: -0.3 },
  h3:      { size: 18, line: 24, weight: "600" as const, tracking: -0.2 },
  body:    { size: 16, line: 24, weight: "500" as const, tracking: 0 },
  meta:    { size: 13, line: 18, weight: "500" as const, tracking: 0.1 },
  caption: { size: 11, line: 14, weight: "600" as const, tracking: 1.2 },
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
    shadowOpacity: 0.10,
    shadowRadius: 32,
    elevation: 10,
  },
};
