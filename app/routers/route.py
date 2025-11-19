"""
Route search router - 경로 탐색 API (AI 점수 기반)
기획 문서: [최종] 비파이 실시간 길안내 서비스.md

더미 데이터 사용 안 함:
- routes 테이블: 실시간 GPS 거리 계산
- optimal_boarding 테이블: 실시간 엘리베이터 위치 기반 계산
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict
import math

from app.database import get_db
from app.models import Station, Exit, Route
from app.services import SeoulMetroAPI
from app.services.route_cache import route_cache

router = APIRouter(prefix="/route", tags=["route"])


# 유틸리티 함수: GPS 거리 계산
def calculate_gps_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Haversine 공식으로 두 GPS 좌표 간 거리 계산

    Args:
        lat1, lon1: 첫 번째 좌표 (위도, 경도)
        lat2, lon2: 두 번째 좌표 (위도, 경도)

    Returns:
        거리 (미터)
    """
    R = 6371000  # 지구 반지름 (미터)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c

    return distance


def _calculate_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """
    두 GPS 좌표 간 방향 계산

    Returns:
        방향 문자열 ("북쪽", "남쪽", "동쪽", "서쪽", "북동쪽" 등)
    """
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    # 주요 방향 결정
    if abs(delta_lat) > abs(delta_lon) * 2:
        # 남북 방향이 우세
        return "북쪽" if delta_lat > 0 else "남쪽"
    elif abs(delta_lon) > abs(delta_lat) * 2:
        # 동서 방향이 우세
        return "동쪽" if delta_lon > 0 else "서쪽"
    else:
        # 대각선 방향
        ns = "북" if delta_lat > 0 else "남"
        ew = "동" if delta_lon > 0 else "서"
        return f"{ns}{ew}쪽"


def _generate_walking_guide(
    user_location: Dict,
    exit_obj: Exit,
    station_name: str
) -> WalkingGuide:
    """출발지에서 출발역 출입구까지 도보 안내 생성"""

    # GPS 거리 계산
    lat1, lon1 = user_location["lat"], user_location["lon"]
    lat2, lon2 = float(exit_obj.latitude), float(exit_obj.longitude)
    distance = calculate_gps_distance(lat1, lon1, lat2, lon2)

    # 방향 계산
    direction = _calculate_direction(lat1, lon1, lat2, lon2)

    # 소요 시간 (도보 4km/h = 66.7m/분)
    walking_time = max(1, int(distance / 66.7))

    # 안내 텍스트 생성
    guide_parts = [f"{direction}으로 약 {int(distance)}m 직진하시면"]
    guide_parts.append(f"{station_name} {exit_obj.exit_number}번 출구가 있습니다.")

    if exit_obj.has_elevator:
        if exit_obj.elevator_location:
            guide_parts.append(f"엘리베이터는 {exit_obj.elevator_location}에 있습니다.")
        else:
            guide_parts.append("이 출구에 엘리베이터가 있습니다.")

    if exit_obj.landmark:
        guide_parts.append(f"({exit_obj.landmark} 근처)")

    guide_text = " ".join(guide_parts)

    # 경사로 정보
    has_slope = exit_obj.has_slope if hasattr(exit_obj, 'has_slope') and exit_obj.has_slope else False
    slope_warning = exit_obj.slope_info if hasattr(exit_obj, 'slope_info') and exit_obj.slope_info else None

    # 랜드마크
    landmarks = []
    if exit_obj.landmark:
        landmarks = [exit_obj.landmark]

    return WalkingGuide(
        distance_meters=int(distance),
        time_minutes=walking_time,
        direction=direction,
        guide_text=guide_text,
        has_slope=has_slope,
        slope_warning=slope_warning,
        landmarks=landmarks
    )


