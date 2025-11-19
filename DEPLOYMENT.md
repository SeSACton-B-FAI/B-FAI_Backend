# 🚀 비파이(B-FAI) 배포 가이드 (SOLID Cloud)

> **SOLID Cloud 전용 배포 가이드**  
> OpenVPN을 통한 내부 네트워크 접속 방식

---

## 🌐 1. SOLID Cloud 특징

### 네트워크 구조
```
인터넷
   ↓
OpenVPN 서버
   ↓
내부 네트워크 (10.0.11.x)
   ↓
SOLID Cloud 인스턴스 (10.0.11.234)
```

### 주요 특징
- ✅ **내부 IP**: 10.0.11.234 (고정)
- ✅ **접속 방식**: OpenVPN 필수
- ✅ **외부 접근**: OpenVPN 연결 시에만 가능
- ⚠️ **공인 IP 없음**: 일반 인터넷에서 직접 접속 불가

### AWS와의 차이점

| 항목 | AWS EC2 | SOLID Cloud |
|------|---------|-------------|
| IP 주소 | 공인 IP (탄력적 IP) | 내부 IP (10.0.11.234) |
| 외부 접속 | 직접 가능 | OpenVPN 필수 |
| 비용 | 시간당 과금 | 무료 (새싹톤 제공) |
| 보안 그룹 | AWS Security Group | 자체 방화벽 |

---

## 📦 2. 사전 준비물

### 2.1 API 키 3개 발급

| API 키 | 발급처 | 용도 |
|--------|--------|------|
| Seoul Open API (일반) | https://data.seoul.go.kr | 엘리베이터, 출입구 정보 |
| Seoul Open API (실시간) | https://data.seoul.go.kr | 실시간 열차 도착 정보 |
| OpenAI API (선택) | https://platform.openai.com | RAG 고품질 안내문 |

### 2.2 OpenVPN 클라이언트 설치

**Windows:**
```
1. OpenVPN GUI 다운로드: https://openvpn.net/community-downloads/
2. 설치 후 실행
3. 새싹톤에서 제공받은 .ovpn 파일 import
4. 연결 클릭
```

**Mac:**
```
1. Tunnelblick 다운로드: https://tunnelblick.net/
2. 설치 후 .ovpn 파일 드래그
3. 연결 클릭
```

**Linux:**
```bash
sudo apt install -y openvpn
sudo openvpn --config your-config.ovpn
```

---

## 🔍 3. 네트워크 연결 확인

### 3.1 OpenVPN 연결 확인

```bash
# Windows (PowerShell)
ipconfig | findstr "10.0.11"

# Mac/Linux
ifconfig | grep "10.0.11"
ip addr show | grep "10.0.11"

# 출력 예시:
# inet 10.0.11.xxx netmask 0xffffff00 broadcast 10.0.11.255
```

### 3.2 인스턴스 접속 테스트

```bash
# Ping 테스트
ping 10.0.11.234

# 출력 예시:
# Reply from 10.0.11.234: bytes=32 time=10ms TTL=64
# ✅ 응답 있으면 연결 성공!
# ❌ Request timeout이면 OpenVPN 재연결

# SSH 접속 테스트
ssh user@10.0.11.234
# 비밀번호 입력 또는 SSH 키 사용
```

### 3.3 외부 통신 확인 (인스턴스 내부에서)

```bash
# 인스턴스에 SSH 접속 후 실행

# 1. 인터넷 연결 확인
ping -c 3 8.8.8.8
# ✅ 응답 있으면 외부 통신 가능

# 2. DNS 확인
ping -c 3 google.com
# ✅ 응답 있으면 DNS 정상

# 3. Seoul Open API 접속 테스트
curl -I http://openapi.seoul.go.kr
# HTTP/1.1 200 OK
# ✅ 200 응답이면 API 호출 가능
```

---

## ⚡ 4. 배포 명령어 (5분 완료)

### Step 1: OpenVPN 연결

```bash
# 1. OpenVPN 클라이언트 실행
# 2. .ovpn 파일로 연결
# 3. 연결 확인
ping 10.0.11.234
```

### Step 2: SSH 접속

```bash
# SOLID Cloud 인스턴스 접속
ssh user@10.0.11.234
# 비밀번호 입력
```

### Step 3: 필수 패키지 설치

```bash
# ============================================
# Docker 설치
# ============================================
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# 설치 확인
docker --version
# Docker version 24.0.0 이상

# ============================================
# Docker Compose 설치
# ============================================
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 설치 확인
docker-compose --version
# docker-compose version 2.0.0 이상

# ============================================
# Git 설치 (선택)
# ============================================
sudo apt update
sudo apt install -y git

# 설치 확인
git --version
```

### Step 4: 프로젝트 업로드

