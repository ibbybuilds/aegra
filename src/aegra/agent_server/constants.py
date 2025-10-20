from uuid import UUID

# Standard namespace UUID for deriving deterministic assistant IDs from graph IDs.
# IMPORTANT: Do not change after initial deploy unless you plan a data migration.
ASSISTANT_NAMESPACE_UUID = UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8")