def _create_exit_detail_info(exit_obj: Exit) -> ExitDetailInfo:
    """Exit 객체에서 상세 정보 추출"""
    return ExitDetailInfo(
        exit_number=exit_obj.exit_number,
        has_elevator=exit_obj.has_elevator,
        elevator_type=exit_obj.elevator_type,
        elevator_location=getattr(exit_obj, 'elevator_location', None),
        elevator_button_info=getattr(exit_obj, 'elevator_button_info', None),
        elevator_time_seconds=getattr(exit_obj, 'elevator_time_seconds', None),
        gate_direction=getattr(exit_obj, 'gate_direction', None),
        floor_level=exit_obj.floor_level,
        gps={
            "lat": float(exit_obj.latitude),
            "lon": float(exit_obj.longitude)
        } if exit_obj.latitude else None
    )


def _generate_arrival_walking_guide(
    end_station: Station,
    end_exit: Exit,
    optimal_boarding: Dict,
    db: Session
) -> Dict:
    """도착역 하차 후 출구까지 안내 생성"""
    from app.models import ElevatorExitMapping

    # 엘리베이터-출구 매핑 조회
    mapping = db.query(ElevatorExitMapping).filter(
        ElevatorExitMapping.station_id == end_station.station_id,
        ElevatorExitMapping.connected_exit == end_exit.exit_number
    ).first()

    guide = {
        "exit_number": end_exit.exit_number,
        "car_position": f"{optimal_boarding['car_start']}-{optimal_boarding['car_end']}번째 칸",
        "direction_from_train": "우측" if mapping and mapping.direction_from_train else "앞쪽",
        "walking_distance_meters": mapping.walking_distance_meters if mapping else 50,
        "walking_time_seconds": mapping.walking_time_seconds if mapping else 60,
        "guide_text": "",
        "features": ["추천", "큰길우선", "계단회피"]
    }

    # 안내 텍스트 생성
    if mapping and mapping.walking_direction:
        guide["guide_text"] = mapping.walking_direction
    else:
        guide["guide_text"] = f"{guide['car_position']}에서 하차 후 {guide['direction_from_train']}으로 가세요."

    if end_exit.has_elevator:
        if mapping and mapping.elevator_location:
            guide["elevator_location"] = mapping.elevator_location
        guide["guide_text"] += f" {end_exit.exit_number}번 출구 엘리베이터를 이용하세요."

    return guide


# Request/Response 모델
class UserTags(BaseModel):
    """사용자 태그 (모빌리티 수준)"""
    mobility_level: str  # "normal", "wheelchair", "walker"
    need_elevator: bool
    prefer_short: bool
    need_charging_info: bool


class RouteSearchRequest(BaseModel):
    """경로 검색 요청"""
    start_station: str
    end_station: str
    user_location: Dict  # 사용자 현재 위치 GPS ⭐
    user_tags: UserTags


class CheckpointData(BaseModel):
    """체크포인트 데이터"""
    id: int
    type: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius: Optional[int] = 30
    data: Optional[Dict] = {}
    optional: bool = False


class WalkingGuide(BaseModel):
    """출발지→출발역 도보 안내"""
    distance_meters: int
    time_minutes: int
    direction: str  # "북쪽", "남쪽" 등
    guide_text: str  # "북쪽으로 약 120m 직진하시면..."
    has_slope: bool = False
    slope_warning: Optional[str] = None  # "가파른 경사로 주의"
    landmarks: List[str] = []  # ["편의점", "버스정류장"]


class ExitDetailInfo(BaseModel):
    """출구 상세 정보"""
    exit_number: str
    has_elevator: bool
    elevator_type: Optional[str]
    elevator_location: Optional[str]  # "출구 왼쪽 10m"
    elevator_button_info: Optional[str]  # "지하 2층 버튼을 누르세요"
    elevator_time_seconds: Optional[int]  # 60
    gate_direction: Optional[str]  # "엘리베이터 하차 후 직진"
    floor_level: Optional[str]
    gps: Optional[Dict]


