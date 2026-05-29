"""Phase 76: Railway デプロイ対応 テスト"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


# ── Dockerfile・.dockerignore 存在確認 ────────────────────────────────────

def _root() -> Path:
    return Path(__file__).parent.parent


class TestDeployFiles:
    def test_dockerfile_exists(self):
        """Dockerfile が存在する"""
        assert (_root() / "Dockerfile").exists()

    def test_dockerignore_exists(self):
        """.dockerignore が存在する"""
        assert (_root() / ".dockerignore").exists()

    def test_railway_toml_exists(self):
        """railway.toml が存在する"""
        assert (_root() / "railway.toml").exists()

    def test_deploy_md_exists(self):
        """DEPLOY.md が存在する"""
        assert (_root() / "DEPLOY.md").exists()

    def test_dockerfile_uses_python311(self):
        """Dockerfile が python:3.11 ベースイメージを使用している"""
        content = (_root() / "Dockerfile").read_text(encoding="utf-8")
        assert "python:3.11" in content

    def test_dockerfile_workdir_app(self):
        """Dockerfile の作業ディレクトリが /app"""
        content = (_root() / "Dockerfile").read_text(encoding="utf-8")
        assert "WORKDIR /app" in content

    def test_dockerfile_volume_data(self):
        """Dockerfile に /app/data ボリューム定義がある"""
        content = (_root() / "Dockerfile").read_text(encoding="utf-8")
        assert "/app/data" in content

    def test_dockerfile_trading_mode_env(self):
        """Dockerfile で TRADING_MODE=demo_only が設定されている"""
        content = (_root() / "Dockerfile").read_text(encoding="utf-8")
        assert "TRADING_MODE=demo_only" in content

    def test_dockerfile_no_live_trading(self):
        """Dockerfile に live 注文機能を示すコードがない"""
        content = (_root() / "Dockerfile").read_text(encoding="utf-8")
        assert "live_order" not in content.lower()
        assert "TRADING_MODE=live" not in content

    def test_dockerignore_excludes_env(self):
        """.dockerignore が .env ファイルを除外している"""
        content = (_root() / ".dockerignore").read_text(encoding="utf-8")
        assert ".env" in content

    def test_dockerignore_excludes_db(self):
        """.dockerignore が .db ファイルを除外している"""
        content = (_root() / ".dockerignore").read_text(encoding="utf-8")
        assert ".db" in content

    def test_railway_toml_uses_dockerfile(self):
        """railway.toml が DOCKERFILE ビルダーを指定している"""
        content = (_root() / "railway.toml").read_text(encoding="utf-8")
        assert "DOCKERFILE" in content

    def test_railway_toml_health_check(self):
        """railway.toml にヘルスチェックパスが設定されている"""
        content = (_root() / "railway.toml").read_text(encoding="utf-8")
        assert "healthcheckPath" in content
        assert "/health" in content

    def test_railway_toml_restart_policy(self):
        """railway.toml にリスタートポリシーが設定されている"""
        content = (_root() / "railway.toml").read_text(encoding="utf-8")
        assert "restartPolicyType" in content


# ── startup_check.py テスト ───────────────────────────────────────────────

class TestEnsureDirectories:
    def test_creates_data_dir(self, tmp_path):
        from app.scripts.startup_check import ensure_directories
        ensure_directories(tmp_path)
        assert (tmp_path / "data").is_dir()
        assert (tmp_path / "data" / "raw").is_dir()
        assert (tmp_path / "data" / "processed").is_dir()

    def test_idempotent(self, tmp_path):
        """2回呼んでもエラーにならない"""
        from app.scripts.startup_check import ensure_directories
        ensure_directories(tmp_path)
        ensure_directories(tmp_path)  # 2回目もエラーなし
        assert (tmp_path / "data" / "raw").is_dir()


class TestCheckSafetyEnv:
    def test_demo_only_no_warnings(self):
        from app.scripts.startup_check import check_safety_env
        with patch.dict(os.environ, {"TRADING_MODE": "demo_only"}, clear=False):
            warnings = check_safety_env()
        mode_warnings = [w for w in warnings if "TRADING_MODE" in w]
        assert mode_warnings == []

    def test_non_demo_mode_triggers_warning(self):
        from app.scripts.startup_check import check_safety_env
        with patch.dict(os.environ, {"TRADING_MODE": "live"}, clear=False):
            warnings = check_safety_env()
        assert any("TRADING_MODE" in w for w in warnings)

    def test_oanda_live_env_triggers_warning(self):
        from app.scripts.startup_check import check_safety_env
        with patch.dict(os.environ, {"OANDA_ENVIRONMENT": "live"}, clear=False):
            warnings = check_safety_env()
        assert any("OANDA_ENVIRONMENT" in w for w in warnings)

    def test_production_without_auth_triggers_warning(self):
        from app.scripts.startup_check import check_safety_env
        env = {"APP_ENV": "production", "AUTH_USERNAME": "", "AUTH_PASSWORD": ""}
        with patch.dict(os.environ, env, clear=False):
            warnings = check_safety_env()
        assert any("AUTH" in w for w in warnings)

    def test_production_with_auth_no_auth_warning(self):
        from app.scripts.startup_check import check_safety_env
        env = {
            "APP_ENV": "production",
            "AUTH_USERNAME": "admin",
            "AUTH_PASSWORD": "s3cure",
            "TRADING_MODE": "demo_only",
            "OANDA_ENVIRONMENT": "practice",
        }
        with patch.dict(os.environ, env, clear=False):
            warnings = check_safety_env()
        auth_warnings = [w for w in warnings if "AUTH" in w]
        assert auth_warnings == []


class TestEnsureCsvData:
    def test_generates_dummy_when_missing(self, tmp_path):
        from app.scripts.startup_check import ensure_directories, ensure_csv_data
        ensure_directories(tmp_path)
        results = ensure_csv_data(tmp_path)
        # 少なくとも1ペアは生成されたか、既存だったか
        assert isinstance(results, dict)
        assert len(results) > 0

    def test_no_generation_when_exists(self, tmp_path):
        from app.scripts.startup_check import ensure_directories, ensure_csv_data
        ensure_directories(tmp_path)
        # ダミーファイルを先に作成
        raw = tmp_path / "data" / "raw"
        from app.config import SYMBOL_CSV_MAP
        for csv_file in SYMBOL_CSV_MAP.values():
            (raw / csv_file).write_text("dummy\n" * 100)
        results = ensure_csv_data(tmp_path)
        # 既存ファイルがある場合は生成しない（False が返る）
        assert all(not generated for generated in results.values())


class TestRunStartupChecks:
    def test_returns_dict(self, tmp_path):
        from app.scripts.startup_check import run_startup_checks
        result = run_startup_checks(tmp_path)
        assert isinstance(result, dict)

    def test_has_trading_mode_key(self, tmp_path):
        from app.scripts.startup_check import run_startup_checks
        result = run_startup_checks(tmp_path)
        assert "trading_mode" in result

    def test_trading_mode_is_demo_only(self, tmp_path):
        from app.scripts.startup_check import run_startup_checks
        with patch.dict(os.environ, {"TRADING_MODE": "demo_only"}, clear=False):
            result = run_startup_checks(tmp_path)
        assert result["trading_mode"] == "demo_only"

    def test_has_safety_warnings_key(self, tmp_path):
        from app.scripts.startup_check import run_startup_checks
        result = run_startup_checks(tmp_path)
        assert "safety_warnings" in result


# ── /health エンドポイント ルース確認（ソース直読み） ─────────────────────

def _health_src() -> str:
    src = (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")
    start = src.find("async def health_check():")
    end = src.find("\n@router", start + 1)
    return src[start:end] if end != -1 else src[start:]


class TestHealthEndpoint:
    def test_health_returns_db_status(self):
        """health エンドポイントが DB ステータスを返す"""
        assert '"db"' in _health_src() or "'db'" in _health_src() or "db_ok" in _health_src()

    def test_health_returns_trading_mode(self):
        """health エンドポイントが trading_mode を返す"""
        assert "trading_mode" in _health_src()

    def test_health_returns_app_env(self):
        """health エンドポイントが app_env を返す"""
        assert "app_env" in _health_src()

    def test_health_returns_csv_status(self):
        """health エンドポイントが CSV データ存在状況を返す"""
        assert "csv" in _health_src()

    def test_health_returns_version(self):
        """health エンドポイントがバージョンを返す"""
        assert "version" in _health_src()

    def test_health_503_on_db_error(self):
        """DB 接続失敗時に 503 を返す設計になっている"""
        assert "503" in _health_src()

    def test_health_phase76_comment(self):
        """Phase 76 のコメントが含まれる"""
        assert "Phase 76" in _health_src()
