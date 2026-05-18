"""Phase 41: Web Push 通知サービス。

VAPID (Voluntary Application Server Identification) 認証を使い、
ブラウザの Push Service に空ペイロードの通知を送信する。

ペイロード暗号化が必要な場合は pywebpush ライブラリの導入を推奨。
本実装は空ペイロード（Trigger-only）push を使用する。
Service Worker が push イベントを受け取ったあと固定テキストを表示する。
"""
from __future__ import annotations

import base64
import logging
import time
from urllib.parse import urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key

logger = logging.getLogger(__name__)

VAPID_SUB = "mailto:admin@localhost"


def generate_vapid_keys() -> tuple[str, str]:
    """EC P-256 VAPID 鍵ペアを生成して (public_b64url, private_pem) で返す。"""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pub_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64url = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return pub_b64url, priv_pem


def make_vapid_jwt(private_key_pem: str, audience: str) -> str:
    """VAPID 認証用の ES256 JWT を生成する。"""
    private_key = load_pem_private_key(private_key_pem.encode(), password=None)
    payload = {
        "aud": audience,
        "exp": int(time.time()) + 12 * 3600,
        "sub": VAPID_SUB,
    }
    return jwt.encode(payload, private_key, algorithm="ES256")


async def send_push_notification(
    endpoint: str,
    private_key_pem: str,
    public_key_b64url: str,
    ttl: int = 86400,
) -> bool:
    """ブラウザの Push Service へ空ペイロードの通知を送信する。

    Returns:
        True: 送信成功（202 Accepted など）
        False: 失敗またはネットワークエラー
    """
    parsed = urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    token = make_vapid_jwt(private_key_pem, audience)
    headers = {
        "Authorization": f"vapid t={token},k={public_key_b64url}",
        "TTL": str(ttl),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(endpoint, headers=headers)
        if res.status_code in (200, 201, 202):
            return True
        logger.warning("Push send failed: status=%d endpoint=%.60s", res.status_code, endpoint)
        return False
    except Exception as exc:
        logger.warning("Push send error: %s endpoint=%.60s", exc, endpoint)
        return False


async def send_push_to_all(db_path=None) -> dict:
    """DB の全購読者にプッシュ通知を送り、集計結果を返す。

    Returns:
        {"sent": int, "failed": int, "removed": int}
    """
    from app.database.repository import (
        delete_push_subscription,
        get_or_create_vapid_keys,
        get_push_subscriptions,
    )

    pub, priv = get_or_create_vapid_keys(db_path=db_path)
    subs = get_push_subscriptions(db_path=db_path)
    sent = failed = removed = 0

    for sub in subs:
        ok = await send_push_notification(sub["endpoint"], priv, pub)
        if ok:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "removed": removed}