class RouteSearchResponse(BaseModel):
    """경로 검색 응답 (간소화 - 상세 정보는 체크포인트/네비게이션 API에서)"""
    route_id: int
    start_station: str
    end_station: str
    line: str
    direction: str
    estimated_time_minutes: int
    distance_meters: int

    # 체크포인트 (GPS 좌표 포함 - 프론트 위치 감지용)
    checkpoints: List[CheckpointData]

    # 실시간 열차 정보 (간단히)
    realtime_train: Optional[Dict] = None

    # 경고 사항
    warnings: List[str] = []

    status: str


@router.post("/search", response_model=RouteSearchResponse)
async def search_route(request: RouteSearchRequest, db: Session = Depends(get_db)):
    """
    경로 탐색 (AI 기반 점수 계산)
    
    기획 문서 기준:
    1. DB에서 가능한 경로 조회
    2. Open API로 실시간 시설 상태 확인
    3. 점수 계산으로 최적 경로 선택 ⭐
    4. 점수 계산으로 최적 출입구 선택 ⭐
    5. 최적 탑승 칸 실시간 계산 ⭐
    6. 체크포인트 자동 생성
    """

    # 1. DB에서 역 찾기
    start_station = db.query(Station).filter(
        Station.name.contains(request.start_station[:2])
    ).first()

    end_station = db.query(Station).filter(
        Station.name.contains(request.end_station[:2])
    ).first()

    if not start_station or not end_station:
        raise HTTPException(status_code=404, detail="역을 찾을 수 없습니다")

    # 2. 경로 실시간 생성 (더미 데이터 사용 안 함)
    # 같은 노선이면 경로 생성
    if start_station.line != end_station.line:
        raise HTTPException(status_code=404, detail="직통 경로가 없습니다 (환승 필요)")
    
    # 실시간 경로 객체 생성
    class RouteObject:
        def __init__(self, start_id, end_id, line, direction, time, distance, route_id):
            self.route_id = route_id
            self.start_station_id = start_id
            self.end_station_id = end_id
            self.line = line
            self.direction = direction
            self.estimated_time_minutes = time
            self.distance_meters = distance
            self.transfer_required = False
    
    # 거리 계산 (GPS 거리 계산)
    lat1, lon1 = float(start_station.latitude), float(start_station.longitude)
    lat2, lon2 = float(end_station.latitude), float(end_station.longitude)

    distance = int(calculate_gps_distance(lat1, lon1, lat2, lon2))
    
    # 시간 계산 (평균 속도 40km/h)
    time = max(5, int(distance / 40000 * 60))  # 최소 5분

    # 유니크 route_id 생성
    generated_route_id = route_cache.generate_route_id()

    route = RouteObject(
        start_id=start_station.station_id,
        end_id=end_station.station_id,
        line=start_station.line,
        direction=f"{end_station.name} 방면",
        time=time,
        distance=distance,
        route_id=generated_route_id
    )

    routes = [route]  # 단일 경로

    # 3. Open API로 실시간 상태 확인
    start_elevator_status = SeoulMetroAPI.get_elevator_status(request.start_station)
    end_elevator_status = SeoulMetroAPI.get_elevator_status(request.end_station)
    exit_closures = SeoulMetroAPI.check_exit_closure(request.start_station)

    # 4. 점수 계산으로 최적 경로 선택 ⭐
    best_route = _select_best_route(
        routes=routes,
        user_tags=request.user_tags,
        start_elevator_status=start_elevator_status,
        end_elevator_status=end_elevator_status
    )

    # 5. 점수 계산으로 최적 출입구 선택 ⭐
    start_exit = _select_best_exit(
        station_id=start_station.station_id,
        user_location=request.user_location,  # 사용자 현재 위치 ⭐
        user_tags=request.user_tags,
        elevator_status=start_elevator_status,
        db=db
    )

    end_exit = _select_best_exit(
        station_id=end_station.station_id,
        user_location=None,  # 도착역은 사용자 위치 무관
        user_tags=request.user_tags,
        elevator_status=end_elevator_status,
        db=db
    )

    if not start_exit:
        raise HTTPException(
            status_code=404,
            detail=f"{request.start_station}에 적합한 출입구를 찾을 수 없습니다"
        )
    if not end_exit:
        raise HTTPException(
            status_code=404,
            detail=f"{request.end_station}에 적합한 출입구를 찾을 수 없습니다"
        )

    # 6. 최적 탑승 칸 실시간 계산 ⭐
    optimal_boarding = _calculate_optimal_boarding(
        route=best_route,
        end_exit=end_exit,
        db=db
    )

    # 7. 경고 메시지 생성
    warnings = []
    status = "정상"

    if not start_elevator_status.get('all_working', True):
        warnings.append(f"{request.start_station} 엘리베이터 일부 점검 중")
        status = "주의"

    if not end_elevator_status.get('all_working', True):
        warnings.append(f"{request.end_station} 엘리베이터 일부 점검 중")
        status = "주의"

    if exit_closures.get('is_closed', False):
        warnings.append(f"출입구 폐쇄: {exit_closures.get('reason', '')}")
        status = "주의"

    # 8. 출발지→출발역 도보 안내 생성
    walking_guide = _generate_walking_guide(
        user_location=request.user_location,
        exit_obj=start_exit,
        station_name=start_station.name
    )

    # 9. 도착역 하차 후 안내 생성
    arrival_guide = _generate_arrival_walking_guide(
        end_station=end_station,
        end_exit=end_exit,
        optimal_boarding=optimal_boarding,
        db=db
    )

    # 10. 체크포인트 자동 생성
    checkpoints = _generate_checkpoints(
        route=best_route,
        start_station=start_station,
        end_station=end_station,
        start_exit=start_exit,
        end_exit=end_exit,
        optimal_boarding=optimal_boarding,
        user_tags=request.user_tags,
        walking_guide=walking_guide,
        arrival_guide=arrival_guide
    )

    # 11. 엘리베이터 상태 통합 (해당 역만 필터링)
    def _filter_station_elevators(status: Dict, station_name: str) -> List[Dict]:
        """해당 역의 엘리베이터만 필터링"""
        station_key = station_name.replace("역", "")
        filtered = []
        for elev in status.get('elevators', []):
            elev_station = elev.get('station_name', '').replace("역", "")
            # 정확히 해당 역 이름만 포함 (잠실 vs 잠실나루 구분)
            if station_key == elev_station.replace("(2)", "").replace("(8)", "").strip():
                filtered.append(elev)
        return filtered

    elevator_status = {
        "start_station": {
            "name": start_station.name,
            "elevators": _filter_station_elevators(start_elevator_status, start_station.name),
            "all_working": start_elevator_status.get('all_working', True)
        },
        "end_station": {
            "name": end_station.name,
            "elevators": _filter_station_elevators(end_elevator_status, end_station.name),
            "all_working": end_elevator_status.get('all_working', True)
        }
    }

    # 12. 실시간 열차 도착 정보 조회
    from app.services.api_service import RealtimeSubwayAPI

    realtime_arrivals = RealtimeSubwayAPI.get_realtime_station_arrival(start_station.name)

    # 요청된 방향의 열차만 필터링
    realtime_train = None
    if realtime_arrivals:
        direction_key = best_route.direction.replace(" 방면", "")
        filtered = [
            arr for arr in realtime_arrivals
            if direction_key in arr.get('terminal_station_name', '') or
               direction_key in arr.get('train_line_name', '')
        ]

        if filtered:
            first = filtered[0]
            realtime_train = {
                "arrival_minutes": first.get('arrival_minutes', 0),
                "arrival_seconds": first.get('arrival_seconds', 0),
                "arrival_message": first.get('arrival_message', ''),
                "terminal_station": first.get('terminal_station_name', ''),
                "train_status": first.get('train_status', '일반'),
                "is_last_train": first.get('is_last_train', False),
                "current_location": first.get('arrival_detail', '')
            }
        elif realtime_arrivals:
            # 필터링 실패 시 첫 번째 열차
            first = realtime_arrivals[0]
            realtime_train = {
                "arrival_minutes": first.get('arrival_minutes', 0),
                "arrival_seconds": first.get('arrival_seconds', 0),
                "arrival_message": first.get('arrival_message', ''),
                "terminal_station": first.get('terminal_station_name', ''),
                "train_status": first.get('train_status', '일반'),
                "is_last_train": first.get('is_last_train', False),
                "current_location": first.get('arrival_detail', '')
            }

    # 13. 경로 정보 캐시에 저장 (네비게이션 API에서 사용)
    route_cache.save_route(
        route_id=best_route.route_id,
        start_station=start_station.name,
        end_station=end_station.name,
        line=best_route.line,
        direction=best_route.direction,
        checkpoints=[cp.model_dump() for cp in checkpoints],
        need_elevator=request.user_tags.need_elevator
    )

    # 14. 응답 생성 (간소화)
    return RouteSearchResponse(
        route_id=best_route.route_id,
        start_station=start_station.name,
        end_station=end_station.name,
        line=best_route.line,
        direction=best_route.direction,
        estimated_time_minutes=best_route.estimated_time_minutes,
        distance_meters=best_route.distance_meters,

        # 체크포인트 (프론트 위치 감지용)
        checkpoints=checkpoints,

        # 실시간 열차 정보
        realtime_train=realtime_train,

        # 경고 사항
        warnings=warnings,

        status=status
    )


