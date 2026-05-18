"""tests/test_push.py — Phase 41: Web Push 通知テスト"""
import base64
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.db import init_db
from app.database.repository import (
    count_push_subscriptions,
    delete_push_subscription,
    get_or_create_vapid_keys,
    get_push_subscriptions,
    save_push_subscription,
)
from app.services.push_sender import generate_vapid_keys, make_vapid_jwt, send_push_notification


# ── フィクスチャ ─────────────────────────────────────────────
@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_push.db"
    init_db(db)
    return db


# ── VAPID 鍵生成 ─────────────────────────────────────────────
class TestGenerateVapidKeys:
    def test_returns_tuple(self):
        pub, priv = generate_vapid_keys()
        assert isinstance(pub, str)
        assert isinstance(priv, str)

    def test_public_key_is_base64url(self):
        pub, _ = generate_vapid_keys()
        # padding なしの base64url で65バイト（P-256 非圧縮ポイント）→約87文字
        decoded = base64.urlsafe_b64decode(pub + "==")
        assert len(decoded) == 65  # uncompressed P-256: 0x04 + 32 + 32

    def test_public_key_starts_with_04(self):
        pub, _ = generate_vapid_keys()
        decoded = base64.urlsafe_b64decode(pub + "==")
        assert decoded[0] == 0x04  # uncompressed point marker

    def test_private_key_is_pem(self):
        _, priv = generate_vapid_keys()
        assert "BEGIN" in priv
        assert "PRIVATE KEY" in priv

    def test_different_calls_produce_different_keys(self):
        pub1, _ = generate_vapid_keys()
        pub2, _ = generate_vapid_keys()
        assert pub1 != pub2


