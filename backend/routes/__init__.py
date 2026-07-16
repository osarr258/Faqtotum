"""Domain-oriented FastAPI routers.

Migration order (Sprint 14 Phase 1 — Strangler Pattern):
  1. auth      ✅
  2. security  ✅
  3. users
  4. artisans
  5. bookings + missions + interventions
  6. payments
  7. homes
  8. ai
  9. admin

All routers are mounted on the main api_router (prefix=/api).
"""
