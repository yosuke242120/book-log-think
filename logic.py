"""
Book Log & Think — コアロジック
ここにテスト対象の純粋関数をまとめる。
"""
from datetime import date
from typing import Optional


def is_alert(status: str, start_date, today: date = None) -> bool:
    """
    読書中かつ開始日から21日超過した場合に True を返す。

    Parameters
    ----------
    status     : 'unread' / 'reading' / 'done'
    start_date : date オブジェクト、または None
    today      : 基準日（省略時は date.today()）

    Returns
    -------
    bool
    """
    if today is None:
        today = date.today()

    if status != "reading":
        return False
    if start_date is None:
        return False

    # 型の正規化（pandas Timestamp などを date に変換）
    if hasattr(start_date, "date"):
        start_date = start_date.date()

    elapsed = (today - start_date).days
    return elapsed > 21


def validate_dates(
    start_date: Optional[date],
    end_date:   Optional[date],
) -> Optional[str]:
    """
    開始日と読了日のバリデーション。

    Returns
    -------
    str  : エラーメッセージ（問題あり）
    None : 問題なし
    """
    if start_date is None or end_date is None:
        return None
    if end_date < start_date:
        return "読了日は読書開始日以降に設定してください"
    return None