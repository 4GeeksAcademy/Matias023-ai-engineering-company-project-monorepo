"""Database configuration tests — DATABASE_URL resolution, production guard,
outbound row-lock structural check.

These tests use ``database`` module functions directly (no fixtures, no
TestClient) so they are both fast and isolated from TinyDB/auth setup.

.. note::
    The tests that monkeypatch ``os.environ`` (``test_*_env_*``) restore
    the previous value of the variables they touch so they don't leak.
"""

import os

import pytest

from database import reset_engine_for_tests


# ============================================================
# Helpers
# ============================================================


def _setenv(**kwargs):
    """Contextual env-var setter — yields, then restores originals."""
    originals = {}
    for k, v in kwargs.items():
        originals[k] = os.environ.get(k)
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in originals.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


# ============================================================
# get_engine / init_db: DATABASE_URL resolved at call time
# ============================================================


class TestDatabaseUrlResolution:
    """Verify DATABASE_URL is read lazily (at engine-build time)."""

    def test_resolve_no_env_no_default_fallback(self):
        """No DATABASE_URL, no APP_ENV, no default -> local SQLite fallback."""
        reset_engine_for_tests()
        for _ in _setenv(DATABASE_URL="", APP_ENV=""):
            from database import get_engine

            engine = get_engine()
            assert str(engine.url) == "sqlite://" or str(engine.url).startswith(
                "sqlite"
            )

    def test_resolve_default_sqlite(self):
        """Explicit sqlite_default parameter is used when DATABASE_URL absent."""
        reset_engine_for_tests()
        for _ in _setenv(DATABASE_URL=""):
            from database import get_engine

            engine = get_engine(sqlite_default="sqlite:///:memory:")
            assert str(engine.url) == "sqlite:///:memory:"
            break  # generator only iterates once

    def test_resolve_env_takes_precedence(self):
        """DATABASE_URL env var overrides sqlite_default."""
        reset_engine_for_tests()
        for _ in _setenv(DATABASE_URL="sqlite:///from-env.db"):
            from database import get_engine

            engine = get_engine(sqlite_default="sqlite:///:memory:")
            assert str(engine.url) == "sqlite:///from-env.db"

    def test_resolve_cached_until_url_changes(self):
        """get_engine caches; a new URL replaces the cached engine."""
        reset_engine_for_tests()
        for _ in _setenv(DATABASE_URL="", APP_ENV=""):
            import database

            e1 = database.get_engine()
            url1 = str(e1.url)

            # Change DATABASE_URL on the second call — must rebuild
            os.environ["DATABASE_URL"] = "sqlite:///rebuilt.db"
            e2 = database.get_engine()
            assert str(e2.url) != url1 or "rebuilt" in str(e2.url)


# ============================================================
# Production guard: APP_ENV=production + no DATABASE_URL
# ============================================================


class TestProductionGuard:
    """Verify that missing DATABASE_URL in production raises."""

    def test_production_raises_without_database_url(self):
        """APP_ENV=production and no DATABASE_URL -> RuntimeError."""
        reset_engine_for_tests()
        for _ in _setenv(DATABASE_URL="", APP_ENV="production"):
            from database import _resolve_engine_url

            with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
                _resolve_engine_url()

    def test_production_ok_with_database_url(self):
        """APP_ENV=production with DATABASE_URL -> no error."""
        reset_engine_for_tests()
        for _ in _setenv(
            DATABASE_URL="sqlite:///prod.db", APP_ENV="production"
        ):
            from database import _resolve_engine_url

            url = _resolve_engine_url()
            assert str(url) == "sqlite:///prod.db"

    def test_production_fallback_allowed_via_allow_flag(self):
        """APP_ENV=production without DATABASE_URL but ALLOW_SQLITE_FALLBACK=1
        -> SQLite fallback (operator opted in)."""
        reset_engine_for_tests()
        for _ in _setenv(
            DATABASE_URL="",
            APP_ENV="production",
            ALLOW_SQLITE_FALLBACK="1",
        ):
            from database import _resolve_engine_url

            url = _resolve_engine_url()
            assert url == "sqlite://"

    def test_production_fallback_true_values(self):
        """ALLOW_SQLITE_FALLBACK=yes/true/on also work."""
        for val in ("yes", "true", "on"):
            reset_engine_for_tests()
            for _ in _setenv(
                DATABASE_URL="",
                APP_ENV="production",
                ALLOW_SQLITE_FALLBACK=val,
            ):
                from database import _resolve_engine_url

                url = _resolve_engine_url()
                assert url == "sqlite://", f"flag value '{val}' should allow"

    def test_development_env_still_falls_back(self):
        """APP_ENV=development (or unset) without DATABASE_URL -> fallback."""
        reset_engine_for_tests()
        for _ in _setenv(DATABASE_URL="", APP_ENV="development"):
            from database import _resolve_engine_url

            url = _resolve_engine_url()
            assert url == "sqlite://"  # no raise