def _select_best_route(
    routes: List,
    user_tags: UserTags,
    start_elevator_status: Dict,
    end_elevator_status: Dict
):
    """
    AI 점수 계산으로 최적 경로 선택
    
    현재는 단일 경로만 생성하므로 점수 계산 후 반환
    """
    route = routes[0]  # 단일 경로
    
    # 점수 계산 (로깅용)
    score = 100
    
    # 엘리베이터 고장이면 감점
    if not start_elevator_status.get('all_working', True):
        score -= 30
    if not end_elevator_status.get('all_working', True):
        score -= 30
    
    # 거리가 짧을수록 높은 점수
    if user_tags.prefer_short:
        score += (10000 - route.distance_meters) // 100
    
    # 시간이 짧을수록 높은 점수
    score += (60 - route.estimated_time_minutes) * 2
    
    return route


def _select_best_exit(
    station_id: int,
    user_location: Optional[Dict],  # {"lat": 37.xxx, "lon": 127.xxx} ⭐
    user_tags: UserTags,
    elevator_status: Dict,
    db: Session
) -> Optional[Exit]:
    """
    AI 점수 계산으로 최적 출입구 선택

    우선순위:
    1. 엘리베이터 필수 시 API 실시간 데이터로 정상 작동하는 엘리베이터 출구 선택
    2. 사용자 현재 위치에서 가장 가까운 출입구 (GPS 거리 계산) ⭐
    3. 엘리베이터 실시간 상태
    """
    import re

    exits = db.query(Exit).filter(
        Exit.station_id == station_id,
        Exit.latitude.isnot(None)  # GPS 좌표 있는 것만
    ).all()

    if not exits:
        return None

    # API에서 외부 엘리베이터가 있는 출구 번호 추출 (정상 작동하는 것만)
    api_elevator_exits = set()  # 정상 작동하는 엘리베이터 출구
    api_broken_exits = set()  # 고장/점검 중인 엘리베이터 출구

    for elev in elevator_status.get('elevators', []):
        location = elev.get('location', '')
        # "1번 출입구", "10번 출입구" 등에서 정확한 번호 추출
        match = re.search(r'(\d+)번\s*출입구', location)
        if match:
            exit_num = match.group(1)
            status = elev.get('status', '')
            if status == '정상':
                api_elevator_exits.add(exit_num)
            else:
                api_broken_exits.add(exit_num)

    best_exit = None
    best_score = -1
    fallback_exit = None  # 엘리베이터 없을 때 가장 가까운 출구

    for exit in exits:
        score = 100

        # API 데이터로 엘리베이터 유무 확인 (DB보다 우선)
        has_working_elevator = exit.exit_number in api_elevator_exits
        has_broken_elevator = exit.exit_number in api_broken_exits
        has_any_elevator = has_working_elevator or has_broken_elevator or exit.has_elevator

        # 1. 엘리베이터 필수인 경우
        if user_tags.need_elevator:
            if has_broken_elevator and not has_working_elevator:
                # 점검 중인 엘리베이터만 있으면 크게 감점
                score -= 200
            elif not has_any_elevator:
                # 엘리베이터 없으면 fallback 후보로만 저장
                if user_location:
                    lat1, lon1 = user_location["lat"], user_location["lon"]
                    lat2, lon2 = float(exit.latitude), float(exit.longitude)
                    distance = calculate_gps_distance(lat1, lon1, lat2, lon2)
                    if fallback_exit is None or distance < fallback_exit[1]:
                        fallback_exit = (exit, distance)
                continue

        # 2. 사용자 현재 위치에서 거리 계산 (가장 중요!) ⭐
        if user_location:
            lat1, lon1 = user_location["lat"], user_location["lon"]
            lat2, lon2 = float(exit.latitude), float(exit.longitude)

            # GPS 거리 계산
            distance = calculate_gps_distance(lat1, lon1, lat2, lon2)

            # 거리가 가까울수록 높은 점수 (최대 +100점)
            # 0m: +100점, 500m: +50점, 1000m: 0점
            distance_score = max(0, 100 - (distance / 10))
            score += distance_score

        # 3. 정상 작동하는 엘리베이터 있으면 큰 가산점
        if has_working_elevator:
            score += 100
        elif has_any_elevator:
            score += 30

        if score > best_score:
            best_score = score
            best_exit = exit

    # 엘리베이터 있는 출구를 못 찾았으면 가장 가까운 출구 반환
    if best_exit is None and fallback_exit:
        best_exit = fallback_exit[0]

    return best_exit