```bash
# 방법 1: Git 클론 (추천)
mkdir -p ~/bfai && cd ~/bfai
git clone https://github.com/your-repo/bfai.git .

# 방법 2: SCP로 파일 업로드 (로컬에서 실행)
# OpenVPN 연결 후 로컬 터미널에서:
scp -r backend/ user@10.0.11.234:~/bfai/
```

### Step 5: 환경 변수 설정

```bash
cd ~/bfai/backend
cp .env.production .env
nano .env

# 필수 수정:
# SEOUL_OPEN_API_KEY=여기에_일반_인증키
# SEOUL_REALTIME_API_KEY=여기에_실시간_인증키
# OPENAI_API_KEY=sk-proj-여기에_OpenAI_키 (선택)
# DB_PASSWORD=보안을_위해_변경 (권장)

# 저장: Ctrl+O, Enter, Ctrl+X
```

### Step 6: Docker 실행

```bash
cd ~/bfai/backend

# Docker Compose 빌드 및 실행
docker-compose up -d --build

# 로그 확인 (정상 실행 확인)
docker-compose logs -f backend

# 출력 예시:
# ✅ Database initialized
# ✅ RAG knowledge base initialized
# 📡 Server running on 0.0.0.0:8000

# Ctrl+C로 로그 종료
```

### Step 7: 데이터 임포트

```bash
# CSV 데이터 임포트 (필수)
docker-compose exec backend python scripts/import_csv.py

# 출력 예시:
# ✅ Imported 50+ stations
# ✅ Imported 200+ exits
# ✅ Imported 1000+ platform edges

# 배리어프리 상세 데이터 (선택, 권장)
docker-compose exec backend python scripts/populate_barrier_free_data.py

# 서버 재시작
docker-compose restart backend
```

### Step 8: 접속 테스트

```bash
# 인스턴스 내부에서 테스트
curl http://localhost:8000/health
# {"status": "healthy", "database": "connected"}

# 로컬 PC에서 테스트 (OpenVPN 연결 상태)
curl http://10.0.11.234:8000/health
# {"status": "healthy", "database": "connected"}

# 브라우저에서 API 문서 확인
# http://10.0.11.234:8000/docs
```

---

## 🔗 5. 프론트엔드 연동

### 5.1 프론트엔드 개발자 요구사항

```
✅ OpenVPN 클라이언트 설치 필수
✅ OpenVPN 연결 후 개발 가능
✅ API Base URL: http://10.0.11.234:8000
```

### 5.2 프론트엔드 환경 변수 설정

```javascript
// .env.local (프론트엔드)
REACT_APP_API_BASE_URL=http://10.0.11.234:8000
NEXT_PUBLIC_API_BASE_URL=http://10.0.11.234:8000
VITE_API_BASE_URL=http://10.0.11.234:8000
```

### 5.3 CORS 설정 확인

```bash
# backend/.env 파일 확인
cat ~/bfai/backend/.env | grep CORS

# 출력:
# CORS_ORIGINS=*  # 모든 도메인 허용 (이미 설정됨)
```

### 5.4 프론트엔드 접속 테스트

```javascript
// 프론트엔드에서 테스트 (OpenVPN 연결 상태)
fetch('http://10.0.11.234:8000/health')
  .then(res => res.json())
  .then(data => console.log(data))
  .catch(err => console.error('연결 실패:', err));

// 성공 시 출력:
// {status: "healthy", database: "connected"}
```

### 5.5 프론트엔드 개발 워크플로우

```
1. OpenVPN 연결
2. 프론트엔드 개발 서버 실행 (npm run dev)
3. http://10.0.11.234:8000 API 호출
4. 개발 완료 후 OpenVPN 연결 해제 가능
```

---

## ✅ 6. 배포 완료 체크

### 6.1 인스턴스 내부 확인

```bash
# SSH 접속 후 실행

# 1. Docker 컨테이너 상태
docker-compose ps
# bfai-backend    Up
# bfai-db         Up

# 2. DB 데이터 확인
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import Station, Exit
db = SessionLocal()
print(f'Stations: {db.query(Station).count()}')
print(f'Exits: {db.query(Exit).count()}')
"
# Stations: 50+
# Exits: 200+

# 3. 로그 확인
docker-compose logs backend --tail=50
```

### 6.2 로컬 PC에서 확인 (OpenVPN 연결)

```bash
# 1. Ping 테스트
ping 10.0.11.234

# 2. 헬스 체크
curl http://10.0.11.234:8000/health

# 3. API 문서 접속
# 브라우저: http://10.0.11.234:8000/docs

# 4. 경로 검색 테스트
curl -X POST http://10.0.11.234:8000/api/route/search \
  -H "Content-Type: application/json" \
  -d '{
    "start_station": "강남역",
    "end_station": "잠실역",
    "user_location": {"lat": 37.497952, "lon": 127.027619},
    "user_tags": {
      "mobility_level": "wheelchair",
      "need_elevator": true,
      "prefer_short": true,
      "need_charging_info": false
    }
  }'
```

