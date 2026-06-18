import os
import sqlite3
from datetime import date, datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP

DB_PATH = os.environ.get("DB_PATH", "/tmp/giftledger.db")

mcp = FastMCP("경조사비 비서")

# 관계·경조사 유형별 적정 금액 기준표 (원)
_AMOUNT_GUIDE: dict[str, dict[str, int]] = {
    "친한친구": {"결혼": 100_000, "돌잔치": 50_000, "부고": 50_000, "생일": 30_000},
    "직장동료": {"결혼": 50_000, "돌잔치": 30_000, "부고": 30_000, "생일": 0},
    "직장상사": {"결혼": 100_000, "돌잔치": 50_000, "부고": 50_000, "생일": 0},
    "친척": {"결혼": 100_000, "돌잔치": 50_000, "부고": 50_000, "생일": 30_000},
    "아는사람": {"결혼": 30_000, "돌잔치": 0, "부고": 30_000, "생일": 0},
}

_MESSAGE_TEMPLATES: dict[str, dict[str, str]] = {
    "결혼": {
        "따뜻한": "{name}의 새로운 시작을 진심으로 축하해! 두 사람이 함께하는 앞날이 행복으로 가득하길 바라. 🎊",
        "격식있는": "{name} 결혼을 진심으로 축하드립니다. 앞으로의 새 출발이 항상 행복하고 건강하시길 기원합니다.",
    },
    "돌잔치": {
        "따뜻한": "아이의 첫 번째 생일 정말 축하해! 건강하고 씩씩하게 자라길 바라. 🎂",
        "격식있는": "소중한 아이의 첫 돌을 진심으로 축하드립니다. 건강하고 밝게 자라나길 기원합니다.",
    },
    "부고": {
        "따뜻한": "삼가 고인의 명복을 빕니다. {name}, 힘든 시간 잘 이겨내길 진심으로 응원해.",
        "격식있는": "삼가 고인의 명복을 빌며, {name}께서 빠른 시일 내에 평안을 찾으시길 기원합니다.",
    },
    "생일": {
        "따뜻한": "{name} 생일 축하해! 오늘 하루도 특별하고 행복한 날이 되길! 🎉",
        "격식있는": "{name}의 생신을 진심으로 축하드립니다. 건강하고 행복한 한 해 되세요.",
    },
}

