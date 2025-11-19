# 비파이(B-FAI) API 가이드

> **프론트엔드 개발자를 위한 상세 API 문서**

**Base URL**: `http://localhost:8000`
**Swagger UI**: http://localhost:8000/docs

---

## 전체 플로우

```
[앱 시작]
    │
    ▼
1. GET /api/route/stations
   → 역 목록 받아서 드롭다운 표시
    │
    ▼
2. 사용자가 출발역/도착역 선택, 엘리베이터 필요 여부 체크
    │
    ▼
3. POST /api/route/search
   → 경로 + 8개 체크포인트 (GPS 좌표 포함) 받음
    │
    ▼
4. 프론트: 8개 체크포인트 좌표 저장
    │
    ▼
5. GPS 모니터링 시작
    │
    ▼
6. 체크포인트 반경 30m 진입 감지
    │
    ▼
7. POST /api/checkpoint/guide
   → 해당 체크포인트 상세 안내 (TTS용 guide_text)
    │
    ▼
8. 다음 체크포인트로 이동... (반복)
```

---

## API 1: 역 목록 조회

### 요청
```http
GET /api/route/stations
```

### 응답
```json
{
  "stations": [
    {"station_id": 1, "name": "강남역", "line": "2호선", "lat": 37.498, "lon": 127.027},
    {"station_id": 2, "name": "잠실역", "line": "2호선", "lat": 37.513, "lon": 127.100}
  ]
}
```

---

## API 2: 경로 검색

### 요청
```http
POST /api/route/search
Content-Type: application/json
```

```json
{
  "start_station": "강남",
  "end_station": "잠실",
  "user_location": {
    "lat": 37.497952,
    "lon": 127.027619
  },
  "user_tags": {
    "mobility_level": "wheelchair",
    "need_elevator": true,
    "prefer_short": true,
    "need_charging_info": true
  }
}
```

### 요청 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| start_station | string | O | 출발역 이름 ("강남", "강남역" 둘 다 가능) |
| end_station | string | O | 도착역 이름 |
| user_location | object | O | 사용자 현재 GPS 좌표 |
| user_tags.mobility_level | string | X | "normal", "wheelchair", "cane" |
| user_tags.need_elevator | boolean | X | 엘리베이터 필요 여부 |
| user_tags.prefer_short | boolean | X | 최단 경로 선호 |
| user_tags.need_charging_info | boolean | X | 충전소 정보 필요 여부 |

### 응답
```json
{
  "route_id": 1,
  "start_station": "강남역",
  "end_station": "잠실역",
  "line": "2호선",
  "direction": "잠실 방면",
  "estimated_time_minutes": 15,
  "distance_meters": 8500,

  "walking_to_station": {
    "distance_meters": 120,
    "time_minutes": 2,
    "direction": "북쪽",
    "guide_text": "북쪽으로 약 120m 직진하시면 강남역 3번 출구가 있습니다.",
    "has_slope": true,
    "slope_warning": "가파른 경사로 주의",
    "landmarks": ["스타벅스"]
  },

  "start_exit": {
    "exit_number": "3",
    "has_elevator": true,
    "elevator_location": "출구 왼쪽 10m",
    "elevator_button_info": "지하 2층 버튼을 누르세요",
    "elevator_time_seconds": 60,
    "gps": {"lat": 37.49805, "lon": 127.0286275}
  },

  "end_exit": {
    "exit_number": "6",
    "has_elevator": true,
    "elevator_location": "잠실새내 방면 6-3",
    "elevator_button_info": "지상 1층 버튼을 누르세요",
    "elevator_time_seconds": 45,
    "gps": {"lat": 37.5132, "lon": 127.1001}
  },

  "recommended_car_start": 7,
  "recommended_car_end": 8,
  "recommended_car_reason": "6번 출구 엘리베이터와 가까운 위치",

  "realtime_train": {
    "arrival_minutes": 3,
    "arrival_seconds": 180,
    "arrival_message": "잠실새내 진입",
    "terminal_station": "잠실새내",
    "is_last_train": false,
    "current_location": "잠실새내 진입"
  },

  "checkpoints": [
    {
      "id": 0,
      "type": "출발지",
      "location": "현재 위치",
      "radius": 30,
      "data": {
        "next_destination": "강남역 3번 출구",
        "walking_distance": 120,
        "direction": "북쪽"
      }
    },
    {
      "id": 1,
      "type": "출발역_출구",
      "location": "강남역 3번 출구",
      "latitude": 37.49805,
      "longitude": 127.0286275,
      "radius": 30,
      "data": {
        "has_elevator": true,
        "elevator_location": "출구 왼쪽 10m"
      }
    },
    {
      "id": 2,
      "type": "출발역_승강장",
      "location": "2호선 잠실 방면 승강장"
    },
    {
      "id": 3,
      "type": "승강장_대기",
      "location": "7-8번째 칸 앞"
    },
    {
      "id": 4,
      "type": "열차_탑승",
      "location": "열차 내"
    },
    {
      "id": 5,
      "type": "도착역_승강장",
      "location": "잠실역 승강장"
    },
    {
      "id": 6,
      "type": "도착역_출구",
      "location": "잠실역 6번 출구",
      "latitude": 37.5132,
      "longitude": 127.1001
    },
    {
      "id": 7,
      "type": "충전소",
      "location": "휠체어 충전소",
      "optional": true
    }
  ],

  "status": "정상"
}
```

