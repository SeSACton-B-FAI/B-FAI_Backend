# 🚀 비파이(B-FAI) 백엔드 환경 설정 가이드

## 📋 목차
1. [환경 변수 설정](#환경-변수-설정)
2. [로컬 개발 환경](#로컬-개발-환경)
3. [Docker로 실행](#docker로-실행)
4. [프로덕션 배포](#프로덕션-배포)
5. [문제 해결](#문제-해결)

---

## 🔐 환경 변수 설정

### 1️⃣ .env.local 파일 생성 (필수!)

```bash
# .env.example을 복사해서 .env.local 생성
cp .env.example .env.local
```

### 2️⃣ OpenAI API 키 설정

`.env.local` 파일을 열고 다음 값을 수정하세요:

```bash
# .env.local
OPENAI_API_KEY=your-actual-openai-api-key-here
```

**OpenAI API 키 받는 방법:**
1. https://platform.openai.com/api-keys 접속
2. 로그인 후 "Create new secret key" 클릭
3. 생성된 키를 복사해서 `.env.local`에 붙여넣기

⚠️ **주의사항:**
- `.env.local` 파일은 절대 Git에 커밋하지 마세요!
- 이미 `.gitignore`에 추가되어 있습니다.

---

## 💻 로컬 개발 환경

### 사전 요구사항
- Python 3.11+
- PostgreSQL 15+
- pip

### 1️⃣ 가상환경 생성

```bash
cd backend

# 가상환경 생성
python -m venv venv

# 가상환경 활성화
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2️⃣ 패키지 설치

```bash
pip install -r requirements.txt
```

### 3️⃣ PostgreSQL 데이터베이스 생성

```bash
# PostgreSQL 접속
psql -U postgres

# 데이터베이스 생성
CREATE DATABASE bfai_db;
CREATE USER bfai_user WITH PASSWORD 'bfai_password';
GRANT ALL PRIVILEGES ON DATABASE bfai_db TO bfai_user;
\q
```

### 4️⃣ .env.local 수정 (로컬 개발용)

```bash
# Docker 없이 로컬 PostgreSQL 사용 시
DATABASE_URL=postgresql://bfai_user:bfai_password@localhost:5432/bfai_db
DB_HOST=localhost
```

### 5️⃣ 데이터베이스 초기화 및 CSV 임포트

```bash
# 테이블 생성
python -c "from app.database import init_db; init_db()"

# CSV 데이터 임포트
python scripts/import_csv.py
```

### 6️⃣ 서버 실행

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

서버 실행 확인:
- http://localhost:8000 - API 루트
- http://localhost:8000/docs - Swagger UI
- http://localhost:8000/health - 헬스체크

---

## 🐳 Docker로 실행 (권장)

### 사전 요구사항
- Docker Desktop 설치
- Docker Compose V2

### 1️⃣ .env.local 파일 준비

```bash
# backend/.env.local 파일에 실제 OpenAI API 키 입력
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
```

### 2️⃣ Docker Compose 실행

```bash
# backend 디렉토리에서
cd backend

# 컨테이너 빌드 및 실행
docker-compose up --build

# 백그라운드 실행
docker-compose up -d
```

### 3️⃣ 실행 확인

```bash
# 컨테이너 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs -f backend

# API 테스트
curl http://localhost:8000/health
```

### 4️⃣ CSV 데이터 임포트

```bash
# 컨테이너 내부에서 실행
docker-compose exec backend python scripts/import_csv.py
```

### 5️⃣ pgAdmin 사용 (선택)

개발 환경에서 데이터베이스 관리 도구 실행:

```bash
docker-compose --profile dev up
```

접속 정보:
- URL: http://localhost:5050
- Email: admin@bfai.com
- Password: admin

### 6️⃣ Docker 정리

```bash
# 컨테이너 중지
docker-compose down

# 볼륨까지 삭제 (데이터베이스 초기화)
docker-compose down -v

# 이미지까지 삭제
docker-compose down --rmi all
```

---

## 🚀 프로덕션 배포

### 1️⃣ .env.production 설정

```bash
# backend/.env.production 파일 수정
DB_PASSWORD=CHANGE_THIS_STRONG_PASSWORD
OPENAI_API_KEY=CHANGE_THIS_YOUR_OPENAI_API_KEY
CORS_ORIGINS=["https://your-domain.com"]
DEBUG=False
```

⚠️ **필수 변경 사항:**
- `DB_PASSWORD`: 강력한 비밀번호로 변경
- `OPENAI_API_KEY`: 실제 OpenAI API 키
- `CORS_ORIGINS`: 실제 프론트엔드 도메인
- `DEBUG`: 반드시 `False`

### 2️⃣ 프로덕션 실행

```bash
# .env.production 사용해서 실행
docker-compose --env-file .env.production up -d
```

### 3️⃣ 보안 체크리스트

- [ ] `DEBUG=False` 확인
- [ ] 강력한 DB 비밀번호 설정
- [ ] CORS 도메인 제한
- [ ] HTTPS 설정 (Nginx/Caddy 리버스 프록시)
- [ ] 방화벽 설정 (5432 포트 외부 차단)
- [ ] 정기 백업 설정
- [ ] 로그 모니터링 설정

---

## 🔍 문제 해결

### 1. OpenAI API 오류

```
Error: OpenAI API key not found
```

**해결:**
```bash
# .env.local 파일 확인
cat .env.local | grep OPENAI_API_KEY

# API 키가 없으면 추가
echo "OPENAI_API_KEY=sk-proj-xxxxx" >> .env.local
```

### 2. 데이터베이스 연결 실패

```
Error: could not connect to server
```

**해결:**
```bash
# PostgreSQL 실행 확인
docker-compose ps db

# 데이터베이스 로그 확인
docker-compose logs db

# 재시작
docker-compose restart db
```

### 3. CSV 인코딩 오류

```
UnicodeDecodeError: 'utf-8' codec can't decode
```

**해결:**
- `scripts/import_csv.py`에서 해당 CSV 파일의 인코딩을 `euc-kr`로 변경

### 4. 포트 충돌

```
Error: Bind for 0.0.0.0:8000 failed: port is already allocated
```

**해결:**
```bash
# 포트 사용 중인 프로세스 확인
# Windows
netstat -ano | findstr :8000

# macOS/Linux
lsof -i :8000

# 프로세스 종료 후 재시작
docker-compose down
docker-compose up
```

### 5. ChromaDB 오류

```
Error: ChromaDB collection not found
```

**해결:**
```bash
# data 디렉토리 삭제 후 재생성
rm -rf backend/data/chromadb
mkdir -p backend/data/chromadb

# 서버 재시작 (RAG 자동 초기화)
docker-compose restart backend
```

---

## 📚 추가 문서

- [API 문서](http://localhost:8000/docs) - Swagger UI
- [기획 문서](../기획/[최종] 비파이 실시간 길안내 서비스.md)
- [백엔드 가이드](../기획/[백엔드 완전 가이드] Open API + DB + 실전 활용법.md)

---

## 🆘 도움이 필요하신가요?

문제가 해결되지 않으면:
1. GitHub Issues 생성
2. 로그 파일 첨부 (`docker-compose logs backend`)
3. 환경 정보 공유 (OS, Docker 버전 등)

**Happy Coding! 💪**
