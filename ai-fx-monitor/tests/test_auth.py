"""Phase 64: HTTP Basic認証テスト"""
from __future__ import annotations

import base64
import importlib
import os
import sys
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


# ---------------------------------------------------------------------------
# app.services.auth のユニットテスト
# ---------------------------------------------------------------------------

class TestParseBasicAuth:
    def test_valid_header(self):
        from app.services.auth import parse_basic_auth
        header = _basic_header("admin", "secret")
        result = parse_basic_auth(header)
        assert result == ("admin", "secret")

    def test_none_returns_none(self):
        from app.services.auth import parse_basic_auth
        assert parse_basic_auth(None) is None

    def test_empty_returns_none(self):
        from app.services.auth import parse_basic_auth
        assert parse_basic_auth("") is None

    def test_non_basic_scheme_returns_none(self):
        from app.services.auth import parse_basic_auth
        assert parse_basic_auth("Bearer tokenxyz") is None

    def test_password_with_colon(self):
        from app.services.auth import parse_basic_auth
        header = _basic_header("user", "pass:with:colons")
        result = parse_basic_auth(header)
        assert result == ("user", "pass:with:colons")

    def test_invalid_base64_returns_none(self):
        from app.services.auth import parse_basic_auth
        assert parse_basic_auth("Basic !!!notbase64!!!") is None


class TestCheckCredentials:
    def test_correct_credentials(self):
        with patch.dict(os.environ, {"AUTH_USERNAME": "admin", "AUTH_PASSWORD": "secret"}):
            import importlib
            import app.services.auth as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.check_credentials("admin", "secret") is True

    def test_wrong_password(self):
        with patch.dict(os.environ, {"AUTH_USERNAME": "admin", "AUTH_PASSWORD": "secret"}):
            import app.services.auth as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.check_credentials("admin", "wrong") is False

    def test_wrong_username(self):
        with patch.dict(os.environ, {"AUTH_USERNAME": "admin", "AUTH_PASSWORD": "secret"}):
            import app.services.auth as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.check_credentials("hacker", "secret") is False

    def test_empty_credentials(self):
        with patch.dict(os.environ, {"AUTH_USERNAME": "admin", "AUTH_PASSWORD": "secret"}):
            import app.services.auth as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.check_credentials("", "") is False


class TestIsPublicPath:
    def test_health_is_public(self):
        from app.services.auth import is_public_path
        assert is_public_path("/health") is True

    def test_static_is_public(self):
        from app.services.auth import is_public_path
        assert is_public_path("/static/style.css") is True

    def test_static_manifest_is_public(self):
        from app.services.auth import is_public_path
        assert is_public_path("/static/manifest.json") is True

    def test_root_is_not_public(self):
        from app.services.auth import is_public_path
        assert is_public_path("/") is False

    def test_dashboard_is_not_public(self):
        from app.services.auth import is_public_path
        assert is_public_path("/dashboard") is False

    def test_api_is_not_public(self):
        from app.services.auth import is_public_path
        assert is_public_path("/api/latest-signal") is False

    def test_partial_static_prefix_not_matched(self):
        from app.services.auth import is_public_path
        # "/staticXXX" は public でない
        assert is_public_path("/staticfiles/x") is False

    def test_health_prefix_not_matched(self):
        from app.services.auth import is_public_path
        # "/healthcheck" は public でない（完全一致のみ）
        assert is_public_path("/healthcheck") is False


# ---------------------------------------------------------------------------
# HTTP レベルの統合テスト（最小限のFastAPIアプリで実施）
# ---------------------------------------------------------------------------

def _make_minimal_app(username: str, password: str):
    """BasicAuthMiddleware のテスト用最小 FastAPI アプリを生成する。"""
    from fastapi import FastAPI
    from starlette.responses import Response
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest

    with patch.dict(os.environ, {"AUTH_USERNAME": username, "AUTH_PASSWORD": password}):
        import app.services.auth as auth_mod
        importlib.reload(auth_mod)

        class _BAuth(BaseHTTPMiddleware):
            async def dispatch(self, request: StarletteRequest, call_next):
                if not auth_mod.AUTH_ENABLED or auth_mod.is_public_path(request.url.path):
                    return await call_next(request)
                creds = auth_mod.parse_basic_auth(request.headers.get("Authorization"))
                if creds and auth_mod.check_credentials(*creds):
                    return await call_next(request)
                return Response(
                    content="Unauthorized",
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="test"'},
                )

        mini = FastAPI()
        mini.add_middleware(_BAuth)

        @mini.get("/health")
        def health():
            return {"status": "ok"}

        @mini.get("/")
        def root():
            return {"page": "index"}

        @mini.get("/dashboard")
        def dashboard():
            return {"page": "dashboard"}

        @mini.get("/api/latest-signal")
        def api_signal():
            return {"signal": "SKIP"}

        # 静的ファイルルートを模倣
        @mini.get("/static/style.css")
        def static_css():
            return Response(content="body{}", media_type="text/css")

    return mini


@pytest.fixture()
def auth_client():
    from fastapi.testclient import TestClient
    mini = _make_minimal_app("testuser", "testpass")
    with TestClient(mini, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture()
def noauth_client():
    from fastapi.testclient import TestClient
    mini = _make_minimal_app("", "")
    with TestClient(mini, raise_server_exceptions=False) as client:
        yield client


class TestAuthMiddlewareEnabled:
    def test_health_no_credentials_returns_200(self, auth_client):
        resp = auth_client.get("/health", auth=None)
        assert resp.status_code == 200

    def test_root_no_credentials_returns_401(self, auth_client):
        resp = auth_client.get("/", auth=None)
        assert resp.status_code == 401

    def test_root_wrong_credentials_returns_401(self, auth_client):
        resp = auth_client.get("/", auth=("bad", "creds"))
        assert resp.status_code == 401

    def test_root_correct_credentials_returns_200(self, auth_client):
        resp = auth_client.get("/", auth=("testuser", "testpass"))
        assert resp.status_code == 200

    def test_401_includes_www_authenticate_header(self, auth_client):
        resp = auth_client.get("/dashboard", auth=None)
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers
        assert "Basic" in resp.headers["WWW-Authenticate"]

    def test_api_endpoint_requires_auth(self, auth_client):
        resp = auth_client.get("/api/latest-signal", auth=None)
        assert resp.status_code == 401

    def test_api_endpoint_correct_credentials_returns_200(self, auth_client):
        resp = auth_client.get("/api/latest-signal", auth=("testuser", "testpass"))
        assert resp.status_code == 200

    def test_static_file_no_auth_returns_200(self, auth_client):
        resp = auth_client.get("/static/style.css", auth=None)
        assert resp.status_code == 200


class TestAuthMiddlewareDisabled:
    def test_root_without_env_returns_200(self, noauth_client):
        resp = noauth_client.get("/")
        assert resp.status_code == 200

    def test_health_without_env_returns_200(self, noauth_client):
        resp = noauth_client.get("/health")
        assert resp.status_code == 200

    def test_dashboard_without_env_returns_200(self, noauth_client):
        resp = noauth_client.get("/dashboard")
        assert resp.status_code == 200

    def test_api_without_env_returns_200(self, noauth_client):
        resp = noauth_client.get("/api/latest-signal")
        assert resp.status_code == 200
