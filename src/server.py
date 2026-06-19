import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Generator, Optional

from mcp.server.fastmcp import FastMCP

DB_PATH = os.environ.get("DB_PATH", "/tmp/giftledger.db")

mcp = FastMCP(
    "경조사비 비서",
    host=os.environ.get("FASTMCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("FASTMCP_PORT", "8000")),
)

# 관계·경조사 유형별 적정 금액 기준표 (원) — 2025년 한국 기준
# 서울 결혼식 뷔페 식대 1인 8~12만원 수준 반영
_AMOUNT_GUIDE: dict[str, dict[str, int]] = {
    "친한친구": {"결혼": 150_000, "돌잔치": 70_000, "부고": 70_000, "생일": 50_000},
    "직장동료": {"결혼": 70_000,  "돌잔치": 50_000, "부고": 50_000, "생일": 0},
    "직장상사": {"결혼": 100_000, "돌잔치": 70_000, "부고": 70_000, "생일": 0},
    "친척":     {"결혼": 200_000, "돌잔치": 100_000, "부고": 100_000, "생일": 50_000},
    "아는사람": {"결혼": 50_000,  "돌잔치": 30_000, "부고": 50_000, "생일": 0},
}

_MESSAGE_TEMPLATES: dict[str, dict[str, str]] = {
    "결혼": {
        "따뜻한": "{name_call}! 결혼 진심으로 축하해! 두 사람이 함께하는 앞날이 사랑과 행복으로 가득하길 바라. 🎊",
        "격식있는": "{name} 결혼을 진심으로 축하드립니다. 앞으로의 새 출발이 항상 행복하고 건강하시길 기원합니다.",
    },
    "돌잔치": {
        "따뜻한": "{name_call}! 아이 첫 돌잔치 진심으로 축하해! 건강하고 씩씩하게 자라길 바라. 🎂",
        "격식있는": "{name} 소중한 아이의 첫 돌을 진심으로 축하드립니다. 건강하고 밝게 자라나길 기원합니다.",
    },
    "부고": {
        "따뜻한": "삼가 고인의 명복을 빕니다. {name_call}... 힘든 시간 잘 이겨내길 진심으로 응원해.",
        "격식있는": "삼가 고인의 명복을 빌며, {name}께서 빠른 시일 내에 평안을 찾으시길 기원합니다.",
    },
    "생일": {
        "따뜻한": "{name_call}! 생일 축하해! 오늘 하루도 특별하고 행복한 날이 되길! 🎉",
        "격식있는": "{name}의 생신을 진심으로 축하드립니다. 건강하고 행복한 한 해 되세요.",
    },
}

_VALID_TONES = {"따뜻한", "격식있는"}

_WEDDING_NOTE = "\n📌 참고: 서울 결혼식 뷔페 식대 1인 8~12만원 수준 (지역·행사에 따라 상이)"

_AMOUNT_RANGE_LOW: float = 0.8
_AMOUNT_RANGE_HIGH: float = 1.5

_MIN_YEAR: int = 1900
_MAX_YEAR: int = 2100
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _extract_firstname(name: str) -> str:
    """성+이름에서 이름 부분만 추출한다. 3글자 이상이면 마지막 2글자를 이름으로 간주한다."""
    return name[-2:] if len(name) >= 3 else name


def _korean_vocative(name: str) -> str:
    """한국어 이름에 받침 여부에 따라 '아' 또는 '야' 호칭을 붙여 반환한다."""
    if not name:
        return name
    code = ord(name[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return name + ("아" if (code - 0xAC00) % 28 != 0 else "야")
    return name + "아"


@contextmanager
def _get_db() -> Generator[sqlite3.Connection, None, None]:
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
    try:
        yield conn
    finally:
        conn.close()


def _calculate_totals(rows: list[sqlite3.Row]) -> tuple[int, int]:
    """(지출 합계, 수입 합계) 반환."""
    if not rows:
        return 0, 0
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
    person = person.strip() if person else ""
    relationship = relationship.strip() if relationship else ""
    event_type = event_type.strip() if event_type else ""

    if not person:
        return "오류: 상대방 이름을 입력하세요."
    if not relationship:
        return "오류: 관계를 입력하세요."
    if not event_type:
        return "오류: 경조사 종류를 입력하세요."
    if amount <= 0:
        return "오류: 금액은 1원 이상이어야 합니다."
    if direction not in ("given", "received"):
        return "오류: direction은 'given' 또는 'received'여야 합니다."
    if len(note) > 1000:
        return "오류: 메모는 1000자 이내여야 합니다."

    event_date = event_date or date.today().isoformat()
    if not _DATE_PATTERN.match(event_date):
        return "오류: 날짜 형식이 잘못되었습니다. YYYY-MM-DD 형식으로 입력해 주세요. (예: 2026-06-18)"
    try:
        date.fromisoformat(event_date)
    except ValueError:
        return "오류: 유효하지 않은 날짜입니다. (예: 2026-06-18)"

    now = datetime.now().isoformat()

    try:
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO events "
                "(person, relationship, event_type, amount, direction, event_date, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (person, relationship, event_type, amount, direction, event_date, note, now),
            )
            conn.commit()
    except sqlite3.OperationalError as e:
        return f"오류: 데이터베이스 오류가 발생했습니다. ({e})"

    direction_label = "지출" if direction == "given" else "수령"
    note_line = f"\n  📝 메모: {note}" if note else ""
    return (
        f"✅ 기록 완료!\n"
        f"  👤 이름: {person} ({relationship})\n"
        f"  🎉 경조사: {event_type}\n"
        f"  💰 금액: {amount:,}원 ({direction_label})\n"
        f"  📅 날짜: {event_date}"
        f"{note_line}"
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
    if year is not None and not (_MIN_YEAR <= year <= _MAX_YEAR):
        return f"오류: 연도는 {_MIN_YEAR}~{_MAX_YEAR} 사이로 입력해 주세요."
    if month is not None and not (1 <= month <= 12):
        return "오류: 월은 1~12 사이로 입력해 주세요."

    query = "SELECT * FROM events WHERE 1=1"
    params: list[Any] = []

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

    try:
        with _get_db() as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.OperationalError as e:
        return f"오류: 데이터베이스 조회 실패. ({e})"

    if not rows:
        return "조건에 맞는 기록이 없습니다."

    total_given, total_received = _calculate_totals(rows)

    lines = [f"📋 경조사 기록 ({len(rows)}건)\n" + "─" * 40]
    for i, r in enumerate(rows, 1):
        label = "▶ 지출" if r["direction"] == "given" else "◀ 수령"
        lines.append(
            f"{i}. {r['event_date']}  {r['person']} ({r['relationship']})\n"
            f"   {r['event_type']}  {r['amount']:,}원  {label}"
        )
        if r["note"]:
            lines.append(f"   📝 {r['note']}")

    lines.append("─" * 40)
    lines.append(f"💰 소계: 지출 {total_given:,}원 | 수령 {total_received:,}원")
    return "\n".join(lines)


@mcp.tool()
def recommend_amount(
    relationship: str,
    event_type: str,
) -> str:
    """관계와 경조사 종류에 따른 적정 금액을 추천합니다.

    Args:
        relationship: 관계 (친한친구/직장동료/직장상사/친척/아는사람/모르는사람)
        event_type: 경조사 종류 (결혼/돌잔치/부고/생일)
    """
    relationship = relationship.strip().replace(" ", "")
    if relationship == "모르는사람":
        return "💡 모르는 분은 경조사 정보를 접할 방법도 없으니 챙기지 않아도 됩니다."

    rel_guide = _AMOUNT_GUIDE.get(relationship)

    if rel_guide is None:
        valid_relationships = ", ".join(_AMOUNT_GUIDE.keys())
        return (
            f"⚠️ '{relationship}'은 등록된 관계가 아닙니다.\n"
            f"지원 관계: {valid_relationships}\n"
            "가장 가까운 관계를 선택하거나 직접 판단해 주세요."
        )

    base = rel_guide.get(event_type)

    if base is None:
        valid_types = ", ".join(rel_guide.keys())
        return (
            f"⚠️ '{relationship}'의 '{event_type}'에 대한 금액 데이터가 없습니다.\n"
            f"지원 경조사: {valid_types}"
        )

    if base == 0:
        result = f"💡 {relationship} {event_type}: 일반적으로 금액 없이 마음으로 챙기는 경우가 많습니다."
    else:
        low = int(base * _AMOUNT_RANGE_LOW)
        high = int(base * _AMOUNT_RANGE_HIGH)
        extra = _WEDDING_NOTE if event_type == "결혼" else ""
        result = (
            f"💰 {relationship} {event_type} 적정 금액 (2025년 기준)\n"
            f"─────────────────────────\n"
            f"  기본 추천: {base:,}원\n"
            f"  적정 범위: {low:,}원 ~ {high:,}원\n"
            f"  ※ 친밀도·지역·행사 규모에 따라 조정하세요.{extra}"
        )

    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT amount FROM events WHERE relationship=? AND event_type=? AND direction='given'",
                (relationship, event_type),
            ).fetchall()
    except sqlite3.OperationalError:
        return result

    if rows:
        amounts = [r["amount"] for r in rows]
        avg = round(sum(amounts) / len(amounts))
        result += f"\n\n📊 내 과거 기록: 동일 유형 평균 {avg:,}원 지출"

    return result


@mcp.tool()
def check_balance(person: str) -> str:
    """특정 인물과의 경조사비 주고받은 내역을 비교합니다.

    Args:
        person: 조회할 상대방 이름 (부분 일치 검색 가능)
    """
    if not person or not person.strip():
        return "오류: 이름을 입력하세요."

    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE person LIKE ? ORDER BY event_date DESC",
                (f"%{person.strip()}%",),
            ).fetchall()
    except sqlite3.OperationalError as e:
        return f"오류: 데이터베이스 조회 실패. ({e})"

    if not rows:
        return f"'{person}'에 대한 기록이 없습니다."

    total_given, total_received = _calculate_totals(rows)
    balance = total_given - total_received

    matched_names = sorted(set(r["person"] for r in rows))
    if len(matched_names) > 1:
        header = f"📋 '{person}' 검색 결과 — {', '.join(matched_names)} ({len(rows)}건)"
    else:
        header = f"📋 {matched_names[0]}과의 경조사 내역 ({len(rows)}건)"

    lines = [header, "─" * 40]
    for r in rows:
        label = "▶ 지출" if r["direction"] == "given" else "◀ 수령"
        lines.append(
            f"  {r['event_date']}  {r['person']} {r['event_type']}\n"
            f"  {r['amount']:,}원  {label}"
        )
        if r["note"]:
            lines.append(f"  📝 {r['note']}")

    lines.append("─" * 40)
    lines.append(f"💰 합계: 내가 낸 것 {total_given:,}원 | 받은 것 {total_received:,}원")
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
    if not event_type or not event_type.strip():
        return "오류: 경조사 종류를 입력하세요."
    if not person_name or not person_name.strip():
        return "오류: 이름을 입력하세요."
    if tone not in _VALID_TONES:
        return f"오류: tone은 '따뜻한' 또는 '격식있는' 중 하나여야 합니다."

    event_templates = _MESSAGE_TEMPLATES.get(event_type.strip(), {})
    template = event_templates.get(tone)

    if template is None:
        available = ", ".join(_MESSAGE_TEMPLATES.keys())
        return f"'{event_type}'에 대한 메시지 템플릿이 없습니다. 사용 가능한 종류: {available}"

    if tone == "따뜻한":
        firstname = _extract_firstname(person_name)
        name_call = _korean_vocative(firstname)
    else:
        name_call = person_name
    message = template.format(name=person_name, name_call=name_call)
    return f'💬 추천 메시지 ({tone}):\n\n"{message}"'


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

    if not (_MIN_YEAR <= year <= _MAX_YEAR):
        return f"오류: 연도는 {_MIN_YEAR}~{_MAX_YEAR} 사이로 입력해 주세요."
    if not (1 <= month <= 12):
        return "오류: 월은 1~12 사이로 입력해 주세요."

    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM events "
                "WHERE strftime('%Y', event_date)=? AND strftime('%m', event_date)=? "
                "ORDER BY event_date",
                (str(year), f"{month:02d}"),
            ).fetchall()
    except sqlite3.OperationalError as e:
        return f"오류: 데이터베이스 조회 실패. ({e})"

    if not rows:
        return f"{year}년 {month}월 경조사 기록이 없습니다."

    total_given, total_received = _calculate_totals(rows)

    by_type: dict[str, int] = {}
    for r in rows:
        if r["direction"] == "given":
            by_type[r["event_type"]] = by_type.get(r["event_type"], 0) + r["amount"]

    lines = [f"📅 {year}년 {month}월 경조사 요약 ({len(rows)}건)", "─" * 40]
    for i, r in enumerate(rows, 1):
        label = "▶ 지출" if r["direction"] == "given" else "◀ 수령"
        lines.append(f"{i}. {r['event_date']}  {r['person']} {r['event_type']}  {r['amount']:,}원  {label}")

    lines.append("─" * 40)
    lines.append(f"💰 지출: {total_given:,}원 | 수령: {total_received:,}원")
    lines.append(f"   순 지출: {total_given - total_received:,}원")

    if by_type:
        lines.append("\n📊 유형별 지출:")
        for t, amt in sorted(by_type.items(), key=lambda x: -x[1]):
            lines.append(f"  · {t}: {amt:,}원")

    return "\n".join(lines)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