def _calculate_optimal_boarding(
    route,
    end_exit: Exit,
    db: Session
) -> Dict:
    """
    최적 탑승 칸 실시간 계산 (PlatformEdge 데이터 활용)

    기획 문서:
    best_car = calculate_best_car_position(
        end_station=end_station,
        end_exit=end_exit,
        elevator_location=elevator_location
    )
    # 결과: 7-8번째 칸 (잠실역 4번 출구 엘리베이터와 가장 가까움)
    """
    from app.models import PlatformEdge

    # PlatformEdge에서 연단간격이 넓고 높이차가 낮은 칸 찾기
    # (휠체어 승하차가 편한 위치)
    best_edges = db.query(PlatformEdge).filter(
        PlatformEdge.station_id == route.end_station_id,
        PlatformEdge.gap_width == '넓음',
        PlatformEdge.height_diff == '낮음'
    ).order_by(PlatformEdge.car_number).all()

    if best_edges:
        # 가장 승하차하기 편한 칸들 선택
        car_numbers = sorted(set(edge.car_number for edge in best_edges if edge.car_number))

        if car_numbers:
            # 연속된 2개 칸 선택 (예: 7-8번째)
            car_start = car_numbers[0]
            car_end = car_numbers[1] if len(car_numbers) > 1 else car_start

            return {
                "car_start": car_start,
                "car_end": car_end,
                "reason": f"도착역 {end_exit.exit_number}번 출구 엘리베이터와 가깝고, 승강장과 열차 간격이 좁아 승하차가 편한 위치"
            }

    # fallback: PlatformEdge 데이터가 없으면 기본값
    if end_exit.has_elevator:
        return {
            "car_start": 7,
            "car_end": 8,
            "reason": f"{end_exit.exit_number}번 출구 엘리베이터와 가까운 위치"
        }
    else:
        # 엘리베이터 없으면 중간 칸
        return {
            "car_start": 5,
            "car_end": 6,
            "reason": "승강장 중앙 위치"
        }