# ── VAPID JWT 生成 ────────────────────────────────────────────
class TestMakeVapidJwt:
    def test_returns_string(self):
        _, priv = generate_vapid_keys()
        token = make_vapid_jwt(priv, "https://fcm.googleapis.com")
        assert isinstance(token, str)

    def test_jwt_has_three_parts(self):
        _, priv = generate_vapid_keys()
        token = make_vapid_jwt(priv, "https://example.com")
        parts = token.split(".")
        assert len(parts) == 3

    def test_jwt_payload_has_required_claims(self):
        import json as _json
        _, priv = generate_vapid_keys()
        token = make_vapid_jwt(priv, "https://example.com")
        payload_b64 = token.split(".")[1]
        pad = "=" * (4 - len(payload_b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        assert "aud" in payload
        assert "exp" in payload
        assert "sub" in payload

    def test_jwt_audience_matches(self):
        import json as _json
        _, priv = generate_vapid_keys()
        audience = "https://push.example.com"
        token = make_vapid_jwt(priv, audience)
        payload_b64 = token.split(".")[1]
        pad = "=" * (4 - len(payload_b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        assert payload["aud"] == audience

    def test_jwt_expiry_is_future(self):
        import json as _json
        _, priv = generate_vapid_keys()
        token = make_vapid_jwt(priv, "https://example.com")
        payload_b64 = token.split(".")[1]
        pad = "=" * (4 - len(payload_b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        assert payload["exp"] > int(time.time())

    def test_jwt_header_alg_is_es256(self):
        import json as _json
        _, priv = generate_vapid_keys()
        token = make_vapid_jwt(priv, "https://example.com")
        header_b64 = token.split(".")[0]
        pad = "=" * (4 - len(header_b64) % 4)
        header = _json.loads(base64.urlsafe_b64decode(header_b64 + pad))
        assert header.get("alg") == "ES256"


# ── send_push_notification ────────────────────────────────────
class TestSendPushNotification:
    @pytest.mark.asyncio
    async def test_returns_true_on_202(self):
        pub, priv = generate_vapid_keys()
        mock_response = MagicMock()
        mock_response.status_code = 202

        with patch("app.services.push_sender.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await send_push_notification(
                "https://fcm.googleapis.com/fcm/send/test-endpoint",
                priv, pub,
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_400(self):
        pub, priv = generate_vapid_keys()
        mock_response = MagicMock()
        mock_response.status_code = 400

        with patch("app.services.push_sender.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await send_push_notification(
                "https://fcm.googleapis.com/fcm/send/test",
                priv, pub,
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_network_error(self):
        pub, priv = generate_vapid_keys()

        with patch("app.services.push_sender.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("network error")
            )
            result = await send_push_notification(
                "https://fcm.googleapis.com/fcm/send/test",
                priv, pub,
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_sends_vapid_authorization_header(self):
        pub, priv = generate_vapid_keys()
        captured_headers = {}
        mock_response = MagicMock()
        mock_response.status_code = 202

        async def mock_post(url, headers=None, **kwargs):
            captured_headers.update(headers or {})
            return mock_response

        with patch("app.services.push_sender.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = mock_post
            await send_push_notification(
                "https://fcm.googleapis.com/fcm/send/test",
                priv, pub,
            )
        assert "Authorization" in captured_headers
        assert captured_headers["Authorization"].startswith("vapid ")
        assert "TTL" in captured_headers


# ── push_subscriptions CRUD ───────────────────────────────────
class TestPushSubscriptionCrud:
    def test_save_returns_id(self, tmp_db):
        sub_id = save_push_subscription(
            "https://example.com/push/1", "p256dh_val", "auth_val", db_path=tmp_db
        )
        assert isinstance(sub_id, int)
        assert sub_id > 0

    def test_count_after_save(self, tmp_db):
        save_push_subscription("https://example.com/push/1", "k1", "a1", db_path=tmp_db)
        save_push_subscription("https://example.com/push/2", "k2", "a2", db_path=tmp_db)
        assert count_push_subscriptions(db_path=tmp_db) == 2

    def test_upsert_on_duplicate_endpoint(self, tmp_db):
        save_push_subscription("https://example.com/push/1", "k1", "a1", db_path=tmp_db)
        save_push_subscription("https://example.com/push/1", "k2", "a2", db_path=tmp_db)
        assert count_push_subscriptions(db_path=tmp_db) == 1

    def test_get_returns_all(self, tmp_db):
        for i in range(3):
            save_push_subscription(f"https://example.com/push/{i}", f"k{i}", f"a{i}", db_path=tmp_db)
        subs = get_push_subscriptions(db_path=tmp_db)
        assert len(subs) == 3

    def test_delete_returns_true(self, tmp_db):
        save_push_subscription("https://example.com/push/1", "k", "a", db_path=tmp_db)
        assert delete_push_subscription("https://example.com/push/1", db_path=tmp_db) is True

    def test_delete_removes_record(self, tmp_db):
        save_push_subscription("https://example.com/push/1", "k", "a", db_path=tmp_db)
        delete_push_subscription("https://example.com/push/1", db_path=tmp_db)
        assert count_push_subscriptions(db_path=tmp_db) == 0

    def test_delete_nonexistent_returns_false(self, tmp_db):
        assert delete_push_subscription("https://not-existing.com/push/99", db_path=tmp_db) is False


# ── get_or_create_vapid_keys ─────────────────────────────────
class TestGetOrCreateVapidKeys:
    def test_creates_new_keys(self, tmp_path):
        db = tmp_path / "vk_test.db"
        from app.database.db import init_db
        init_db(db)
        pub, priv = get_or_create_vapid_keys(db_path=db)
        assert pub
        assert priv

    def test_returns_same_keys_on_second_call(self, tmp_path):
        db = tmp_path / "vk_test.db"
        from app.database.db import init_db
        init_db(db)
        pub1, priv1 = get_or_create_vapid_keys(db_path=db)
        pub2, priv2 = get_or_create_vapid_keys(db_path=db)
        assert pub1 == pub2
        assert priv1 == priv2

    def test_public_key_is_valid_p256(self, tmp_path):
        db = tmp_path / "vk_test.db"
        from app.database.db import init_db
        init_db(db)
        pub, _ = get_or_create_vapid_keys(db_path=db)
        decoded = base64.urlsafe_b64decode(pub + "==")
        assert len(decoded) == 65
        assert decoded[0] == 0x04


# ── HTTP エンドポイント ────────────────────────────────────────
@pytest.mark.asyncio
async def test_vapid_public_key_endpoint():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/push/vapid-public-key")
    assert res.status_code == 200
    data = res.json()
    assert "publicKey" in data
    assert len(data["publicKey"]) > 20


@pytest.mark.asyncio
async def test_push_subscribe_ok():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/push/subscribe", json={
            "endpoint": "https://fcm.googleapis.com/fcm/test-sub-123",
            "keys": {"p256dh": "test_p256dh_value", "auth": "test_auth_value"},
        })
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_push_subscribe_missing_fields():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/push/subscribe", json={"endpoint": "https://example.com"})
    data = res.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_push_unsubscribe():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    endpoint = "https://fcm.googleapis.com/fcm/test-unsub-456"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/api/push/subscribe", json={
            "endpoint": endpoint,
            "keys": {"p256dh": "k1", "auth": "a1"},
        })
        res = await ac.post("/api/push/unsubscribe", json={"endpoint": endpoint})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_push_test_no_subscribers():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/push/test")
    assert res.status_code == 200
    # テスト DB に購読者がいなければ sent=0 か購読者0件メッセージ


# ── SW push ハンドラの記述確認 ────────────────────────────────
def test_sw_has_push_handler():
    from pathlib import Path
    sw = (Path(__file__).parent.parent / "app/web/static/sw.js").read_text()
    assert "addEventListener('push'" in sw


def test_sw_has_notificationclick_handler():
    from pathlib import Path
    sw = (Path(__file__).parent.parent / "app/web/static/sw.js").read_text()
    assert "notificationclick" in sw


def test_sw_shows_notification():
    from pathlib import Path
    sw = (Path(__file__).parent.parent / "app/web/static/sw.js").read_text()
    assert "showNotification" in sw


# ── 設定ページ確認 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_settings_page_has_push_ui():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/settings")
    assert res.status_code == 200
    assert "プッシュ通知" in res.text
    assert "push-enable-btn" in res.text
