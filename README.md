# 비파이(B-FAI) 백엔드

> **노인 및 교통약자를 위한 실시간 지하철 길안내 서비스**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)](https://www.postgresql.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?logo=openai)](https://openai.com/)



### 수동 설치

#### 1. 환경 변수 설정 (필수!)

```bash
cd backend

# .env 파일 생성
cp .env.example .env

# .env 파일 편집
nano .env  # 또는 vim, code 등
```

**.env 파일에서 반드시 수정해야 할 항목:**
```bash
# OpenAI API 키 (필수!)
OPENAI_API_KEY=your-openai-api-key-here  # ← 실제 API 키로 변경
```

**OpenAI API 키 받는 방법:**
1. https://platform.openai.com/api-keys 접속
2. 로그인 후 "Create new secret key" 클릭
3. 생성된 키를 복사하여 .env 파일에 붙여넣기

### 2. Docker 실행

**Docker 권한 오류 발생 시:**
```bash
# Docker 그룹에 사용자 추가
sudo usermod -aG docker $USER

# 그룹 변경 적용
newgrp docker

# 또는 sudo 사용
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

**정상 실행:**
```bash
# 컨테이너 시작 (캐시 없이 빌드)
docker-compose build --no-cache
docker-compose up -d

# 로그 확인 (서버 시작 대기)
docker-compose logs -f backend
```

서버가 시작되면 (Ctrl+C로 로그 종료):

### 3. 데이터 임포트
```bash
# CSV 데이터를 DB에 임포트
docker-compose exec backend python scripts/import_csv.py
```

**예상 출력:**
```
✅ Imported 20 new stations
✅ Imported 89 station facilities
✅ Imported 156 exits
```

### 4. API 테스트
- **Swagger UI**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **API 가이드**: [API_GUIDE.md](API_GUIDE.md)

---

## 🔄 컨테이너 관리

### 일반 재시작 (데이터 유지)
```bash
# 컨테이너 중지 및 삭제 (볼륨/데이터는 유지)
docker-compose down

# 재시작
docker-compose up -d
```

### 코드 변경 후 재빌드
```bash
# 1. 컨테이너 중지
docker-compose down

# 2. 이미지 캐시 없이 재빌드
docker-compose build --no-cache

# 3. 재시작
docker-compose up -d
```

### 데이터베이스 초기화 (완전 초기화)
```bash
# 볼륨(DB 데이터)까지 삭제
docker-compose down -v

# 재시작
docker-compose up -d

# 데이터 다시 임포트
docker-compose exec backend python scripts/import_csv.py
```

### 완전 초기화 (이미지 + 볼륨 모두 삭제)
```bash
docker-compose down --rmi all --volumes
docker-compose build --no-cache
docker-compose up -d
docker-compose exec backend python scripts/import_csv.py
```

**중요**: 
- `down` → 컨테이너만 삭제, **데이터 유지**
- `down -v` → 컨테이너 + **데이터 삭제**

---

## 📡 주요 API

### 1. 경로 탐색
```http
POST /api/route/search
```
GPS 기반 최적 출입구 선택, 실시간 엘리베이터 상태 확인, 8개 체크포인트 자동 생성

### 2. 체크포인트 안내
```http
POST /api/checkpoint/guide
```
RAG 5단계 처리: DB → Open API → RAG 검색 → GPT-4 → 노인 친화적 안내문

### 3. 실시간 정보
```http
GET /api/checkpoint/realtime/{station_name}
```
엘리베이터 상태, 출입구 폐쇄, 휠체어 충전소 정보

---

## 🧪 Open API 테스트

### 전체 API 테스트 (11개)
```bash
# 모든 Open API 자동 테스트
docker-compose exec backend python scripts/test_all_apis.py
```

**사용 가능한 API:**
- ✅ 일반 인증키 (9개): 엘리베이터, 출입구 폐쇄, 최단경로, 안전발판, 충전소 등
- ✅ 실시간 인증키 (2개): 실시간 열차위치, 실시간 도착정보

**상세 가이드**: [API_TEST_GUIDE.md](API_TEST_GUIDE.md)

---

## 🏗️ 기술 스택

- **Backend**: FastAPI, Python 3.11
- **Database**: PostgreSQL 15
- **AI**: OpenAI GPT-4, LangChain, ChromaDB
- **Open API**: 
  - 일반 인증키 (9개 API): 교통약자 시설, 출입구 폐쇄, 최단경로 등
  - 실시간 인증키 (2개 API): 실시간 열차위치, 도착정보
  - 캐싱: 5분 (메모리 캐시)
- **Container**: Docker, Docker Compose

---

## 🔧 문제 해결

### CSV 파일을 찾을 수 없음
```bash
# static_data 폴더 확인
ls -la backend/static_data/

# 컨테이너 내부 확인
docker-compose exec backend ls -la /app/static_data/

# 파일이 없으면 재시작
docker-compose down
docker-compose up -d
```

### 데이터 중복 오류 (duplicate key)
```bash
# 데이터베이스 초기화 후 재임포트
docker-compose down -v
docker-compose up -d
docker-compose exec backend python scripts/import_csv.py
```

### 이전 코드가 계속 실행됨
```bash
# 이미지 캐시 삭제 후 재빌드
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 포트 충돌
```bash
# 기존 컨테이너 중지
docker-compose down

# 포트 확인 (Windows)
netstat -ano | findstr :8000
netstat -ano | findstr :5432

# 포트 확인 (Linux/WSL)
lsof -i :8000
lsof -i :5432
```

### 로그 확인
```bash
# 전체 로그
docker-compose logs -f

# Backend만
docker-compose logs -f backend

# DB만
docker-compose logs -f db

# 최근 100줄만
docker-compose logs --tail=100 backend
```

---

## 📊 데이터베이스

### 테이블 구조 (10개)
- `stations` - 역 정보 (20개)
- `exits` - 출입구 (156개, GPS 좌표)
- `station_facilities` - 편의시설
- `platform_info` - 승강장 정보
- `platform_edges` - 연단 정보
- `routes` - 경로 (실시간 계산)
- `optimal_boarding` - 최적 탑승 칸
- `exit_to_platform` - 출구↔승강장 매핑
- `transfer_info` - 환승 정보
- `charging_stations` - 휠체어 충전소

### DB 접속
```bash
docker-compose exec db psql -U bfai_user -d bfai_db

# 테이블 확인
\dt

# 역 개수 확인
SELECT COUNT(*) FROM stations;

# 종료
\q
```

---

## 📚 API 문서

### 프론트엔드 개발자용
- **API_GUIDE.md** - 상세한 API 사용법, 프론트엔드 통합 가이드

### 대화형 테스트
- **Swagger UI**: http://localhost:8000/docs
- **Postman**: `POSTMAN_COLLECTION.json` 파일을 Postman에 Import

---

**작성일**: 2025-11-18  
**프로젝트**: 비파이(B-FAI) 실시간 길안내 서비스
