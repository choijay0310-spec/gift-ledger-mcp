import os
import sys
import tempfile

import pytest

# 테스트용 임시 DB 사용
_tmp = tempfile.mktemp(suffix=".db")
os.environ["DB_PATH"] = _tmp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.server import (
    check_balance,
    generate_message,
    list_events,
    record_event,
    recommend_amount,
    summarize_monthly,
)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """각 테스트마다 새 DB 파일 사용."""
    db_file = str(tmp_path / "test.db")
    os.environ["DB_PATH"] = db_file
    yield
    if os.path.exists(db_file):
        os.remove(db_file)


# ──────────────────────────────────────────────
# record_event
# ──────────────────────────────────────────────

class TestRecordEvent:
    def test_given_direction_returns_success(self):
        result = record_event("김철수", "친한친구", "결혼", 100_000, "given", "2026-05-01")
        assert "김철수" in result
        assert "100,000원" in result
        assert "지출" in result

    def test_received_direction_returns_received_label(self):
        result = record_event("이영희", "친척", "돌잔치", 50_000, "received", "2026-06-01")
        assert "수령" in result

    def test_invalid_direction_returns_error(self):
        result = record_event("홍길동", "직장동료", "결혼", 50_000, "WRONG")
        assert "오류" in result

    def test_no_date_uses_today(self):
        result = record_event("박지수", "친한친구", "생일", 30_000, "given")
        assert "박지수" in result
        # 날짜 없어도 정상 기록
        assert "30,000원" in result

    def test_note_stored(self):
        record_event("최민준", "직장상사", "결혼", 100_000, "given", note="케이크도 같이")
        result = list_events(person="최민준")
        assert "케이크도 같이" in result


# ──────────────────────────────────────────────
# list_events
# ──────────────────────────────────────────────

class TestListEvents:
    def setup_method(self):
        record_event("A", "친한친구", "결혼", 100_000, "given", "2026-03-01")
        record_event("B", "직장동료", "부고", 30_000, "given", "2026-03-10")
        record_event("A", "친한친구", "생일", 30_000, "received", "2026-04-01")

    def test_no_filter_returns_all(self):
        result = list_events()
        assert "3건" in result

    def test_filter_by_person(self):
        result = list_events(person="A")
        assert "2건" in result
        assert "B" not in result

    def test_filter_by_direction_given(self):
        result = list_events(direction="given")
        assert "2건" in result

    def test_filter_by_year_month(self):
        result = list_events(year=2026, month=3)
        assert "2건" in result

    def test_empty_result_message(self):
        result = list_events(person="없는사람")
        assert "없습니다" in result

    def test_subtotal_shown(self):
        result = list_events()
        assert "소계" in result


# ──────────────────────────────────────────────
# recommend_amount
# ──────────────────────────────────────────────

class TestRecommendAmount:
    def test_known_relationship_and_type(self):
        result = recommend_amount("친한친구", "결혼")
        assert "150,000원" in result
        assert "범위" in result

    def test_unknown_returns_no_data_message(self):
        result = recommend_amount("모르는관계", "파티")
        assert "⚠️" in result

    def test_personal_history_appended(self):
        record_event("X", "직장동료", "결혼", 70_000, "given")
        result = recommend_amount("직장동료", "결혼")
        assert "평균" in result


# ──────────────────────────────────────────────
# check_balance
# ──────────────────────────────────────────────

class TestCheckBalance:
    def test_no_record_returns_not_found(self):
        result = check_balance("없는사람")
        assert "없습니다" in result

    def test_balance_more_given(self):
        record_event("영희", "친한친구", "결혼", 100_000, "given")
        record_event("영희", "친한친구", "생일", 30_000, "received")
        result = check_balance("영희")
        assert "더 씀" in result
        assert "70,000원" in result

    def test_balance_equal(self):
        record_event("철수", "친척", "결혼", 50_000, "given")
        record_event("철수", "친척", "돌잔치", 50_000, "received")
        result = check_balance("철수")
        assert "딱 맞음" in result

    def test_balance_more_received(self):
        record_event("민수", "직장동료", "결혼", 30_000, "given")
        record_event("민수", "직장동료", "부고", 80_000, "received")
        result = check_balance("민수")
        assert "더 받음" in result


# ──────────────────────────────────────────────
# generate_message
# ──────────────────────────────────────────────