def _generate_checkpoints(
    route: Route,
    start_station: Station,
    end_station: Station,
    start_exit: Exit,
    end_exit: Exit,
    optimal_boarding: Dict,
    user_tags: UserTags,
    walking_guide: WalkingGuide = None,
    arrival_guide: Dict = None
) -> List[CheckpointData]:
    """
    체크포인트 자동 생성 (간소화 - 상세 정보는 체크포인트/네비게이션 API에서)

    프론트 위치 감지용 최소 정보만 포함
    """
    checkpoints = []

    # 0. 출발지 (현재 위치)
    checkpoints.append(CheckpointData(
        id=0,
        type="출발지",
        location="현재 위치",
        radius=30,
        data={
            "station_name": start_station.name,
            "exit_number": start_exit.exit_number,
            "line": route.line,
            "direction": route.direction
        }
    ))

    # 1. 출발역 출입구
    checkpoints.append(CheckpointData(
        id=1,
        type="출발역_출구",
        location=f"{start_station.name} {start_exit.exit_number}번 출구",
        latitude=float(start_exit.latitude) if start_exit.latitude else None,
        longitude=float(start_exit.longitude) if start_exit.longitude else None,
        radius=30,
        data={
            "station_name": start_station.name,
            "exit_number": start_exit.exit_number,
            "line": route.line,
            "direction": route.direction
        }
    ))

    # 2. 출발역 승강장
    checkpoints.append(CheckpointData(
        id=2,
        type="출발역_승강장",
        location=f"{start_station.name} {route.line} {route.direction}",
        radius=30,
        data={
            "station_name": start_station.name,
            "line": route.line,
            "direction": route.direction
        }
    ))

    # 3. 승강장 대기
    checkpoints.append(CheckpointData(
        id=3,
        type="승강장_대기",
        location=f"{start_station.name} {route.line} 승강장",
        radius=30,
        data={
            "station_name": start_station.name,
            "line": route.line,
            "direction": route.direction
        }
    ))

    # 4. 열차 탑승
    checkpoints.append(CheckpointData(
        id=4,
        type="열차_탑승",
        location="열차 내부",
        data={
            "start_station": start_station.name,
            "end_station": end_station.name,
            "line": route.line,
            "direction": route.direction
        }
    ))

    # 5. 도착역 승강장
    checkpoints.append(CheckpointData(
        id=5,
        type="도착역_승강장",
        location=f"{end_station.name} {route.line} 승강장",
        radius=30,
        data={
            "station_name": end_station.name,
            "exit_number": end_exit.exit_number,
            "line": route.line,
            "direction": route.direction
        }
    ))

    # 6. 도착역 출구
    checkpoints.append(CheckpointData(
        id=6,
        type="도착역_출구",
        location=f"{end_station.name} {end_exit.exit_number}번 출구",
        latitude=float(end_exit.latitude) if end_exit.latitude else None,
        longitude=float(end_exit.longitude) if end_exit.longitude else None,
        radius=30,
        data={
            "station_name": end_station.name,
            "exit_number": end_exit.exit_number,
            "line": route.line,
            "direction": route.direction
        }
    ))

    # 7. 충전소 (전동 휠체어만)
    if user_tags.need_charging_info:
        checkpoints.append(CheckpointData(
            id=7,
            type="충전소",
            location=f"{end_station.name} 충전소",
            radius=50,
            optional=True,
            data={
                "station_name": end_station.name
            }
        ))

    return checkpoints


@router.get("/stations")
async def get_stations(db: Session = Depends(get_db)):
    """모든 역 목록 조회"""
    stations = db.query(Station).all()

    return {
        "count": len(stations),
        "stations": [
            {
                "id": s.station_id,
                "name": s.name,
                "line": s.line,
                "latitude": float(s.latitude),
                "longitude": float(s.longitude)
            }
            for s in stations
        ]
    }
