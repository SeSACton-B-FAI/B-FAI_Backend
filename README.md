# 비파이(B-FAI) 백엔드

> **노인 및 교통약자를 위한 실시간 지하철 배리어프리 길안내 서비스**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)](https://www.postgresql.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?logo=openai)](https://openai.com/)

---

## 주요 기능

- **8단계 체크포인트 안내**: 출발지 → 출발역 출구 → 승강장 → 대기 → 탑승 → 도착역 승강장 → 도착역 출구 → 충전소
- **실시간 열차 정보**: 서울교통공사 Open API 연동 (도착 시간, 막차 여부)
- **배리어프리 경로**: 엘리베이터 위치, 버튼 안내, 소요 시간
- **RAG 기반 안내**: DB + Open API + LLM 통합 안내문 생성

---

## 설치 및 실행

### 1. 환경 변수 설정

```bash
cd backend
cp .env.example .env
```

**.env 파일 수정:**
```bash
OPENAI_API_KEY=your-openai-api-key-here
```

### 2. Docker 실행

```bash
# 빌드 및 실행
docker-compose build --no-cache
docker-compose up -d

# 로그 확인
docker-compose logs -f backend
```

### 3. 데이터 임포트

```bash
# CSV 데이터 임포트 (역, 출구, 시설 등)
docker-compose exec backend python scripts/import_csv.py

# RAG 벡터 데이터 임포트 (임베딩 모델 로딩에 몇 분 소요)
docker-compose exec backend python scripts/populate_barrier_free_data.py
```

> **참고**: CSV 데이터는 `static_data` 폴더에서 읽어옵니다.

### 4. API 테스트

- **Swagger UI**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## API 개요 (프론트엔드용)

프론트엔드는 **3개 API**만 사용합니다.

### 1. 역 목록 조회
```http
GET /api/route/stations
```
역 선택 드롭다운용

### 2. 경로 검색
```http
POST /api/route/search
```
```json
{
  "start_station": "강남",
  "end_station": "잠실",
  "user_location": {"lat": 37.497952, "lon": 127.027619},
  "user_tags": {
    "mobility_level": "wheelchair",
    "need_elevator": true
  }
}
```

**응답 포함:**
- `walking_to_station`: 출발지→출발역 도보 안내
- `start_exit`/`end_exit`: 출구 상세 (엘리베이터 위치, 버튼)
- `realtime_train`: 실시간 열차 도착 정보
- `checkpoints`: 8단계 체크포인트 (GPS 좌표 포함)

### 3. 체크포인트 안내
```http
POST /api/checkpoint/guide
```
```json
{
  "checkpoint_id": 1,
  "station_name": "강남역",
  "exit_number": "3",
  "need_elevator": true
}
```

| ID | 타입 | 안내 내용 |
|----|------|----------|
| 0 | 출발지 | 도보 방향, 거리, 경사로 주의 |
| 1 | 출발역_출구 | 엘리베이터 위치/버튼/소요시간 |
| 2 | 출발역_승강장 | 탑승 칸 안내 (7-8번째 칸) |
| 3 | 승강장_대기 | **실시간 열차 도착 정보** |
| 4 | 열차_탑승 | **도착역 접근 알림** |
| 5 | 도착역_승강장 | 하차 후 출구 방향 안내 |
| 6 | 도착역_출구 | 엘리베이터 상세 |
| 7 | 충전소 | 휠체어 충전소 위치 (선택) |

---

## 사용 흐름

```
1. GET /api/route/stations → 역 목록
2. POST /api/route/search → 경로 + 8개 체크포인트 GPS
3. 프론트: GPS로 체크포인트 도착 감지
4. POST /api/checkpoint/guide → 해당 체크포인트 상세 안내
```

---

## 기술 스택

- **Backend**: FastAPI, Python 3.11
- **Database**: PostgreSQL 15
- **AI/RAG**: OpenAI GPT-4, LangChain, ChromaDB, HuggingFace Embeddings
- **Open API**: 서울교통공사 실시간 API (11개)
- **Container**: Docker, Docker Compose

---

## 데이터베이스

### 주요 테이블
- `stations` - 역 정보 (20개)
- `exits` - 출입구 (156개, GPS 좌표, 엘리베이터 정보)
- `station_facilities` - 편의시설
- `platform_edges` - 연단 정보
- `transfer_info` - 환승 정보
- `elevator_exit_mapping` - 엘리베이터-출구 매핑

### DB 접속
```bash
docker-compose exec db psql -U bfai_user -d bfai_db
```

---

## 컨테이너 관리

### 일반 재시작
```bash
docker-compose down
docker-compose up -d
```

### 코드 변경 후
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 완전 초기화
```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
docker-compose exec backend python scripts/import_csv.py
docker-compose exec backend python scripts/populate_barrier_free_data.py
```

---

## 문제 해결

### sentence-transformers 오류
```bash
docker-compose build --no-cache
```

### 데이터 중복 오류
```bash
docker-compose down -v
docker-compose up -d
docker-compose exec backend python scripts/import_csv.py
docker-compose exec backend python scripts/populate_barrier_free_data.py
```

### 포트 충돌
```bash
lsof -i :8000
lsof -i :5432
```

---

## 파일 구조

```
backend/
├── app/
│   ├── main.py              # FastAPI 앱
│   ├── routers/
│   │   ├── route.py         # 경로 검색 API
│   │   └── checkpoint.py    # 체크포인트 안내 API
│   ├── services/
│   │   ├── api_service.py   # 서울교통공사 Open API
│   │   └── rag_service.py   # RAG 서비스
│   └── models/
│       └── models.py        # DB 모델
├── scripts/
│   ├── import_csv.py                  # CSV 데이터 임포트
│   └── populate_barrier_free_data.py  # RAG 벡터 데이터 임포트
├── static_data/                        # 정적 CSV 데이터
├── dynamic_data/                       # 동적 API 문서
├── data/                               # ChromaDB 벡터 저장소
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 관련 문서

- **API_GUIDE.md** - 프론트엔드용 상세 API 문서
- **Postman Collection** - `BFAI_API_Collection.postman_collection.json`

---

**작성일**: 2025-11-19
**프로젝트**: 비파이(B-FAI) 실시간 배리어프리 길안내 서비스
