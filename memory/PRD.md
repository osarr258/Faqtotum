# ProConnect — PRD

## Problem Statement (original, FR)
Application de mise en relation à la Uber/Airbnb connectant les clients (particuliers/pros) aux artisans des métiers manuels (plombier, chauffagiste, climaticien, peintre, serrurier, etc.). Les clients sélectionnent et réservent un artisan ; les sociétés/artisans paient l'accès pour être référencés. Interface fluide et intuitive façon Revolut.

## User choices
- MVP: les deux côtés (client + artisan)
- Auth: Email/mot de passe (JWT) + Google (Emergent)
- Paiement abonnement: SIMULÉ pour l'instant
- Mise en relation: le client réserve directement un créneau
- Design: au choix de l'agent (graphite/blanc fintech, Plus Jakarta Sans)

## Personas
- Client: cherche un artisan par métier/ville, consulte profils, réserve un créneau, suit ses réservations.
- Artisan/Pro: crée son profil, s'abonne pour être référencé, gère les demandes (accepter/refuser/terminer).

## Architecture
- Backend FastAPI (/api), MongoDB (motor). Auth par session_token Bearer (7j), bcrypt pour mots de passe.
- Collections: users, user_sessions, artisan_profiles, bookings.
- Frontend Expo Router. AuthContext. Thème /src/theme. Composants /src/components/ui.
- Tabs client: Accueil, Réservations, Profil. Tabs artisan: Tableau de bord, Mon profil, Abonnement.

## Implemented (2026-06-30)
### Phase 3 — AI-first premium pivot (latest)
- Refonte design complète: thème premium DARK + accents OR CHAMPAGNE (Revolut/Apple), Plus Jakarta Sans.
- Bouton "J'ai un problème" + écran Diagnostic IA: texte + photos (expo-image-picker) + voix (expo-audio → Whisper /ai/transcribe). GPT-4o vision (/ai/diagnose) → problème, métier, urgence, durée, fourchette de prix, matériel, score de confiance, conseil sécurité.
- Matching IA automatique (/missions): scoring (note, Trust Score, acceptation, réponse, distance) → propose LE meilleur pro; refuser → pro suivant.
- Mission flow: confirmer → suivi GPS/ETA temps réel simulé (/missions/{id}) avec carte (react-native-maps natif + fallback web) + compte à rebours + bouton terminer.
- Trust Score par artisan; IA via clé universelle Emergent (GPT-4o + Whisper).

### Phase 1 & 2
- Auth email/password + Google (Emergent), rôles client/artisan.
- Catégories de métiers (12), 12 artisans seedés.
- Client: home (recherche + grille catégories + top artisans), liste/recherche artisans, fiche artisan + réservation créneau, mes réservations.
- Artisan: dashboard (métriques + accept/refuse/terminer), édition profil pro, abonnement Premium (paiement simulé).

## Backlog
- P1: Messagerie client↔artisan, avis/notes réels après mission, vraie intégration Stripe.
- P1: Filtres avancés (prix, dispo), géolocalisation/carte.
- P2: Notifications, upload photo profil/portfolio, historique gains artisan.

## Next tasks
- Stripe Connect (paiement + escrow + commission) — phase suivante.
- Rôles Admin/Support/Finance/Modération + dashboard admin (carte temps réel, litiges, stats, monitoring IA).
- Acceptation réelle des missions côté artisan + notifications push.
- Home Digital Passport (historique entretien, garanties, équipements).
- GPS réel (artisan en mouvement), mode Urgence multi-pros simultané.
