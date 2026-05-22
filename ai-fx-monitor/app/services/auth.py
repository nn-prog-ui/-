"""HTTP Basic認証サービス（Phase 64）"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

AUTH_USERNAME: str = os.getenv("AUTH_USERNAME", "")
AUTH_PASSWORD: str = os.getenv("AUTH_PASSWORD", "")
AUTH_ENABLED: bool = bool(AUTH_USERNAME and AUTH_PASSWORD)

# 認証不要なパス（Railway ヘルスチェック・静的ファイル）
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})
PUBLIC_PREFIXES: tuple[str, ...] = ("/static/",)


def parse_basic_auth(authorization: Optional[str]) -> Optional[tuple[str, str]]:
    """Authorization ヘッダーを (username, password) に分解する。"""
    if not authorization or not authorization.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(authorization[6:]).decode("utf-8")
        username, _, password = decoded.partition(":")
        return username, password
    except Exception:
        return None


def check_credentials(username: str, password: str) -> bool:
    """タイミング攻撃に耐性のある資格情報検証。"""
    correct_user = secrets.compare_digest(username.encode(), AUTH_USERNAME.encode())
    correct_pass = secrets.compare_digest(password.encode(), AUTH_PASSWORD.encode())
    return correct_user and correct_pass


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)