_VALID_TONES = {"따뜻한", "격식있는"}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ.get("DB_PATH", DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            person       TEXT    NOT NULL,
            relationship TEXT    NOT NULL,
            event_type   TEXT    NOT NULL,
            amount       INTEGER NOT NULL,
            direction    TEXT    NOT NULL CHECK(direction IN ('given', 'received')),
            event_date   TEXT    NOT NULL,
            note         TEXT    DEFAULT '',
            created_at   TEXT    NOT NULL
        )
    """)
    conn.commit()
    return conn


def _calculate_totals(rows: list) -> tuple[int, int]:
    """(지출 합계, 수입 합계) 반환."""
    total_given = sum(r["amount"] for r in rows if r["direction"] == "given")
    total_received = sum(r["amount"] for r in rows if r["direction"] == "received")
    return total_given, total_received


@mcp.tool()
def record_event(
    person: str,
    relationship: str,
    event_type: str,
    amount: int,
    direction: str,
    event_date: Optional[str] = None,
    note: str = "",
) -> str:
    """경조사 이벤트를 기록합니다.

    Args:
        person: 상대방 이름
        relationship: 관계 (친한친구/직장동료/직장상사/친척/아는사람 등)
        event_type: 경조사 종류 (결혼/돌잔치/부고/생일 등)
        amount: 금액 (원 단위 양의 정수)
        direction: given(내가 냄) 또는 received(받음)
        event_date: 날짜 YYYY-MM-DD, 생략 시 오늘
        note: 메모 (선택)
    """
    if not person or not person.strip():
        return "오류: 상대방 이름을 입력하세요."
    if not relationship or not relationship.strip():
        return "오류: 관계를 입력하세요."
    if not event_type or not event_type.strip():
        return "오류: 경조사 종류를 입력하세요."
    if amount <= 0:
        return "오류: 금액은 1원 이상이어야 합니다."
    if direction not in ("given", "received"):
        return "오류: direction은 'given' 또는 'received'여야 합니다."
    if len(note) > 1000:
        return "오류: 메모는 1000자 이내여야 합니다."

    event_date = event_date or date.today().isoformat()
    if len(event_date) != 10 or event_date[4] != "-" or event_date[7] != "-":
        return "오류: 날짜 형식이 잘못되었습니다. YYYY-MM-DD 형식으로 입력해 주세요. (예: 2026-06-17)"
    try:
        date.fromisoformat(event_date)
    except ValueError:
        return "오류: 날짜 형식이 잘못되었습니다. YYYY-MM-DD 형식으로 입력해 주세요. (예: 2026-06-17)"

    person = person.strip()
    relationship = relationship.strip()
    event_type = event_type.strip()
    now = datetime.now().isoformat()

    with _get_db() as conn:
        conn.execute(
            "INSERT INTO events "
            "(person, relationship, event_type, amount, direction, event_date, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (person, relationship, event_type, amount, direction, event_date, note, now),
        )
        conn.commit()

    direction_label = "냈습니다" if direction == "given" else "받았습니다"
    return (
        f"✅ {event_date} | {person}({relationship}) {event_type}에 "
        f"{amount:,}원을 {direction_label}. 기록 완료!"
    )


@mcp.tool()
def list_events(
    person: Optional[str] = None,
    event_type: Optional[str] = None,
    direction: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> str:
    """경조사 기록 목록을 조회합니다. (최근 50건 제한)

    Args:
        person: 특정 인물 필터 — 부분 일치 검색 가능 (선택)
        event_type: 경조사 종류 필터 (선택)
        direction: given 또는 received 필터 (선택)
        year: 연도 필터 (선택)
        month: 월 필터 1~12 (선택)
    """
    if direction is not None and direction not in ("given", "received"):
        return "오류: direction은 'given' 또는 'received'여야 합니다."
    if year is not None and not (1900 <= year <= 2100):
        return "오류: 연도는 1900~2100 사이로 입력해 주세요."
    if month is not None and not (1 <= month <= 12):
        return "오류: 월은 1~12 사이로 입력해 주세요."

    query = "SELECT * FROM events WHERE 1=1"
    params: list = []

    if person:
        query += " AND person LIKE ?"
        params.append(f"%{person.strip()}%")
    if event_type:
        query += " AND event_type=?"
        params.append(event_type)
    if direction:
        query += " AND direction=?"
        params.append(direction)
    if year:
        query += " AND strftime('%Y', event_date)=?"
        params.append(str(year))
    if month:
        query += " AND strftime('%m', event_date)=?"
        params.append(f"{month:02d}")

    query += " ORDER BY event_date DESC LIMIT 50"

    with _get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return "조건에 맞는 기록이 없습니다."

    total_given, total_received = _calculate_totals(rows)

    lines = [f"📋 경조사 기록 ({len(rows)}건):\n"]
    for r in rows:
        label = "▶ 냄" if r["direction"] == "given" else "◀ 받음"
        lines.append(
            f"  {r['event_date']} | {r['person']}({r['relationship']}) "
            f"| {r['event_type']} | {r['amount']:,}원 | {label}"
        )
        if r["note"]:
            lines.append(f"    메모: {r['note']}")

    lines.append(f"\n💰 소계: 지출 {total_given:,}원 | 수입 {total_received:,}원")
    return "\n".join(lines)


@mcp.tool()
def recommend_amount(
    relationship: str,
    event_type: str,
) -> str:
    """관계와 경조사 종류에 따른 적정 금액을 추천합니다.

    Args:
        relationship: 관계 (친한친구/직장동료/직장상사/친척/아는사람)
        event_type: 경조사 종류 (결혼/돌잔치/부고/생일)
    """
    guide = _AMOUNT_GUIDE.get(relationship, {})
    base = guide.get(event_type, 0)

    if base == 0:
        valid_relationships = ", ".join(_AMOUNT_GUIDE.keys())
        result = f"⚠️ '{relationship}'의 '{event_type}'에 대한 표준 금액 데이터가 없습니다.\n"
        result += f"지원 관계: {valid_relationships}\n"
        result += "비슷한 경우를 참고하거나 직접 판단해 주세요."
    else:
        low = int(base * 0.8)
        high = int(base * 1.5)
        result = (
            f"💰 {relationship} {event_type} 적정 금액:\n"
            f"  기본: {base:,}원\n"
            f"  범위: {low:,}원 ~ {high:,}원\n"
            f"  친밀도·상황에 따라 조정하세요."
        )

    with _get_db() as conn:
        rows = conn.execute(
            "SELECT amount FROM events WHERE relationship=? AND event_type=? AND direction='given'",
            (relationship, event_type),
        ).fetchall()

    if rows:
        amounts = [r["amount"] for r in rows]
        avg = round(sum(amounts) / len(amounts))
        result += f"\n\n📊 내 과거 기록: 동일 유형에 평균 {avg:,}원 냈습니다."

    return result


@mcp.tool()
def check_balance(person: str) -> str:
    """특정 인물과의 경조사비 주고받은 내역을 비교합니다.

    Args:
        person: 조회할 상대방 이름 (부분 일치 검색 가능)
    """
    if not person or not person.strip():
        return "오류: 이름을 입력하세요."

    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE person LIKE ? ORDER BY event_date DESC",
            (f"%{person.strip()}%",),
        ).fetchall()

    if not rows:
        return f"'{person}'에 대한 기록이 없습니다."

    total_given, total_received = _calculate_totals(rows)
    balance = total_given - total_received

    matched_names = sorted(set(r["person"] for r in rows))
    if len(matched_names) > 1:
        header = f"📋 '{person}' 검색 결과 — {', '.join(matched_names)} 포함 {len(rows)}건:\n"
    else:
        header = f"📋 {matched_names[0]}과의 경조사 내역:\n"

    lines = [header]
    for r in rows:
        label = "▶ 내가 냄" if r["direction"] == "given" else "◀ 받음"
        lines.append(
            f"  {r['event_date']} | {r['person']} {r['event_type']} | {r['amount']:,}원 | {label}"
        )
        if r["note"]:
            lines.append(f"    메모: {r['note']}")

    lines.append(f"\n💰 합계: 내가 낸 것 {total_given:,}원 | 받은 것 {total_received:,}원")
    if balance > 0:
        lines.append(f"➡ 내가 {balance:,}원 더 씀")
    elif balance < 0:
        lines.append(f"➡ 내가 {abs(balance):,}원 더 받음")
    else:
        lines.append("➡ 딱 맞음!")

    return "\n".join(lines)


@mcp.tool()
def generate_message(
    event_type: str,
    person_name: str,
    tone: str = "따뜻한",
) -> str:
    """경조사에 맞는 메시지를 생성합니다.

    Args:
        event_type: 경조사 종류 (결혼/돌잔치/부고/생일)
        person_name: 상대방 이름 또는 호칭
        tone: 메시지 톤 — 따뜻한(기본) 또는 격식있는
    """
    if tone not in _VALID_TONES:
        return f"오류: tone은 '따뜻한' 또는 '격식있는' 중 하나여야 합니다."

    event_templates = _MESSAGE_TEMPLATES.get(event_type, {})
    template = event_templates.get(tone)

    if template is None:
        available = ", ".join(_MESSAGE_TEMPLATES.keys())
        return f"'{event_type}'에 대한 메시지 템플릿이 없습니다. 사용 가능한 종류: {available}"

    message = template.format(name=person_name)
    return f'💬 추천 메시지:\n"{message}"'


@mcp.tool()
def summarize_monthly(
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> str:
    """월별 경조사 지출·수입을 요약합니다.

    Args:
        year: 연도 (생략 시 올해)
        month: 월 (생략 시 이번 달)
    """
    today = date.today()
    year = year if year is not None else today.year
    month = month if month is not None else today.month

    if not (1900 <= year <= 2100):
        return "오류: 연도는 1900~2100 사이로 입력해 주세요."
    if not (1 <= month <= 12):
        return "오류: 월은 1~12 사이로 입력해 주세요."

    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM events "
            "WHERE strftime('%Y', event_date)=? AND strftime('%m', event_date)=? "
            "ORDER BY event_date",
            (str(year), f"{month:02d}"),
        ).fetchall()

    if not rows:
        return f"{year}년 {month}월 경조사 기록이 없습니다."

    total_given, total_received = _calculate_totals(rows)

    by_type: dict[str, int] = {}
    for r in rows:
        if r["direction"] == "given":
            by_type[r["event_type"]] = by_type.get(r["event_type"], 0) + r["amount"]

    lines = [f"📅 {year}년 {month}월 경조사 요약 ({len(rows)}건):\n"]
    for r in rows:
        label = "▶ 냄" if r["direction"] == "given" else "◀ 받음"
        lines.append(f"  {r['event_date']} | {r['person']} {r['event_type']} | {r['amount']:,}원 | {label}")

    lines.append(f"\n💰 지출: {total_given:,}원 | 수입: {total_received:,}원")
    lines.append(f"   순 지출: {total_given - total_received:,}원")

    if by_type:
        lines.append("\n📊 유형별 지출:")
        for t, amt in sorted(by_type.items(), key=lambda x: -x[1]):
            lines.append(f"  {t}: {amt:,}원")

    return "\n".join(lines)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")
