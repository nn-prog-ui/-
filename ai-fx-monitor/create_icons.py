"""stdlib のみでシンプルな PNG アイコンを生成するスクリプト。

出力:
  app/web/static/icons/icon-192.png  (192x192)
  app/web/static/icons/icon-512.png  (512x512)
"""
import struct
import zlib
from pathlib import Path


def _make_png(size: int) -> bytes:
    """
    size×size の PNG を生成する。
    背景: #1a1a2e (ダーク紺)
    折れ線チャート: #4ade80 (グリーン), 線幅は size//20 ピクセル
    """
    # ── ピクセル配列を構築 ────────────────────────────────────
    # RGB (r, g, b) タプルの 2D リスト
    BG  = (0x1a, 0x1a, 0x2e)
    FG  = (0x4a, 0xde, 0x80)
    ACCENT = (0x63, 0xb3, 0xed)  # 青緑の補助線

    pixels = [[BG] * size for _ in range(size)]

    pad   = size // 8        # 余白
    inner = size - 2 * pad   # 描画領域

    # 折れ線グラフの折り返しポイント (x, y) をグリッド内比率で定義
    points_rel = [
        (0.00, 0.70),
        (0.18, 0.50),
        (0.35, 0.60),
        (0.52, 0.30),
        (0.68, 0.45),
        (0.82, 0.15),
        (1.00, 0.25),
    ]
    pts = [
        (int(pad + r[0] * inner), int(pad + r[1] * inner))
        for r in points_rel
    ]

    lw = max(size // 40, 2)  # 線幅

    def draw_pixel(px: int, py: int, color: tuple, radius: int = 0):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = px + dx, py + dy
                if 0 <= nx < size and 0 <= ny < size:
                    pixels[ny][nx] = color

    # セグメントをブレゼンハムで描画
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dx = abs(x1 - x0); dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        cx, cy = x0, y0
        while True:
            for ky in range(-lw, lw + 1):
                for kx in range(-lw, lw + 1):
                    nx, ny = cx + kx, cy + ky
                    if 0 <= nx < size and 0 <= ny < size:
                        pixels[ny][nx] = FG
            if cx == x1 and cy == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy; cx += sx
            if e2 < dx:
                err += dx; cy += sy

    # 折り返し点に小さい丸を打つ
    dot_r = max(size // 50, 2)
    for px, py in pts:
        draw_pixel(px, py, ACCENT, dot_r)

    # ── PNG バイナリを組み立て ────────────────────────────────
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB

    raw = b""
    for row in pixels:
        raw += b"\x00"  # filter type None
        for r, g, b in row:
            raw += bytes([r, g, b])

    idat_data = zlib.compress(raw, level=6)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat_data)
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    out_dir = Path(__file__).parent / "app/web/static/icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    for sz in (192, 512):
        path = out_dir / f"icon-{sz}.png"
        path.write_bytes(_make_png(sz))
        print(f"Generated: {path}  ({path.stat().st_size:,} bytes)")
