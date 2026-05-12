"""経済指標カレンダーモジュール

現在はモック実装。将来はForexFactoryやInvesting.com等のAPIに接続する。
"""
from __future__ import annotations

from datetime import datetime, timedelta


# モック用の重要指標スケジュール（日時はUTC）
# 将来はAPIや外部CSVから動的に読み込む
_MOCK_EVENTS: list[dict] = [
    # 例: {"name": "米国雇用統計", "datetime_utc": "2026-05-02 12:30:00", "impact": "high"}
]


def is_near_economic_event(
    dt: datetime | None = None,
    buffer_minutes: int = 60,
) -> tuple[bool, str]:
    """指定時刻の前後buffer_minutes分以内に重要指標があるか判定する。

    Args:
        dt: チェック対象の時刻（Noneなら現在時刻）
        buffer_minutes: 前後の警戒時間（分）

    Returns:
        (is_warning, event_name): 警戒フラグとイベント名
    """
    if dt is None:
        dt = datetime.utcnow()

    buffer = timedelta(minutes=buffer_minutes)

    for event in _MOCK_EVENTS:
        try:
            event_dt = datetime.strptime(event["datetime_utc"], "%Y-%m-%d %H:%M:%S")
            if abs(dt - event_dt) <= buffer:
                return True, event["name"]
        except (ValueError, KeyError):
            continue

    return False, ""


def get_upcoming_events(hours_ahead: int = 24) -> list[dict]:
    """今後hours_ahead時間以内の重要指標一覧を返す。"""
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=hours_ahead)

    upcoming = []
    for event in _MOCK_EVENTS:
        try:
            event_dt = datetime.strptime(event["datetime_utc"], "%Y-%m-%d %H:%M:%S")
            if now <= event_dt <= cutoff:
                upcoming.append(event)
        except (ValueError, KeyError):
            continue

    return upcoming
