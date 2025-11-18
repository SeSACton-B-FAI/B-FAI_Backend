# Git 레포지토리 재설정 가이드

## 🔄 backend 디렉토리의 Git 레포지토리 끊기

### Windows (PowerShell/CMD)
```powershell
# backend 디렉토리로 이동
cd backend

# .git 폴더 삭제 (숨김 폴더)
Remove-Item -Recurse -Force .git

# 확인
ls -Force  # .git 폴더가 없어야 함
```

### Linux/Mac/WSL
```bash
# backend 디렉토리로 이동
cd backend

# .git 폴더 삭제
rm -rf .git

# 확인
ls -la  # .git 폴더가 없어야 함
```

---

## 🆕 새로운 Git 레포지토리 생성

### 1. 로컬 Git 초기화
```bash
cd backend

# Git 초기화
git init

# 모든 파일 추가
git add .

# 첫 커밋
git commit -m "Initial commit: B-FAI backend with 11 Open APIs"
```

### 2. GitHub 레포지토리 생성 및 연결
```bash
# GitHub에서 새 레포지토리 생성 후

# 원격 저장소 추가
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

# 푸시
git branch -M main
git push -u origin main
```

---

## ✅ Git에 포함되는 파일 확인

### 포함되는 파일 (.gitignore 제외)
```
✅ .env.example          # 환경변수 템플릿
✅ .env.production       # 프로덕션 환경변수 (API 키 제외)
✅ README.md             # 프로젝트 문서
✅ API_GUIDE.md          # API 가이드
✅ docker-compose.yml    # Docker 설정
✅ requirements.txt      # Python 패키지
✅ app/                  # 소스 코드
✅ scripts/              # 스크립트
✅ static_data/          # CSV 데이터
```

### 제외되는 파일 (.gitignore 적용)
```
❌ .env                  # 실제 API 키 (보안!)
❌ .env.local            # 로컬 환경변수
❌ dynamic_data/일반인증키
❌ dynamic_data/지하철 실시간 인증키
❌ dynamic_data/*.pdf
❌ __pycache__/
❌ venv/
❌ data/chromadb/
❌ logs/
❌ *.log
```

---

## 🔍 Git 상태 확인

```bash
# 추적되지 않는 파일 확인
git status

# .gitignore가 제대로 작동하는지 확인
git check-ignore -v .env
git check-ignore -v dynamic_data/일반인증키

# 커밋 이력 확인
git log --oneline
```

---

## ⚠️ 주의사항

1. **API 키 노출 방지**
   - `.env` 파일은 절대 Git에 커밋하지 마세요
   - `dynamic_data/일반인증키`, `지하철 실시간 인증키` 파일도 제외됩니다

2. **민감한 정보 확인**
   ```bash
   # 커밋 전 확인
   git diff --cached
   
   # API 키가 포함되어 있는지 검색
   git grep -i "7854767a417373733432534e426264"
   ```

3. **이미 커밋된 민감한 정보 제거**
   ```bash
   # Git 히스토리에서 완전히 제거 (주의!)
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all
   
   # 강제 푸시 (주의!)
   git push origin --force --all
   ```

---

## 📝 .env.production 사용법

`.env.production`은 Git에 포함되지만, 실제 API 키는 포함하지 않습니다.

**배포 시:**
1. 서버에서 `.env.production` 복사
2. 실제 API 키로 교체
3. 환경변수로 로드

```bash
# 프로덕션 환경변수 사용
cp .env.production .env
nano .env  # API 키 입력

# Docker Compose 실행
docker-compose up -d
```

---

**작성일**: 2025-11-18  
**프로젝트**: 비파이(B-FAI) 실시간 길안내 서비스
