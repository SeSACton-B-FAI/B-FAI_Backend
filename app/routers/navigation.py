"""
실시간 네비게이션 API

프론트에서 주기적으로 (5-10초) 현재 좌표를 전송하면
DB, Open API, RAG를 활용해 상세한 안내문 제공
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Dict, List
import math

from app.database import get_db
from app.models import Station, Exit, Route
from app.services.api_service import SeoulMetroAPI, RealtimeSubwayAPI
from app.services.rag_service import RAGService
from app.services.route_cache import route_cache

router = APIRouter(prefix="/api/navigation", tags=["navigation"])

# 서비스 인스턴스
api_service = SeoulMetroAPI()
rag_service = RAGService()


class NavigationRequest(BaseModel):
    """실시간 위치 안내 요청 (간소화)"""
    route_id: int
    current_location: Dict[str, float]  # {"lat": 37.xxx, "lon": 127.xxx}
    current_checkpoint_id: int


class NavigationResponse(BaseModel):
    """실시간 위치 안내 응답"""
    guide_text: str  # 상세 안내문 (TTS용)

    # 현재 상태
    current_checkpoint_id: int
    current_checkpoint_type: str

    # 다음 목표
    next_checkpoint: Optional[Dict] = None
    distance_to_next: Optional[int] = None  # 미터
    direction: Optional[str] = None  # "직진", "좌회전", "우회전"

    # 체크포인트 도달 여부
    is_checkpoint_reached: bool = False
    reached_checkpoint_id: Optional[int] = None

    # 실시간 정보
    realtime_info: Optional[Dict] = None

    status: str = "정상"


def calculate_gps_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 GPS 좌표 간 거리 계산 (미터)"""
    R = 6371000  # 지구 반지름 (미터)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c


def calculate_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """두 좌표 간 방향 계산"""
    delta_lon = lon2 - lon1
    delta_lat = lat2 - lat1

    angle = math.degrees(math.atan2(delta_lon, delta_lat))

    if -22.5 <= angle < 22.5:
        return "북쪽"
    elif 22.5 <= angle < 67.5:
        return "북동쪽"
    elif 67.5 <= angle < 112.5:
        return "동쪽"
    elif 112.5 <= angle < 157.5:
        return "남동쪽"
    elif angle >= 157.5 or angle < -157.5:
        return "남쪽"
    elif -157.5 <= angle < -112.5:
        return "남서쪽"
    elif -112.5 <= angle < -67.5:
        return "서쪽"
    else:
        return "북서쪽"


