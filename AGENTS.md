# 경조사비 비서 MCP — AGENTS.md

## 프로젝트 개요
한국 경조사 문화에 특화된 MCP 서버. 경조사비 기록·조회·추천·메시지 생성 6개 도구를 제공한다.
Agentic Player 10 공모전 제출용 (예선 마감: 2026-07-14).

## 기술 스택
- Python 3.12 + FastMCP (`mcp[cli]>=1.9.0`)
- SQLite (`/tmp/giftledger.db`) — 컨테이너 재시작 시 초기화
- Streamable-HTTP transport, 포트 8000
- Dockerfile → PlayMCP in KC 배포

## 폴더 구조
```
경조사비-mcp/
├── src/
│   └── server.py       # MCP 서버 진입점 (모든 도구 포함)
├── tests/
│   └── test_server.py  # pytest 기반 단위 테스트
├── Dockerfile
├── requirements.txt
└── AGENTS.md
```

## MCP 도구 목록 (6개)
| 도구 | 역할 |
|------|------|
| `record_event` | 경조사 기록 (받은 것/낸 것) |
| `list_events` | 기록 목록 조회 (필터: 인물/유형/방향/날짜) |
| `recommend_amount` | 관계·상황별 적정 금액 추천 |
| `check_balance` | 특정 인물과 주고받은 금액 비교 |
| `generate_message` | 축하·위로 메시지 생성 |
| `summarize_monthly` | 월별 지출 요약 |

## 로컬 개발 명령
```bash
pip install -r requirements.txt
python src/server.py          # HTTP 서버 시작 (포트 8000)
mcp dev src/server.py         # MCP Inspector로 도구 테스트
pytest tests/ -v              # 단위 테스트
```

## Docker 빌드 & 실행
```bash
docker build -t gift-mcp .
docker run -p 8000:8000 gift-mcp
```

## 운영 규칙
- 도구 설명은 반드시 한국어로 작성 (PlayMCP 심사 기준)
- 금액은 항상 원(₩) 단위 정수, 쉼표 포맷으로 표시
- direction 값: `given`(내가 냄) / `received`(받음)
- 새 도구 추가 시 tests/test_server.py 에 테스트 먼저 작성 (TDD)
- 파일 1개 (server.py) 800줄 미만 유지 — 초과 시 tools/ 디렉토리로 분리
