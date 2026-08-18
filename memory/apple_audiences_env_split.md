# APPLE_AUDIENCES — Split by environment (structural safeguard)

Date : Juin 2026
Contexte : durcissement Apple Sign-In V1.

## Résumé

Il n'existe plus de variable statique `APPLE_AUDIENCES` à nettoyer manuellement avant un build de production. À la place, deux variables séparées sont utilisées, et le backend choisit automatiquement la bonne selon `APP_ENV` :

| Variable | Environnement | Contenu |
|---|---|---|
| `APPLE_AUDIENCES_PROD` | `APP_ENV=production` uniquement | Bundle iOS réel(s) uniquement. **`host.exp.Exponent` interdit → refus de démarrage** |
| `APPLE_AUDIENCES_DEV` | tout autre `APP_ENV` (dev, preview, staging) | Bundle iOS réel + `host.exp.Exponent` pour Expo Go |
| `APPLE_AUDIENCES` (legacy) | fallback en DEV uniquement, **ignoré en prod** | Conservé pour compat, refuse de satisfaire les exigences prod |

## Garanties structurelles

1. **Impossible d'exposer `host.exp.Exponent` en production** : le processus refuse de démarrer avec un message d'erreur explicite (`AppleAudiencesConfigError`).
2. **Impossible de démarrer en production sans avoir configuré `APPLE_AUDIENCES_PROD`** : idem, exit 1 au boot.
3. **La variable legacy `APPLE_AUDIENCES` est ignorée en prod**, même si elle reste dans le `.env` par erreur : elle ne peut pas satisfaire l'exigence.

## Où c'est validé

- Fonction : `routes/auth.py::_apple_audiences()` — lit `APP_ENV` puis résout la bonne source.
- Boot check : `routes/auth.py::verify_apple_audiences_config()` — appelée depuis `server.py` juste après `load_dotenv()`.
- Server bootstrap : `server.py:37-50` — `SystemExit` explicite si la config est invalide.
- Tests : `tests/test_apple_audiences_env_split.py` — 10 cas (incluant un boot integration test qui lance un subprocess Python avec une config prod poisoned et vérifie le exit code non-zéro + message d'erreur).

## À faire au moment de builder pour la production

1. Configurer `APP_ENV=production` sur l'environnement cible.
2. Configurer `APPLE_AUDIENCES_PROD="com.faqtotum.app"` (le bundle iOS réel, séparés par virgule si plusieurs targets).
3. Laisser `APPLE_AUDIENCES_DEV` en place — il n'est pas lu en prod.
4. Ne PAS définir `APPLE_AUDIENCES` (legacy). S'il est présent avec `host.exp.Exponent`, il est ignoré, mais autant nettoyer.

Si le build de prod démarre correctement, la config est saine. S'il refuse de démarrer, le message d'erreur indiquera exactement quoi corriger.
