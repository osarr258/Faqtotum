/**
 * FaqtotumLogo — SVG inline du symbole "P à crochet".
 *
 * Charte FAQTOTUM : trait arrondi épaisseur uniforme, noir sur blanc
 * (ou l'inverse). Le symbole s'inspire du logo officiel v1.0 (mai 2025).
 */
import React from "react";
import Svg, { Path } from "react-native-svg";

type Props = {
  size?: number;
  color?: string;
};

export default function FaqtotumLogo({ size = 28, color = "#000000" }: Props) {
  // ViewBox 64 x 80 pour respecter les proportions du "P à crochet"
  // (boucle en haut, hampe verticale, barre horizontale à mi-hauteur).
  return (
    <Svg width={size} height={size * (80 / 64)} viewBox="0 0 64 80" fill="none">
      {/* Boucle circulaire supérieure (P) */}
      <Path
        d="M22 6 C 12 6, 6 14, 6 22 C 6 30, 12 38, 22 38 C 32 38, 38 30, 38 22 C 38 14, 32 6, 22 6 Z"
        stroke={color}
        strokeWidth={7}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Hampe verticale descendant sous la boucle */}
      <Path
        d="M22 38 L 22 74"
        stroke={color}
        strokeWidth={7}
        strokeLinecap="round"
      />
      {/* Barre horizontale à mi-hampe (le crochet) */}
      <Path
        d="M4 52 L 22 52"
        stroke={color}
        strokeWidth={7}
        strokeLinecap="round"
      />
    </Svg>
  );
}
