"""OrderHub CRM — Module-level constants.

Stable identifiers and values referenced from multiple modules. Kept here
to avoid circular imports and to give them a single source of truth.
"""

import uuid

# SEC-04 — Persistent system user used as the actor for audit rows produced
# by webhooks (Shopify) and the background scheduler. Inserted by the
# alembic migration a1b2c3d4e5f6_add_persistent_system_user. The row is
# is_active=False with an unusable password hash, so no one can log in as
# it. Do NOT change this UUID without a data migration that updates every
# referencing order_status_history row.
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