# ============================================================
# Structural check: row-lock in outbound handler
# ============================================================


class TestOutboundRowLockStructure:
    """Verify the outbound route uses ``with_for_update()``."""

    def test_with_for_update_present(self):
        """create_outbound_order calls _get_sku_for_update_or_404 which
        internally uses .with_for_update()."""
        import ast
        import pathlib

        router_path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "routers"
            / "inventory.py"
        )
        with open(router_path) as f:
            tree = ast.parse(f.read())

        # Walk the AST for the function definition
        outbound_func = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "create_outbound_order"
            ),
            None,
        )
        assert outbound_func is not None, (
            "create_outbound_order function not found"
        )

        source_lines = router_path.read_text().splitlines()
        func_start = outbound_func.lineno - 1  # 0-indexed
        func_end = outbound_func.end_lineno or func_start
        body = "\n".join(source_lines[func_start:func_end])

        # The outbound function delegates to the helper; verify the helper
        # (which IS inside the same file) has .with_for_update().
        helper = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "_get_sku_for_update_or_404"
            ),
            None,
        )
        assert helper is not None, (
            "_get_sku_for_update_or_404 helper not found"
        )
        helper_start = helper.lineno - 1
        helper_end = helper.end_lineno or helper_start
        helper_body = "\n".join(source_lines[helper_start:helper_end])

        assert ".with_for_update()" in helper_body, (
            "_get_sku_for_update_or_404 must use SELECT ... FOR UPDATE "
            "(.with_for_update()) on the SKU query."
        )

        assert "_get_sku_for_update_or_404" in body, (
            "Expected create_outbound_order to call "
            "_get_sku_for_update_or_404 (not _get_sku_or_404) "
            "to acquire a row-level lock before computing stock."
        )

        # Also verify _get_sku_or_404 does NOT appear in the outbound body
        assert "_get_sku_or_404(" not in body, (
            "create_outbound_order should use _get_sku_for_update_or_404 "
            "instead of the non-locking _get_sku_or_404."
        )

    def test_sku_for_update_helper_exists(self):
        """_get_sku_for_update_or_404 helper is defined."""
        import ast
        import pathlib

        router_path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "routers"
            / "inventory.py"
        )
        with open(router_path) as f:
            tree = ast.parse(f.read())

        helper = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "_get_sku_for_update_or_404"
            ),
            None,
        )
        assert helper is not None, (
            "_get_sku_for_update_or_404 helper is not defined in inventory.py"
        )


# ============================================================
# Transaction rollback in write routes
# ============================================================


class TestTransactionRollbackStructure:
    """Verify write routes have try/except rollback."""

    WRITE_FUNCTIONS = [
        "create_product",
        "create_inbound_order",
        "create_outbound_order",
    ]

    def test_each_write_route_has_rollback(self):
        """Every write route catches SQLAlchemyError and calls rollback()."""
        import ast
        import pathlib

        router_path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "routers"
            / "inventory.py"
        )
        with open(router_path) as f:
            tree = ast.parse(f.read())

        funcs = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name in self.WRITE_FUNCTIONS
        }

        for name in self.WRITE_FUNCTIONS:
            func = funcs.get(name)
            assert func is not None, (
                f"{name} function not found in inventory.py"
            )

            source_lines = router_path.read_text().splitlines()
            func_start = func.lineno - 1
            func_end = func.end_lineno or func_start
            body = "\n".join(source_lines[func_start:func_end])

            assert "session.rollback()" in body, (
                f"{name} is missing exception handling with session.rollback(). "
                "Wrap the session.commit() call in a try/except SQLAlchemyError "
                "block that calls rollback before re-raising."
            )

            assert "except SQLAlchemyError" in body, (
                f"{name} should catch 'except SQLAlchemyError' around commit. "
            )
