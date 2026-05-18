/**
 * Phase 40: Service Worker (PWA対応)
 *
 * 戦略:
 *   - Static assets (/static/*): Cache First（バージョニングで管理）
 *   - HTML ページ:              Network First（常に最新データを表示）
 *   - API エンドポイント:        Network Only（キャッシュしない）
 */

const CACHE_VERSION = 'v1';
const STATIC_CACHE  = `fx-monitor-static-${CACHE_VERSION}`;
const PAGES_CACHE   = `fx-monitor-pages-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  '/static/style.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

const OFFLINE_FALLBACK = '/offline';

// ── インストール ──────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) =>
      cache.addAll(STATIC_ASSETS)
    )
  );
  self.skipWaiting();
});

// ── アクティベート（古いキャッシュを削除） ─────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== PAGES_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── フェッチ ──────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // GET 以外・別オリジンはそのままネットワークへ
  if (request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  // API エンドポイント → Network Only
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // Static assets → Cache First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.match(request).then((cached) =>
          cached || fetch(request).then((res) => {
            cache.put(request, res.clone());
            return res;
          })
        )
      )
    );
    return;
  }

  // HTML ページ → Network First（オフライン時はキャッシュから）
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok) {
          caches.open(PAGES_CACHE).then((cache) => cache.put(request, res.clone()));
        }
        return res;
      })
      .catch(() =>
        caches.match(request).then(
          (cached) => cached || new Response(
            '<html><body style="font-family:sans-serif;padding:2rem;">' +
            '<h1>オフラインです</h1>' +
            '<p>インターネット接続を確認してください。</p>' +
            '<a href="/">再試行</a></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          )
        )
      )
  );
});