@router.post("/guide", response_model=NavigationResponse)
async def get_navigation_guide(
    request: NavigationRequest,
    db: Session = Depends(get_db)
):
    """
    실시간 위치 기반 안내

    프론트에서 5-10초마다 호출하여 현재 위치에 맞는 안내 제공
    DB, Open API, RAG를 모두 활용하여 상세한 안내문 생성

    간소화된 요청: route_id, current_location, current_checkpoint_id만 필요
    나머지 정보는 route_id로 캐시에서 조회
    """

    # 1. 캐시에서 경로 정보 조회
    route_info = route_cache.get_route(request.route_id)

    if not route_info:
        raise HTTPException(
            status_code=404,
            detail="경로 정보를 찾을 수 없습니다. 경로 검색을 다시 해주세요."
        )

    # 캐시에서 필요한 정보 추출
    start_station_name = route_info["start_station"]
    end_station_name = route_info["end_station"]
    line = route_info["line"]
    direction = route_info["direction"]
    need_elevator = route_info.get("need_elevator", False)

    # 현재 체크포인트 데이터에서 출구 번호 추출
    checkpoint_data = route_cache.get_checkpoint_data(request.route_id, request.current_checkpoint_id)
    exit_number = checkpoint_data.get("exit_number", "1") if checkpoint_data else "1"

    # 2. 역 정보 조회
    station = db.query(Station).filter(
        Station.name.contains(start_station_name[:2])
    ).first()

    end_station = db.query(Station).filter(
        Station.name.contains(end_station_name[:2])
    ).first()

    if not station:
        raise HTTPException(status_code=404, detail="역을 찾을 수 없습니다")

    # 3. 현재 체크포인트 타입별 처리
    checkpoint_id = request.current_checkpoint_id
    user_lat = request.current_location["lat"]
    user_lon = request.current_location["lon"]

    guide_text = ""
    next_checkpoint = None
    distance_to_next = None
    nav_direction = None
    is_reached = False
    reached_id = None
    realtime_info = {}

    # 체크포인트별 안내 로직
    if checkpoint_id == 0:
        # 출발지 → 출발역 출구
        guide_text, distance_to_next, nav_direction, is_reached, realtime_info = await _guide_to_exit(
            db=db,
            station=station,
            exit_number=exit_number,
            user_lat=user_lat,
            user_lon=user_lon,
            need_elevator=need_elevator
        )

        if is_reached:
            reached_id = 1
            next_checkpoint = {"id": 1, "type": "출발역_출구"}
        else:
            next_checkpoint = {"id": 1, "type": "출발역_출구", "location": f"{station.name} {exit_number}번 출구"}

    elif checkpoint_id == 1:
        # 출발역 출구 → 승강장
        guide_text, realtime_info = await _guide_exit_to_platform(
            db=db,
            station=station,
            exit_number=exit_number,
            line=line,
            direction=direction,
            need_elevator=need_elevator
        )
        next_checkpoint = {"id": 2, "type": "출발역_승강장"}

    elif checkpoint_id == 2:
        # 승강장 도착 → 대기 위치 안내
        guide_text, realtime_info = await _guide_platform_waiting(
            db=db,
            station=station,
            line=line,
            direction=direction,
            end_station=end_station
        )
        next_checkpoint = {"id": 3, "type": "승강장_대기"}

    elif checkpoint_id == 3:
        # 승강장 대기 → 실시간 열차 정보
        guide_text, realtime_info = await _guide_train_arrival(
            station=station,
            line=line,
            direction=direction
        )
        next_checkpoint = {"id": 4, "type": "열차_탑승"}

    elif checkpoint_id == 4:
        # 열차 탑승 중 → 하차 안내
        guide_text, realtime_info = await _guide_on_train(
            start_station=station,
            end_station=end_station,
            line=line
        )
        next_checkpoint = {"id": 5, "type": "도착역_승강장"}

    elif checkpoint_id == 5:
        # 도착역 승강장 → 출구 안내
        # 도착역 출구 번호 가져오기
        end_checkpoint_data = route_cache.get_checkpoint_data(request.route_id, 6)
        end_exit_number = end_checkpoint_data.get("exit_number", "1") if end_checkpoint_data else "1"

        guide_text, realtime_info = await _guide_arrival_platform(
            db=db,
            station=end_station,
            exit_number=end_exit_number,
            need_elevator=need_elevator
        )
        next_checkpoint = {"id": 6, "type": "도착역_출구"}

    elif checkpoint_id == 6:
        # 도착역 출구
        # 도착역 출구 번호 가져오기
        end_checkpoint_data = route_cache.get_checkpoint_data(request.route_id, 6)
        end_exit_number = end_checkpoint_data.get("exit_number", "1") if end_checkpoint_data else "1"

        guide_text, realtime_info = await _guide_final_exit(
            db=db,
            station=end_station,
            exit_number=end_exit_number,
            need_elevator=need_elevator
        )
        next_checkpoint = {"id": 7, "type": "충전소"} if need_elevator else None

    elif checkpoint_id == 7:
        # 충전소 안내
        guide_text = f"{end_station.name} 주변 휠체어 충전소를 안내해드립니다."
        realtime_info = {}

    # RAG로 추가 정보 보강
    rag_context = {
        "station_name": station.name if checkpoint_id <= 4 else end_station.name,
        "checkpoint_type": _get_checkpoint_type_name(checkpoint_id),
        "need_elevator": need_elevator
    }

    rag_tip = rag_service.generate_guide(
        question=f"{rag_context['station_name']} {rag_context['checkpoint_type']} 이용 팁",
        db_data=rag_context,
        api_data=realtime_info
    )

    if rag_tip and len(rag_tip) > 20 and "팁" not in guide_text:
        guide_text += f"\n\n{rag_tip}"

    return NavigationResponse(
        guide_text=guide_text,
        current_checkpoint_id=checkpoint_id,
        current_checkpoint_type=_get_checkpoint_type_name(checkpoint_id),
        next_checkpoint=next_checkpoint,
        distance_to_next=distance_to_next,
        direction=nav_direction,
        is_checkpoint_reached=is_reached,
        reached_checkpoint_id=reached_id,
        realtime_info=realtime_info,
        status="정상"
    )


