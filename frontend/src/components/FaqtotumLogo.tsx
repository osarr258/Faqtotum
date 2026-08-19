/**
 * FaqtotumLogo — SVG du monogramme FAQTOTUM.
 *
 * Charte v1.0 (mai 2025) : trait arrondi épaisseur uniforme, boucle
 * fermée en haut, hampe verticale, crochet horizontal à mi-hauteur.
 *
 * Note : pour une fidélité pixel-perfect, remplacez ce SVG par le
 * fichier officiel fourni par le brand book. Ce composant reste un
 * substitut proche mais approximatif.
 */
import React from "react";
import Svg, { Circle, Path } from "react-native-svg";

type Props = {
  size?: number;
  color?: string;
};

export default function FaqtotumLogo({ size = 28, color = "#000000" }: Props) {
  // ViewBox carré 100x100, symbole centré, trait 10 (rond aux extrémités).
  // La boucle est offset légèrement en haut à droite, la hampe descend
  // depuis le bas de la boucle et le crochet part vers la gauche à
  // 65 % de la hauteur.
  const stroke = 10;
  return (
    <Svg width={size} height={size} viewBox="0 0 100 100" fill="none">
      <Circle
        cx={58}
        cy={30}
        r={22}
        stroke={color}
        strokeWidth={stroke}
        fill="none"
      />
      {/* Hampe : du bas de la boucle jusqu'au bas du symbole */}
      <Path
        d="M58 52 L 58 92"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
      />
      {/* Crochet horizontal à gauche */}
      <Path
        d="M18 66 L 58 66"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
      />
    </Svg>
  );
}
