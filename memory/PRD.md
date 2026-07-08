# ProConnect / Auxora — PRD

## Problem Statement (original, FR)
Application de mise en relation à la Uber/Airbnb connectant les clients (particuliers/pros) aux artisans des métiers manuels (plombier, chauffagiste, climaticien, peintre, serrurier, etc.). Les clients sélectionnent et réservent un artisan ; les sociétés/artisans paient l'accès pour être référencés. Interface fluide et intuitive façon Revolut.

**Pivot 2026-07** : passage du modèle marketplace pur au modèle **Home Operating System** — l'utilisateur revient chaque mois, pas seulement quand il a un problème.

## User choices
- MVP: les deux côtés (client + artisan)
- Auth: Email/mot de passe (JWT) + Google (Emergent)
- Paiement abonnement: SIMULÉ pour l'instant
- Mise en relation: le client réserve directement un créneau
- Design: dark premium + or champagne, Plus Jakarta Sans (inchangé après pivot)

## Personas
- Client: cherche un artisan, réserve, suit ses interventions, **gère ses biens et équipements**.
- Artisan/Pro: crée son profil, s'abonne pour être référencé, gère les demandes.

## Architecture
- Backend FastAPI (/api), MongoDB (motor). Bearer session_token (7j), bcrypt.
- 58 endpoints. Collections: users, user_sessions, artisan_profiles, bookings, conversations, missions, invoices, guarantees, home_passport, **properties, property_equipment, property_documents, property_reminders**.
- Frontend Expo Router. AuthContext. Thème /src/theme.
- Tabs client (5): Accueil, **Ma Maison**, Réservations, Messages, Profil.
- Tabs artisan: Tableau de bord, Mon profil, Abonnement.

## Implemented (2026-07 — Sprint My Home)
### Ma Maison — Home Operating System (NOUVEAU)
- **Multi-biens** : 5 types (apartment, house, office, commercial, vacation). Photos base64, adresse, surface, année, notes.
- **Property Dashboard** : hero image + gradient scrim, quick actions (Équipements/Documents/Timeline/Rappels), carte insights santé %, entretiens à venir, équipements récents, cartes IA "Bientôt disponible".
- **Équipements** : 14 catégories (chaudière, chauffe-eau, PAC, tableau élec, clim, VMC, toit, fenêtres, portes, détecteurs, solaire, borne VE, adoucisseur, autre). Marque, modèle, N° série, installateur, dates installation/garantie, statut (ok/attention/maintenance/replace), notes, photos, documents liés.
- **Documents (Passeport numérique)** : 8 catégories (factures, garanties, manuels, certificats, plans, photos, rapports, autres). Filtres par catégorie.
- **Timeline agrégée** : équipements installés + documents ajoutés + interventions (bookings.property_id) + rappels terminés, groupés par année.
- **Insights** : équipements OK / à surveiller, documents, upcoming maintenance, interventions, argent investi, santé moyenne %. Valeurs de démo réalistes quand vide.
- **Rappels** : architecture prête (upcoming/due/done/snoozed), suggestions rapides, fréquences (once/monthly/quarterly/biannual/yearly). Pas de notifs (à venir).
- **IA placeholders** : 6 cartes "Bientôt disponible" (Santé équipements, Maintenance prédictive, Détection risques, Optimisation énergétique, Expiration garanties, Inspection recommandée).
- **Sécurité** : toutes les routes /properties requièrent Bearer, 401/404 propres.

### Phase 4 — Couche d'intelligence backend (architecte IA)
- Moteur de matching pondéré `services/matching.py`: score 0-100 + `match_reasons` FR — affichés sur écran matching.
- Mode Urgence: broadcast top 5 pros, premier qui accepte gagne.
- Architecture sync calendrier MOCKÉE `services/calendar_sync.py`.
- Modèles: complete_mission génère facture + garantie 12 mois + entrée Home Passport.

### Phase 3 — AI-first premium pivot
- Design premium DARK + accents OR CHAMPAGNE, Plus Jakarta Sans.
- Bouton "J'ai un problème" + écran Diagnostic IA (texte + photos + voix via Whisper).
- Matching IA automatique, Trust Score par artisan, clé universelle Emergent (GPT-4o + Whisper).

### Phase 1 & 2
- Auth email/password + Google (Emergent), rôles client/artisan.
- 12 catégories, 12 artisans seedés.
- Client: home, liste/recherche artisans, fiche + réservation créneau, mes réservations.
- Artisan: dashboard, édition profil, abonnement Premium simulé.

## Backlog
- P1: Lier bookings/interventions à property_id via l'UI (déjà supporté côté schema).
- P1: Upload documents réels (base64 file), stockage S3.
- P1: Vraie intégration Stripe Connect (paiement + escrow + commission).
- P1: Messagerie temps réel (WebSocket), avis réels après mission.
- P2: Réelle IA sur les 6 cartes "Bientôt" (santé, maintenance prédictive, risques…).
- P2: Notifications réelles sur rappels d'entretien (push).
- P2: Dashboard admin, GPS artisan réel, mode Urgence multi-pros polish.

## Next tasks
- Attacher les interventions du diagnostic IA à un bien sélectionné.
- Rendre 3 des 6 cartes IA fonctionnelles (santé équipement calculé, expiration garanties, inspection recommandée).
- Notifications push sur rappels.