async def _guide_to_exit(
    db: Session,
    station: Station,
    exit_number: str,
    user_lat: float,
    user_lon: float,
    need_elevator: bool
) -> tuple:
    """출발지 → 출발역 출구 안내"""

    # 출구 좌표 조회
    exit_obj = db.query(Exit).filter(
        Exit.station_id == station.station_id,
        Exit.exit_number == exit_number
    ).first()

    if not exit_obj or not exit_obj.latitude:
        return "출구 정보를 찾을 수 없습니다.", None, None, False, {}

    exit_lat = float(exit_obj.latitude)
    exit_lon = float(exit_obj.longitude)

    # 거리 및 방향 계산
    distance = calculate_gps_distance(user_lat, user_lon, exit_lat, exit_lon)
    direction = calculate_direction(user_lat, user_lon, exit_lat, exit_lon)

    # 체크포인트 도달 여부 (30m 이내)
    is_reached = distance <= 30

    # 엘리베이터 실시간 상태
    elevator_status = api_service.get_elevator_status(station.name)

    # 안내문 생성
    guide_parts = []

    if is_reached:
        guide_parts.append(f"{station.name} {exit_number}번 출구에 도착하셨습니다.")
        if need_elevator and exit_obj.has_elevator:
            elev_location = getattr(exit_obj, 'elevator_location', None) or f"{exit_number}번 출입구"
            guide_parts.append(f"엘리베이터는 {elev_location}에 있습니다.")
    else:
        # 거리별 안내
        if distance > 100:
            guide_parts.append(f"{direction}으로 약 {int(distance)}m 이동하세요.")
            guide_parts.append(f"{station.name} {exit_number}번 출구로 향합니다.")
        elif distance > 50:
            guide_parts.append(f"{direction}으로 약 {int(distance)}m 남았습니다.")
            guide_parts.append(f"곧 {station.name} {exit_number}번 출구가 보입니다.")
        else:
            guide_parts.append(f"거의 다 왔습니다! {int(distance)}m 앞에 {exit_number}번 출구가 있습니다.")

        # 엘리베이터 정보
        if need_elevator:
            working_elevators = [e for e in elevator_status.get('elevators', [])
                               if exit_number in e.get('location', '') and e.get('status') == '정상']
            if working_elevators:
                guide_parts.append(f"엘리베이터가 정상 운행 중입니다.")
            elif elevator_status.get('elevators'):
                guide_parts.append(f"엘리베이터 상태를 확인해주세요.")

    guide_text = " ".join(guide_parts)

    return guide_text, int(distance), direction, is_reached, {"elevator_status": elevator_status}


async def _guide_exit_to_platform(
    db: Session,
    station: Station,
    exit_number: str,
    line: str,
    direction: str,
    need_elevator: bool
) -> tuple:
    """출구 → 승강장 안내"""

    exit_obj = db.query(Exit).filter(
        Exit.station_id == station.station_id,
        Exit.exit_number == exit_number
    ).first()

    guide_parts = []
    guide_parts.append(f"{station.name} {exit_number}번 출구에서 {line} {direction} 승강장으로 이동합니다.")

    if need_elevator and exit_obj and exit_obj.has_elevator:
        button_info = getattr(exit_obj, 'elevator_button_info', None) or "지하층 버튼을 누르세요"
        time_seconds = getattr(exit_obj, 'elevator_time_seconds', None) or 60

        guide_parts.append(f"\n\n엘리베이터를 이용하세요.")
        guide_parts.append(f"{button_info}")
        guide_parts.append(f"약 {time_seconds}초 소요됩니다.")
        guide_parts.append(f"\n엘리베이터 하차 후 {direction} 안내 표지판을 따라가세요.")
    else:
        guide_parts.append(f"\n{direction} 안내 표지판을 따라 승강장으로 이동하세요.")

    # 엘리베이터 상태
    elevator_status = api_service.get_elevator_status(station.name)

    return " ".join(guide_parts), {"elevator_status": elevator_status}


async def _guide_platform_waiting(
    db: Session,
    station: Station,
    line: str,
    direction: str,
    end_station: Station
) -> tuple:
    """승강장 대기 위치 안내"""

    # 최적 탑승 칸 계산 (간단히 7-8번째 칸)
    car_start, car_end = 7, 8

    guide_parts = []
    guide_parts.append(f"{station.name} {line} {direction} 승강장입니다.")
    guide_parts.append(f"\n\n{car_start}-{car_end}번째 칸 앞에서 대기해주세요.")
    guide_parts.append(f"도착역 {end_station.name}에서 엘리베이터와 가장 가까운 위치입니다.")

    # 실시간 열차 정보
    train_arrival = RealtimeSubwayAPI.get_realtime_station_arrival(station.name)

    if train_arrival:
        first = train_arrival[0] if train_arrival else {}
        minutes = first.get('arrival_minutes', 0)
        if minutes:
            guide_parts.append(f"\n\n다음 열차가 약 {minutes}분 후 도착합니다.")

    return " ".join(guide_parts), {"train_arrival": train_arrival}


