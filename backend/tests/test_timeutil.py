from datetime import datetime

import pytest

from app.utils.timeutil import iso_utc, week_start_utc


@pytest.mark.parametrize(
    "now_utc, expected",
    [
        # 北京时间 2026-11-05（周四）10:00 → 本周一 11-02 00:00 北京 = 11-01 16:00 UTC
        (datetime(2026, 11, 5, 2, 0), datetime(2026, 11, 1, 16, 0)),
        # 北京时间周一 00:30（UTC 周日 16:30）→ 就是当天 0 点
        (datetime(2026, 11, 1, 16, 30), datetime(2026, 11, 1, 16, 0)),
        # 北京时间周日 23:59（UTC 周日 15:59）→ 上周一
        (datetime(2026, 11, 1, 15, 59), datetime(2026, 10, 25, 16, 0)),
    ],
)
def test_week_starts_monday_midnight_beijing(now_utc, expected):
    assert week_start_utc(now_utc) == expected


def test_iso_utc_has_z_suffix_and_no_fraction():
    # iOS 的 Date 解析不认 "2026-11-05 10:00:00"，统一给 ISO 8601 + Z
    assert iso_utc(datetime(2026, 11, 5, 2, 3, 4, 567000)) == "2026-11-05T02:03:04Z"
