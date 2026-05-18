"""tests/test_pwa.py — Phase 40: PWA対応テスト"""
import json
import struct
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).parent.parent / "app/web/static"
TEMPLATES_DIR = Path(__file__).parent.parent / "app/web/templates"


# ── ファイル存在確認 ──────────────────────────────────────────
class TestPWAFiles:
    def test_manifest_exists(self):
        assert (STATIC_DIR / "manifest.json").exists()

    def test_sw_exists(self):
        assert (STATIC_DIR / "sw.js").exists()

    def test_icon_192_exists(self):
        assert (STATIC_DIR / "icons" / "icon-192.png").exists()

    def test_icon_512_exists(self):
        assert (STATIC_DIR / "icons" / "icon-512.png").exists()


# ── manifest.json バリデーション ─────────────────────────────
class TestManifest:
    @pytest.fixture(autouse=True)
    def load_manifest(self):
        self.manifest = json.loads((STATIC_DIR / "manifest.json").read_text())

    def test_name_present(self):
        assert "name" in self.manifest
        assert len(self.manifest["name"]) > 0

    def test_short_name_present(self):
        assert "short_name" in self.manifest

    def test_start_url_is_root(self):
        assert self.manifest.get("start_url") == "/"

    def test_display_standalone(self):
        assert self.manifest.get("display") == "standalone"

    def test_background_color_present(self):
        assert "background_color" in self.manifest

    def test_theme_color_present(self):
        assert "theme_color" in self.manifest

    def test_icons_present(self):
        assert "icons" in self.manifest
        assert len(self.manifest["icons"]) >= 2

    def test_icon_192_in_manifest(self):
        sizes = [icon.get("sizes") for icon in self.manifest["icons"]]
        assert "192x192" in sizes

    def test_icon_512_in_manifest(self):
        sizes = [icon.get("sizes") for icon in self.manifest["icons"]]
        assert "512x512" in sizes

    def test_icons_have_src_and_type(self):
        for icon in self.manifest["icons"]:
            assert "src" in icon
            assert "type" in icon
            assert icon["type"] == "image/png"

    def test_shortcuts_if_present(self):
        shortcuts = self.manifest.get("shortcuts", [])
        for sc in shortcuts:
            assert "name" in sc
            assert "url" in sc


# ── PNG アイコン検証 ─────────────────────────────────────────
class TestPNGIcons:
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    def _check_png(self, path: Path, expected_size: int):
        data = path.read_bytes()
        assert data[:8] == self.PNG_SIGNATURE, f"{path.name}: Invalid PNG signature"
        w, h = struct.unpack(">II", data[16:24])
        assert w == expected_size, f"{path.name}: width={w}, expected {expected_size}"
        assert h == expected_size, f"{path.name}: height={h}, expected {expected_size}"

    def test_icon_192_valid_png(self):
        self._check_png(STATIC_DIR / "icons" / "icon-192.png", 192)

    def test_icon_512_valid_png(self):
        self._check_png(STATIC_DIR / "icons" / "icon-512.png", 512)

    def test_icon_192_not_empty(self):
        assert (STATIC_DIR / "icons" / "icon-192.png").stat().st_size > 100

    def test_icon_512_not_empty(self):
        assert (STATIC_DIR / "icons" / "icon-512.png").stat().st_size > 100


# ── sw.js 内容確認 ─────────────────────────────────────────
class TestServiceWorker:
    @pytest.fixture(autouse=True)
    def load_sw(self):
        self.sw = (STATIC_DIR / "sw.js").read_text()

    def test_has_install_event(self):
        assert "install" in self.sw

    def test_has_activate_event(self):
        assert "activate" in self.sw

    def test_has_fetch_event(self):
        assert "fetch" in self.sw

    def test_has_cache_open(self):
        assert "caches.open" in self.sw

    def test_no_api_caching(self):
        assert "/api/" in self.sw

    def test_static_assets_listed(self):
        assert "/static/style.css" in self.sw

    def test_skip_waiting(self):
        assert "skipWaiting" in self.sw


# ── テンプレート内の PWA マークアップ確認 ──────────────────────
class TestTemplatesPWA:
    @pytest.fixture(params=list(TEMPLATES_DIR.glob("*.html")))
    def template(self, request):
        return request.param.read_text()

    def test_manifest_link_in_head(self, template):
        assert 'rel="manifest"' in template

    def test_sw_registration_script(self, template):
        assert "serviceWorker" in template or "sw.js" in template

    def test_apple_touch_icon(self, template):
        assert "apple-touch-icon" in template

    def test_mobile_web_app_capable(self, template):
        assert "mobile-web-app-capable" in template


# ── HTTP エンドポイントでの静的ファイル配信確認 ──────────────
@pytest.mark.asyncio
async def test_manifest_served():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/static/manifest.json")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_sw_served():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/static/sw.js")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_icon_192_served():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/static/icons/icon-192.png")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_icon_512_served():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/static/icons/icon-512.png")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_manifest_content_type():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/static/manifest.json")
    assert "json" in res.headers.get("content-type", "").lower()
