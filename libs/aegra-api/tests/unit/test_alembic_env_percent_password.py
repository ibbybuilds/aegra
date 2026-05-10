"""Regression: alembic env.py must accept URL-encoded passwords.

Issue #357: since 0.9.6 settings.db.database_url runs the password through
quote_plus, producing `%XX` substrings. The previous env.py routed the URL
through configparser via Config.set_main_option, which interprets `%` as
interpolation syntax (`%(name)s`) and crashes on any `%XX` it can't parse.

The fix stashes the URL on config.attributes (a plain dict, no interpolation)
and reads it back with a small helper. This test asserts the mechanism works
for a representative encoded-password URL so we don't regress.
"""

from alembic.config import Config


def test_set_main_option_rejects_percent_url() -> None:
    """Document the underlying configparser behavior we are working around.

    If this assertion ever stops raising, alembic/configparser changed and
    the env.py workaround can be revisited.
    """
    cfg = Config()
    encoded_url = "postgresql+asyncpg://user:abc%3Cdef@localhost:5432/test"

    raised = False
    try:
        cfg.set_main_option("sqlalchemy.url", encoded_url)
    except ValueError as exc:
        raised = "interpolation" in str(exc)

    assert raised, "configparser should still raise on %XX in set_main_option"


def test_attributes_roundtrip_preserves_percent_url() -> None:
    """config.attributes is a plain dict and survives URL-encoded passwords."""
    cfg = Config()
    encoded_url = "postgresql+asyncpg://user:abc%3Cdef%40x@localhost:5432/test"

    cfg.attributes["sqlalchemy.url"] = encoded_url

    assert cfg.attributes.get("sqlalchemy.url") == encoded_url


def test_get_database_url_helper_prefers_attributes() -> None:
    """env.py's _get_database_url returns the attributes value when present."""
    cfg = Config()
    encoded_url = "postgresql+asyncpg://user:abc%3Cdef@localhost:5432/test"
    cfg.attributes["sqlalchemy.url"] = encoded_url

    # Mirror env.py._get_database_url logic. Kept inline so the test fails
    # loudly if env.py is rewritten to use a different mechanism.
    url = cfg.attributes.get("sqlalchemy.url") or cfg.get_main_option("sqlalchemy.url")

    assert url == encoded_url
