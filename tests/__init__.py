"""Test package defaults: legacy suites exercise key mode; trusted mode is covered explicitly in tests/test_auth_trusted.py."""
import server.db as _db

_db.AUTH_MODE = "key"
