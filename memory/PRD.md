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
- Auth email/password + Google (Emergent), rôles client/artisan.
- Catégories de métiers (12), 12 artisans seedés.
- Client: home (recherche + grille catégories + top artisans), liste/recherche artisans, fiche artisan + réservation créneau, mes réservations.
- Artisan: dashboard (métriques + accept/refuse/terminer), édition profil pro, abonnement Premium (paiement simulé).

## Backlog
- P1: Messagerie client↔artisan, avis/notes réels après mission, vraie intégration Stripe.
- P1: Filtres avancés (prix, dispo), géolocalisation/carte.
- P2: Notifications, upload photo profil/portfolio, historique gains artisan.

## Next tasks
- Brancher un vrai paiement (Stripe) pour l'abonnement artisan.
- Système d'avis et de messagerie.