### 응답 필드 설명

| 필드 | 설명 | 프론트 사용 |
|------|------|-------------|
| walking_to_station | 출발지→출발역 도보 안내 | 첫 화면 표시 |
| start_exit/end_exit | 출구 상세 정보 | 엘리베이터 위치/버튼 안내 |
| recommended_car_* | 추천 탑승 칸 | 승강장 안내 화면 |
| realtime_train | 실시간 열차 도착 | 대기 화면 표시 |
| checkpoints | 8단계 체크포인트 | **GPS 좌표 저장 필수** |
| checkpoints[].latitude/longitude | 체크포인트 GPS | 위치 감지용 |
| checkpoints[].radius | 감지 반경 (기본 30m) | geofencing |

---

## API 3: 체크포인트 안내

### 요청
```http
POST /api/checkpoint/guide
Content-Type: application/json
```

```json
{
  "checkpoint_id": 1,
  "station_name": "강남역",
  "exit_number": "3",
  "line": "2호선",
  "direction": "잠실 방면",
  "need_elevator": true,
  "user_location": {
    "lat": 37.497952,
    "lon": 127.027619
  }
}
```

### 요청 필드 (체크포인트별)

| checkpoint_id | 필수 필드 |
|---------------|-----------|
| 0 (출발지) | station_name, exit_number, user_location |
| 1 (출발역 출구) | station_name, exit_number, need_elevator |
| 2 (승강장) | station_name, line, direction |
| 3 (대기) | station_name, line, direction |
| 4 (탑승) | station_name (도착역) |
| 5 (도착역 승강장) | station_name, exit_number |
| 6 (도착역 출구) | station_name, exit_number, need_elevator |
| 7 (충전소) | station_name |

### 응답
```json
{
  "checkpoint_id": 1,
  "checkpoint_type": "출입구",
  "guide_text": "강남역 3번 출구에 도착하셨습니다.\n\n엘리베이터 위치: 출구 왼쪽 10m\n지하 2층 버튼을 누르세요.\n약 1분 소요됩니다.\n\n엘리베이터 하차 후 왼쪽으로 직진하세요.",
  "status": "정상"
}
```

### guide_text 활용

- **TTS 음성 출력용**: `guide_text`를 그대로 TTS에 전달
- **화면 표시용**: `\n\n`으로 분리하여 섹션별 표시

---

## 체크포인트별 상세

### 0. 출발지
```json
{
  "checkpoint_id": 0,
  "checkpoint_type": "출발지",
  "guide_text": "현재 위치에서 강남역 3번 출구로 이동합니다.\n\n북쪽으로 약 120m 직진하세요.\n약 2분 소요됩니다.\n\n경사로 주의: 가파른 경사로가 있습니다.\n\n엘리베이터는 출구 왼쪽 10m에 있습니다."
}
```

### 1. 출발역 출구
```json
{
  "checkpoint_id": 1,
  "checkpoint_type": "출입구",
  "guide_text": "강남역 3번 출구에 도착하셨습니다.\n\n엘리베이터 위치: 출구 왼쪽 10m\n지하 2층 버튼을 누르세요.\n약 1분 소요됩니다.\n\n엘리베이터 하차 후 왼쪽으로 직진하세요."
}
```