async def _guide_train_arrival(
    station: Station,
    line: str,
    direction: str
) -> tuple:
    """실시간 열차 도착 안내"""

    train_arrival = RealtimeSubwayAPI.get_realtime_station_arrival(station.name)

    guide_parts = []

    if train_arrival:
        first = train_arrival[0]
        minutes = first.get('arrival_minutes', 0)
        message = first.get('arrival_message', '')
        terminal = first.get('terminal_station_name', '')
        is_last = first.get('is_last_train', False)

        if minutes <= 1:
            guide_parts.append(f"열차가 곧 도착합니다! 승차 준비를 해주세요.")
        else:
            guide_parts.append(f"다음 열차가 약 {minutes}분 후 도착합니다.")

        if terminal:
            guide_parts.append(f"행선지: {terminal}")

        if is_last:
            guide_parts.append(f"이 열차가 막차입니다!")

        if message:
            guide_parts.append(f"\n현재 위치: {message}")
    else:
        guide_parts.append(f"열차 도착 정보를 확인 중입니다. 잠시만 기다려주세요.")

    return " ".join(guide_parts), {"train_arrival": train_arrival}


async def _guide_on_train(
    start_station: Station,
    end_station: Station,
    line: str
) -> tuple:
    """열차 탑승 중 안내"""

    guide_parts = []
    guide_parts.append(f"열차에 탑승하셨습니다.")
    guide_parts.append(f"\n\n{end_station.name}에서 하차하세요.")
    guide_parts.append(f"하차 후 출구 방향 안내를 따라가세요.")

    # 도착역 실시간 정보 (미리 확인)
    elevator_status = api_service.get_elevator_status(end_station.name)

    if not elevator_status.get('all_working', True):
        guide_parts.append(f"\n\n주의: {end_station.name} 엘리베이터 일부가 점검 중입니다.")

    return " ".join(guide_parts), {"end_station_elevator": elevator_status}


async def _guide_arrival_platform(
    db: Session,
    station: Station,
    exit_number: str,
    need_elevator: bool
) -> tuple:
    """도착역 승강장 → 출구 안내"""

    exit_obj = db.query(Exit).filter(
        Exit.station_id == station.station_id,
        Exit.exit_number == exit_number
    ).first()

    guide_parts = []
    guide_parts.append(f"{station.name}에 도착하셨습니다!")
    guide_parts.append(f"\n\n{exit_number}번 출구 방향으로 이동하세요.")

    if need_elevator and exit_obj:
        elev_location = getattr(exit_obj, 'elevator_location', None)
        if elev_location:
            guide_parts.append(f"엘리베이터는 {elev_location}에 있습니다.")

        button_info = getattr(exit_obj, 'elevator_button_info', None)
        if button_info:
            guide_parts.append(f"{button_info}")

    elevator_status = api_service.get_elevator_status(station.name)

    return " ".join(guide_parts), {"elevator_status": elevator_status}


async def _guide_final_exit(
    db: Session,
    station: Station,
    exit_number: str,
    need_elevator: bool
) -> tuple:
    """도착역 출구 최종 안내"""

    exit_obj = db.query(Exit).filter(
        Exit.station_id == station.station_id,
        Exit.exit_number == exit_number
    ).first()

    guide_parts = []
    guide_parts.append(f"{station.name} {exit_number}번 출구입니다.")

    if need_elevator and exit_obj and exit_obj.has_elevator:
        button_info = getattr(exit_obj, 'elevator_button_info', None) or "지상층 버튼을 누르세요"
        time_seconds = getattr(exit_obj, 'elevator_time_seconds', None) or 60

        guide_parts.append(f"\n\n엘리베이터를 이용하세요.")
        guide_parts.append(f"{button_info}")
        guide_parts.append(f"약 {time_seconds}초 후 지상에 도착합니다.")

    guide_parts.append(f"\n\n목적지에 도착하셨습니다! 안전한 이동이 되셨길 바랍니다.")

    return " ".join(guide_parts), {}


def _get_checkpoint_type_name(checkpoint_id: int) -> str:
    """체크포인트 ID → 타입명"""
    types = {
        0: "출발지",
        1: "출발역_출구",
        2: "출발역_승강장",
        3: "승강장_대기",
        4: "열차_탑승",
        5: "도착역_승강장",
        6: "도착역_출구",
        7: "충전소"
    }
    return types.get(checkpoint_id, "unknown")