---

## 🔧 7. 자주 쓰는 명령어

```bash
# OpenVPN 연결 후 SSH 접속
ssh user@10.0.11.234

# 서버 재시작
cd ~/bfai/backend
docker-compose restart backend

# 로그 확인
docker-compose logs -f backend

# 서버 중지
docker-compose down

# 서버 시작
docker-compose up -d

# 업데이트 배포
git pull origin main
docker-compose up -d --build
```

---

## 🚨 8. 트러블슈팅

### 문제 1: OpenVPN 연결 안 됨

```bash
# 증상: ping 10.0.11.234 실패

# 해결:
1. OpenVPN 클라이언트 재시작
2. .ovpn 파일 재import
3. 네트워크 어댑터 확인 (Windows: 네트워크 설정)
4. 방화벽 확인 (OpenVPN 허용)
```

### 문제 2: SSH 접속 안 됨

```bash
# 증상: ssh user@10.0.11.234 실패

# 해결:
1. OpenVPN 연결 확인
   ping 10.0.11.234

2. SSH 포트 확인 (기본 22)
   telnet 10.0.11.234 22

3. 비밀번호 확인 (새싹톤 제공 정보)

4. SSH 키 사용 시
   ssh -i your-key.pem user@10.0.11.234
```

### 문제 3: 프론트엔드에서 API 호출 실패

```bash
# 증상: fetch() 에러, CORS 에러

# 해결:
1. OpenVPN 연결 확인
   ping 10.0.11.234

2. 백엔드 서버 실행 확인
   curl http://10.0.11.234:8000/health

3. CORS 설정 확인
   cat ~/bfai/backend/.env | grep CORS
   # CORS_ORIGINS=* 확인

4. 브라우저 콘솔 확인
   # Network 탭에서 요청 상태 확인
```

### 문제 4: Docker 빌드 실패

```bash
# 증상: docker-compose up 실패

# 해결:
1. Docker 설치 확인
   docker --version

2. 권한 확인
   sudo usermod -aG docker $USER
   newgrp docker

3. 디스크 공간 확인
   df -h

4. 로그 확인
   docker-compose logs
```

### 문제 5: 외부 API 호출 실패 (Seoul Open API)

```bash
# 증상: 엘리베이터 정보 조회 실패

# 해결:
1. 인스턴스 외부 통신 확인
   ping 8.8.8.8
   curl -I http://openapi.seoul.go.kr

2. API 키 확인
   cat ~/bfai/backend/.env | grep API_KEY

3. API 키 테스트
   curl "http://openapi.seoul.go.kr:8088/YOUR_KEY/json/SeoulMetroFaciInfo/1/5/"
```

---

## 📋 9. 배포 체크리스트

### 배포 전
- [ ] OpenVPN 클라이언트 설치
- [ ] .ovpn 파일 받기 (새싹톤)
- [ ] Seoul Open API 키 2개 발급
- [ ] OpenAI API 키 발급 (선택)

### 배포 중
- [ ] OpenVPN 연결 성공 (`ping 10.0.11.234`)
- [ ] SSH 접속 성공
- [ ] Docker & Docker Compose 설치
- [ ] 프로젝트 파일 업로드
- [ ] .env 파일 설정
- [ ] `docker-compose up -d` 성공
- [ ] CSV 데이터 임포트 완료

### 배포 후
- [ ] `curl http://localhost:8000/health` 성공 (인스턴스 내부)
- [ ] `curl http://10.0.11.234:8000/health` 성공 (로컬 PC)
- [ ] API 문서 접속 (`http://10.0.11.234:8000/docs`)
- [ ] 프론트엔드 연동 테스트 성공

---

## 📞 10. 도움말

### API 접속 정보
```
Base URL: http://10.0.11.234:8000
API 문서: http://10.0.11.234:8000/docs
헬스 체크: http://10.0.11.234:8000/health
```

### 주의사항
```
⚠️ OpenVPN 연결 필수!
⚠️ 공인 IP 없음 (내부 IP만)
⚠️ 프론트엔드 개발자도 OpenVPN 필요
⚠️ OpenVPN 연결 해제 시 API 접속 불가
```

### 참고 문서
- Postman Collection: `BFAI_API_Collection.postman_collection.json`
- AWS 배포 가이드: `AWS_DEPLOYMENT.md` (참고용)
- GitHub: https://github.com/your-repo/bfai

---

**SOLID Cloud 배포 완료! 🎉**

**다음 단계:**
1. 프론트엔드 팀에 IP 공유 (10.0.11.234)
2. OpenVPN 설정 파일 공유
3. API 문서 공유 (http://10.0.11.234:8000/docs)
4. 프론트엔드 연동 테스트