### 2. 승강장
```json
{
  "checkpoint_id": 2,
  "checkpoint_type": "승강장",
  "guide_text": "2호선 잠실 방면 승강장입니다.\n\n7-8번째 칸 앞에서 대기해주세요.\n도착역 엘리베이터와 가장 가까운 위치입니다."
}
```

### 3. 승강장 대기 (실시간 정보)
```json
{
  "checkpoint_id": 3,
  "checkpoint_type": "승강장_대기",
  "guide_text": "강남역 2호선 잠실 방면 승강장입니다.\n\n7-8번째 칸 앞에서 대기해주세요.\n\n열차가 진입합니다!\n행선지: 잠실새내\n\n다음 열차: 약 5분 후"
}
```

### 4. 열차 탑승 (도착 알림)
```json
{
  "checkpoint_id": 4,
  "checkpoint_type": "열차_탑승",
  "guide_text": "열차 탑승 중입니다.\n\n곧 잠실역에 도착합니다!\n하차 준비를 해주세요.\n\n하차 후 우측으로 이동하세요."
}
```

### 5. 도착역 승강장
```json
{
  "checkpoint_id": 5,
  "checkpoint_type": "도착역_승강장",
  "guide_text": "잠실역에 도착하셨습니다.\n\n7-8번째 칸에서 하차 후 우측으로 가세요.\n\n엘리베이터 위치: 잠실새내 방면 6-3\n6번 출구로 나가실 수 있습니다.\n약 1분 소요됩니다."
}
```

### 6. 도착역 출구
```json
{
  "checkpoint_id": 6,
  "checkpoint_type": "도착역_출구",
  "guide_text": "잠실역 6번 출구입니다.\n\n엘리베이터 위치: 잠실새내 방면 6-3\n지상 1층 버튼을 누르세요.\n약 45초 소요됩니다.\n\n목적지에 도착하셨습니다!"
}
```

### 7. 충전소 (선택)
```json
{
  "checkpoint_id": 7,
  "checkpoint_type": "충전소",
  "guide_text": "잠실역 휠체어 충전소 안내\n\n위치: 대합실 6번 출구 방면\n운영 시간: 05:30 ~ 24:00\n\n현재 충전 가능합니다."
}
```

---

## 프론트엔드 구현 가이드

### 1. 체크포인트 GPS 저장

```javascript
// 경로 검색 응답 후
const checkpoints = response.checkpoints;

// GPS 좌표가 있는 체크포인트 저장
const gpsCheckpoints = checkpoints.filter(cp => cp.latitude && cp.longitude);

// 예: [{id: 1, lat: 37.49805, lon: 127.0286275, radius: 30}, ...]
```

### 2. 위치 모니터링

```javascript
// Geofencing으로 체크포인트 진입 감지
navigator.geolocation.watchPosition((position) => {
  const userLat = position.coords.latitude;
  const userLon = position.coords.longitude;

  gpsCheckpoints.forEach(cp => {
    const distance = calculateDistance(userLat, userLon, cp.lat, cp.lon);

    if (distance <= cp.radius) {
      // 체크포인트 도착 - API 호출
      fetchCheckpointGuide(cp.id);
    }
  });
});
```

### 3. 안내 표시 및 TTS

```javascript
async function fetchCheckpointGuide(checkpointId) {
  const response = await fetch('/api/checkpoint/guide', {
    method: 'POST',
    body: JSON.stringify({
      checkpoint_id: checkpointId,
      station_name: currentRoute.station_name,
      // ... 기타 필드
    })
  });

  const data = await response.json();

  // 화면 표시
  displayGuide(data.guide_text);

  // TTS 음성 출력
  speakText(data.guide_text);
}
```

---

## 에러 처리

### HTTP 상태 코드

| 코드 | 설명 |
|------|------|
| 200 | 성공 |
| 404 | 역을 찾을 수 없음 |
| 422 | 요청 필드 오류 |
| 500 | 서버 오류 |

### 에러 응답 예시

```json
{
  "detail": "역을 찾을 수 없습니다"
}
```

---

## Postman Collection

테스트용 Postman Collection: `BFAI_API_Collection.postman_collection.json`

Postman에서 Import하여 바로 테스트 가능합니다.

---

**작성일**: 2025-11-19
