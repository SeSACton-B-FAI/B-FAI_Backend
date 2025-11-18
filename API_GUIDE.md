# 비파이(B-FAI) API 가이드 (프론트엔드용)

> **프론트엔드 개발자를 위한 API 상세 문서**

**Base URL**: `http://localhost:8000`  
**Swagger UI**: http://localhost:8000/docs

---

## 📋 목차

1. [전체 플로우](#전체-플로우)
2. [API 1: 경로 탐색](#api-1-경로-탐색)
3. [API 2: 체크포인트 안내](#api-2-체크포인트-안내)
4. [API 3: 실시간 정보](#api-3-실시간-정보)
5. [프론트엔드 통합 가이드](#프론트엔드-통합-가이드)
6. [에러 처리](#에러-처리)

---

## 🔄 전체 플로우

```
[앱 시작]
   ↓
출발지/목적지 입력
   ↓
Phase 1: 출발 전 질문 (2단계)
   ↓
Phase 2: 경로 탐색 API 호출
   ↓
Phase 3: GPS 추적 + 체크포인트 안내 API 호출
   ↓
[목적지 도착]
```

---

## API 1: 경로 탐색

### Endpoint
```http
POST /api/route/search
```

### 설명
사용자의 현재 위치와 조건에 따라 최적의 지하철 경로를 탐색합니다.
- GPS 기반 최적 출입구 선택
- 실시간 엘리베이터 상태 확인
- 최적 탑승 칸 계산
- 8개 체크포인트 자동 생성

### Request Body
```json
{
  "start_station": "강남",
  "end_station": "잠실",
  "user_location": {
    "latitude": 37.497952,
    "longitude": 127.027619
  },
  "user_tags": {
    "mobility_level": "wheelchair",
    "need_elevator": true,
    "prefer_short": true,
    "need_charging_info": false
  }
}
```

#### 파라미터 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `start_station` | string | ✅ | 출발역 이름 (예: "강남", "잠실") |
| `end_station` | string | ✅ | 도착역 이름 |
| `user_location.latitude` | float | ✅ | 사용자 현재 위도 |
| `user_location.longitude` | float | ✅ | 사용자 현재 경도 |
| `user_tags.mobility_level` | string | ✅ | "normal", "wheelchair", "walker" |
| `user_tags.need_elevator` | boolean | ✅ | 엘리베이터 필수 여부 |
| `user_tags.prefer_short` | boolean | ❌ | 짧은 경로 선호 (기본: true) |
| `user_tags.need_charging_info` | boolean | ❌ | 충전소 정보 필요 (기본: false) |

#### user_tags 생성 규칙

**질문 1: 계단 이용 가능?**
- "네, 가능해요" → `need_elevator: false`, `mobility_level: "normal"`
- "아니요, 어려워요" → 질문 2로 이동

**질문 2: 이동 보조 수단?** (계단 불가 시)
- "수동 휠체어" → `mobility_level: "wheelchair"`, `need_elevator: true`, `need_charging_info: false`
- "전동 휠체어" → `mobility_level: "wheelchair"`, `need_elevator: true`, `need_charging_info: true`
- "보행기" → `mobility_level: "walker"`, `need_elevator: true`, `need_charging_info: false`

### Response Body
```json
{
  "route_id": 1,
  "start_station": "강남역",
  "end_station": "잠실역",
  "line": "2호선",
  "direction": "잠실 방면",
  "estimated_time_minutes": 10,
  "distance_meters": 5000,
  "start_exit_number": "3",
  "start_exit_has_elevator": true,
  "start_exit_gps": {
    "lat": 37.497952,
    "lon": 127.027619
  },
  "end_exit_number": "4",
  "end_exit_has_elevator": true,
  "end_exit_gps": {
    "lat": 37.513294,
    "lon": 127.100388
  },
  "recommended_car_start": 7,
  "recommended_car_end": 8,
  "recommended_car_reason": "4번 출구 엘리베이터와 가까운 위치",
  "start_elevator_status": {
    "elevators": [...],
    "all_working": true
  },
  "end_elevator_status": {
    "elevators": [...],
    "all_working": true
  },
  "checkpoints": [
    {
      "id": 0,
      "type": "출발지",
      "location": "현재 위치",
      "radius": 30
    },
    {
      "id": 1,
      "type": "출발역_출구",
      "location": "강남역 3번 출구",
      "latitude": 37.497952,
      "longitude": 127.027619,
      "radius": 30,
      "data": {
        "has_elevator": true
      }
    },
    {
      "id": 2,
      "type": "출발역_승강장",
      "location": "강남역 승강장 (잠실 방면)",
      "latitude": 37.497952,
      "longitude": 127.027619,
      "radius": 30,
      "data": {
        "direction": "잠실 방면",
        "recommended_car": "7-8번째 칸"
      }
    },
    {
      "id": 3,
      "type": "승강장_대기",
      "location": "승강장 대기",
      "radius": 0
    },
    {
      "id": 4,
      "type": "열차_탑승",
      "location": "열차 탑승",
      "radius": 0
    },
    {
      "id": 5,
      "type": "도착역_승강장",
      "location": "잠실역 승강장",
      "latitude": 37.513294,
      "longitude": 127.100388,
      "radius": 30
    },
    {
      "id": 6,
      "type": "도착역_출구",
      "location": "잠실역 4번 출구",
      "latitude": 37.513294,
      "longitude": 127.100388,
      "radius": 30,
      "data": {
        "has_elevator": true
      }
    },
    {
      "id": 7,
      "type": "충전소",
      "location": "잠실역 휠체어 충전소",
      "latitude": 37.513294,
      "longitude": 127.100388,
      "radius": 50,
      "data": {
        "floor": "B1",
        "count": 2,
        "location_desc": "3, 4번 출구쪽"
      }
    }
  ],
  "status": "정상",
  "warnings": []
}
```

#### 응답 필드 활용

| 필드 | 화면 표시 용도 |
|------|--------------|
| `start_station` + `start_exit_number` | "강남역 3번 출구로 이동하세요" |
| `start_exit_has_elevator` | "엘리베이터 있음" 아이콘 표시 |
| `start_exit_gps` | 지도에 출발 출구 마커 표시 |
| `line` + `direction` | "2호선 잠실 방면 탑승" |
| `recommended_car_start` ~ `end` | "7-8번째 칸에 탑승하세요" |
| `recommended_car_reason` | "도착역 엘리베이터와 가까워요" |
| `checkpoints[]` | GPS 추적용 저장 (전체 배열) |
| `warnings[]` | 경고 메시지 표시 (예: "엘리베이터 고장") |

---

## API 2: 체크포인트 안내

### Endpoint
```http
POST /api/checkpoint/guide
```

### 설명
체크포인트 도착 시 노인 친화적 안내문을 생성합니다.
- RAG 5단계 처리: DB → Open API → RAG 검색 → GPT-4 → TTS
- 실시간 상태 반영 (엘리베이터 고장, 출입구 폐쇄)
- 대체 경로 자동 제공

### Request Body
```json
{
  "checkpoint_id": 1,
  "station_name": "강남",
  "exit_number": "3",
  "platform_direction": null,
  "need_elevator": true
}
```

#### 파라미터 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `checkpoint_id` | integer | ✅ | 체크포인트 ID (0~7) |
| `station_name` | string | ✅ | 역 이름 (예: "강남") |
| `exit_number` | string | ❌ | 출입구 번호 (출입구 체크포인트만) |
| `platform_direction` | string | ❌ | 승강장 방면 (승강장 체크포인트만) |
| `need_elevator` | boolean | ✅ | 엘리베이터 필요 여부 |

#### 체크포인트별 파라미터

| checkpoint_id | type | exit_number | platform_direction |
|--------------|------|-------------|-------------------|
| 0 | 출발지 | null | null |
| 1 | 출발역_출구 | "3" | null |
| 2 | 출발역_승강장 | null | "잠실 방면" |
| 3 | 승강장_대기 | null | null |
| 4 | 열차_탑승 | null | null |
| 5 | 도착역_승강장 | null | null |
| 6 | 도착역_출구 | "4" | null |
| 7 | 충전소 | null | null |

### Response Body
```json
{
  "checkpoint_id": 1,
  "checkpoint_type": "출입구",
  "guide_text": "🚇 강남역 3번 출구에 도착하셨습니다.\n\n🛗 엘리베이터는 출구 왼쪽 10m에 있습니다. 지상에서 지하1층까지 운행 중이며, 현재 정상 작동 중입니다.\n\n📍 엘리베이터를 타고 지하1층으로 내려가신 후, 잠실 방면 승강장으로 이동해주세요.",
  "status": "정상",
  "db_data": {
    "exit_number": "3",
    "has_elevator": true,
    "elevator_type": "외부E/V",
    "description": "출구 왼쪽 10m",
    "floor_level": "B1",
    "gps": {
      "lat": 37.497952,
      "lon": 127.027619
    },
    "facilities": {
      "has_nursing_room": true,
      "has_meeting_place": false,
      "has_auto_kiosk": true
    }
  },
  "api_data": {
    "elevator_status": {
      "all_working": true
    },
    "elevator_details": [
      {
        "location": "출구 왼쪽 10m",
        "floor_info": "지상 ~ 지하1층",
        "status": "정상",
        "last_check": "2025-11-17"
      }
    ],
    "exit_closure": {
      "is_closed": false
    }
  },
  "alternative_route": null
}
```

#### 응답 필드 활용

| 필드 | 화면 표시 용도 |
|------|--------------|
| `guide_text` | TTS 음성 재생 + 화면 텍스트 표시 |
| `status` | "정상", "주의", "경고" 상태 표시 |
| `alternative_route` | 대체 경로 안내 (엘리베이터 고장 시) |

---

## API 3: 실시간 정보

### Endpoint
```http
GET /api/checkpoint/realtime/{station_name}
```

### 설명
역의 실시간 정보를 조회합니다.
- 엘리베이터 상태
- 출입구 폐쇄 여부
- 휠체어 충전소 위치

### Request
```http
GET /api/checkpoint/realtime/강남
```

### Response Body
```json
{
  "station": "강남",
  "elevator_status": {
    "elevators": [
      {
        "location": "3번 출구",
        "floor_info": "지상 ~ 지하1층",
        "status": "정상",
        "last_check": "2025-11-17"
      }
    ],
    "all_working": true
  },
  "exit_closures": {
    "is_closed": false,
    "closed_exits": []
  },
  "chargers": [
    {
      "station": "강남",
      "floor": "B1",
      "count": 1,
      "location": "3, 4번 출구쪽"
    }
  ]
}
```

---

## 🎨 프론트엔드 통합 가이드

### Phase 1: 출발 전 질문

#### 질문 1: 계단 이용 가능?
```typescript
const question1 = "계단을 이용하실 수 있나요?";
const options = ["네, 가능해요", "아니요, 어려워요"];

if (answer === "네, 가능해요") {
  userTags = {
    mobility_level: "normal",
    need_elevator: false,
    prefer_short: true,
    need_charging_info: false
  };
  // Phase 2로 이동
} else {
  // 질문 2로 이동
}
```

#### 질문 2: 이동 보조 수단?
```typescript
const question2 = "어떤 이동 보조 수단을 사용하시나요?";
const options = ["수동 휠체어", "전동 휠체어", "보행기"];

switch (answer) {
  case "수동 휠체어":
    userTags = {
      mobility_level: "wheelchair",
      need_elevator: true,
      prefer_short: true,
      need_charging_info: false
    };
    break;
  case "전동 휠체어":
    userTags = {
      mobility_level: "wheelchair",
      need_elevator: true,
      prefer_short: true,
      need_charging_info: true
    };
    break;
  case "보행기":
    userTags = {
      mobility_level: "walker",
      need_elevator: true,
      prefer_short: true,
      need_charging_info: false
    };
    break;
}
// Phase 2로 이동
```

### Phase 2: 경로 탐색

```typescript
const response = await fetch('http://localhost:8000/api/route/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    start_station: '강남',
    end_station: '잠실',
    user_location: {
      latitude: currentLat,
      longitude: currentLon
    },
    user_tags: userTags
  })
});

const route = await response.json();

// 경로 정보 저장
saveRoute(route);

// 화면 표시
displayRoute({
  startExit: `${route.start_station} ${route.start_exit_number}번 출구`,
  endExit: `${route.end_station} ${route.end_exit_number}번 출구`,
  line: route.line,
  direction: route.direction,
  recommendedCar: `${route.recommended_car_start}-${route.recommended_car_end}번째 칸`,
  checkpoints: route.checkpoints
});
```

### Phase 3: GPS 추적 및 체크포인트 안내

```typescript
// GPS 추적 시작
let currentCheckpointIndex = 0;
const checkpoints = route.checkpoints;

setInterval(async () => {
  const currentLocation = await getCurrentGPS();
  const nextCheckpoint = checkpoints[currentCheckpointIndex];
  
  // GPS 좌표가 있는 체크포인트만 거리 계산
  if (nextCheckpoint.latitude && nextCheckpoint.longitude) {
    const distance = calculateDistance(
      currentLocation.lat,
      currentLocation.lon,
      nextCheckpoint.latitude,
      nextCheckpoint.longitude
    );
    
    // 30m 이내 도착
    if (distance <= nextCheckpoint.radius) {
      await showCheckpointGuide(nextCheckpoint);
      currentCheckpointIndex++;
    }
  } else {
    // GPS 없는 체크포인트 (승강장_대기, 열차_탑승)
    // 타이머 또는 사용자 버튼으로 처리
    if (userClickedNext) {
      await showCheckpointGuide(nextCheckpoint);
      currentCheckpointIndex++;
    }
  }
}, 1000); // 1초마다 확인

// 체크포인트 안내 표시
async function showCheckpointGuide(checkpoint) {
  const response = await fetch('http://localhost:8000/api/checkpoint/guide', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      checkpoint_id: checkpoint.id,
      station_name: checkpoint.location.split('역')[0],
      exit_number: checkpoint.data?.exit_number || null,
      platform_direction: checkpoint.data?.direction || null,
      need_elevator: userTags.need_elevator
    })
  });
  
  const guide = await response.json();
  
  // TTS 음성 재생
  speakText(guide.guide_text);
  
  // 화면에 텍스트 표시
  displayGuideText(guide.guide_text);
  
  // 대체 경로가 있으면 표시
  if (guide.alternative_route) {
    showAlternativeRoute(guide.alternative_route);
  }
}
```

### Haversine 거리 계산 함수

```typescript
function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371e3; // 지구 반지름 (미터)
  const φ1 = lat1 * Math.PI / 180;
  const φ2 = lat2 * Math.PI / 180;
  const Δφ = (lat2 - lat1) * Math.PI / 180;
  const Δλ = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c; // 미터 단위
}
```

---

## ⚠️ 에러 처리

### 에러 응답 형식
```json
{
  "detail": "역을 찾을 수 없습니다",
  "error_code": "STATION_NOT_FOUND"
}
```

### 에러 코드

| 코드 | 메시지 | 처리 방법 |
|------|--------|----------|
| `STATION_NOT_FOUND` | 역을 찾을 수 없습니다 | 역 이름 확인 후 재시도 |
| `NO_ROUTE_FOUND` | 경로를 찾을 수 없습니다 | 다른 경로 제안 |
| `ELEVATOR_REQUIRED` | 엘리베이터가 필요하지만 없습니다 | 대체 역 제안 |
| `API_ERROR` | 외부 API 오류 | 잠시 후 재시도 |
| `RAG_ERROR` | 안내문 생성 실패 | 기본 안내문 표시 |

### 에러 처리 예제

```typescript
try {
  const response = await fetch('http://localhost:8000/api/route/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestData)
  });
  
  if (!response.ok) {
    const error = await response.json();
    
    switch (error.error_code) {
      case 'STATION_NOT_FOUND':
        showError('역을 찾을 수 없습니다. 역 이름을 확인해주세요.');
        break;
      case 'ELEVATOR_REQUIRED':
        showError('엘리베이터가 없는 역입니다. 다른 출구를 찾고 있습니다...');
        // 대체 경로 요청
        break;
      default:
        showError('오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
    }
    return;
  }
  
  const route = await response.json();
  // 정상 처리
  
} catch (error) {
  showError('네트워크 오류가 발생했습니다.');
}
```

---

## 📚 추가 리소스

- **Swagger UI**: http://localhost:8000/docs (대화형 API 테스트)
- **Postman 컬렉션**: `POSTMAN_COLLECTION.json` 파일 Import
- **기획 문서**: `../기획/[최종] 비파이 실시간 길안내 서비스.md`

---

**작성일**: 2025-11-18  
**프로젝트**: 비파이(B-FAI) 실시간 길안내 서비스