class TestGenerateMessage:
    def test_wedding_warm_tone(self):
        result = generate_message("결혼", "지수")
        assert "지수" in result
        assert "추천 메시지" in result

    def test_funeral_formal_tone(self):
        result = generate_message("부고", "철수", tone="격식있는")
        assert "명복" in result

    def test_unknown_event_type(self):
        result = generate_message("입사", "민준")
        assert "없습니다" in result

    def test_birthday_message(self):
        result = generate_message("생일", "예린")
        assert "예린" in result

    def test_warm_tone_full_name_uses_firstname_vocative(self):
        result = generate_message("돌잔치", "박지훈")
        assert "지훈아" in result
        assert "박지훈" not in result.split('"')[1]  # 메시지 본문에 성 제거 확인

    def test_warm_tone_short_name_adds_vocative(self):
        result = generate_message("생일", "민수")
        assert "민수야" in result

    def test_warm_tone_name_with_batchim_adds_ah(self):
        result = generate_message("결혼", "김지훈")
        assert "지훈아" in result

    def test_empty_event_type_returns_error(self):
        result = generate_message("", "지수")
        assert "오류" in result

    def test_empty_person_name_returns_error(self):
        result = generate_message("결혼", "")
        assert "오류" in result


# ──────────────────────────────────────────────
# summarize_monthly
# ──────────────────────────────────────────────

class TestSummarizeMonthly:
    def test_no_record_returns_empty_message(self):
        result = summarize_monthly(year=2000, month=1)
        assert "없습니다" in result

    def test_totals_correct(self):
        record_event("A", "친한친구", "결혼", 100_000, "given", "2026-06-05")
        record_event("B", "직장동료", "생일", 50_000, "received", "2026-06-10")
        result = summarize_monthly(year=2026, month=6)
        assert "100,000원" in result
        assert "50,000원" in result

    def test_type_breakdown_shown(self):
        record_event("A", "친한친구", "결혼", 100_000, "given", "2026-06-01")
        record_event("B", "친척", "돌잔치", 50_000, "given", "2026-06-15")
        result = summarize_monthly(year=2026, month=6)
        assert "유형별 지출" in result
        assert "결혼" in result


# ──────────────────────────────────────────────
# 입력 검증 (신규 추가)
# ──────────────────────────────────────────────

class TestInputValidation:
    def test_negative_amount_returns_error(self):
        result = record_event("김철수", "친한친구", "결혼", -50_000, "given")
        assert "오류" in result

    def test_zero_amount_returns_error(self):
        result = record_event("김철수", "친한친구", "결혼", 0, "given")
        assert "오류" in result

    def test_empty_person_returns_error(self):
        result = record_event("   ", "친한친구", "결혼", 100_000, "given")
        assert "오류" in result

    def test_empty_event_type_returns_error(self):
        result = record_event("김철수", "친한친구", "", 100_000, "given")
        assert "오류" in result

    def test_invalid_date_format_returns_error(self):
        result = record_event("김철수", "친한친구", "결혼", 100_000, "given", "20260601")
        assert "오류" in result

    def test_invalid_month_list_events_returns_error(self):
        result = list_events(month=13)
        assert "오류" in result

    def test_invalid_year_list_events_returns_error(self):
        result = list_events(year=1800)
        assert "오류" in result

    def test_invalid_direction_list_events_returns_error(self):
        result = list_events(direction="both")
        assert "오류" in result

    def test_partial_person_search_works(self):
        record_event("김철수", "친한친구", "결혼", 100_000, "given", "2026-05-01")
        result = list_events(person="철수")
        assert "김철수" in result

    def test_invalid_tone_returns_error(self):
        result = generate_message("결혼", "지수", tone="우스운")
        assert "오류" in result

    def test_empty_person_check_balance_returns_error(self):
        result = check_balance("")
        assert "오류" in result

    def test_partial_person_check_balance_works(self):
        record_event("김영희", "친척", "돌잔치", 50_000, "given")
        result = check_balance("영희")
        assert "김영희" in result

    def test_invalid_month_summarize_returns_error(self):
        result = summarize_monthly(year=2026, month=0)
        assert "오류" in result

    def test_invalid_year_summarize_returns_error(self):
        result = summarize_monthly(year=2200, month=6)
        assert "오류" in result
