"""
Checkpoint guide router - 체크포인트별 안내 API
기획 문서: [최종] 비파이 실시간 길안내 서비스.md

데이터 흐름 (5단계):
1. DB → 기본 정보 (출입구, 엘리베이터 위치 등)
2. Open API → 실시간 상태 (고장, 폐쇄 등)
3. RAG → 추가 정보 (이용 방법, 팁 등)
4. LLM → 통합 안내문 생성
5. TTS → 음성 출력 (프론트엔드)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, List

from app.database import get_db
from app.models import Station, Exit, PlatformInfo, PlatformEdge
from app.services.api_service import GeneralSeoulAPI as SeoulMetroAPI, RealtimeSubwayAPI
from app.services import rag_service

router = APIRouter(prefix="/checkpoint", tags=["checkpoint"])


# Request/Response 모델
class CheckpointGuideRequest(BaseModel):
    """체크포인트 안내 요청"""
    checkpoint_id: int
    station_name: str
    exit_number: Optional[str] = None
    line: Optional[str] = None
    direction: Optional[str] = None  # "잠실역 방면"
    platform_direction: Optional[str] = None  # 하위 호환용
    need_elevator: bool = False

    def get_direction(self) -> str:
        """direction 또는 platform_direction 반환"""
        return self.direction or self.platform_direction or ""


class CheckpointGuideResponse(BaseModel):
    """체크포인트 안내 응답"""
    checkpoint_id: int
    checkpoint_type: str
    guide_text: str
    status: str  # "정상", "주의", "경고"

    db_data: Optional[Dict] = {}
    api_data: Optional[Dict] = {}
    alternative_route: Optional[Dict] = None


@router.post("/guide", response_model=CheckpointGuideResponse)
async def get_checkpoint_guide(
    request: CheckpointGuideRequest,
    db: Session = Depends(get_db)
):
    """
    체크포인트 도착 시 안내문 생성 (5단계 처리)
    
    기획 문서:
    def trigger_checkpoint_guide(checkpoint_id, user_tags):
        # 1단계: DB 쿼리
        db_data = db.query(...)
        
        # 2단계: Open API 호출
        elevator_status = api.call("getWksnElvtr", ...)
        
        # 3단계: RAG 검색
        rag_data = rag.search("강남역 3번 출구 엘리베이터 위치")
        
        # 4단계: LLM 통합 생성
        guide_text = llm.generate(prompt)
        
        # 5단계: TTS 음성 출력
        audio = tts.synthesize(guide_text)
    """

    # 역 찾기
    station = db.query(Station).filter(
        Station.name.contains(request.station_name[:2])
    ).first()

    if not station:
        raise HTTPException(status_code=404, detail="역을 찾을 수 없습니다")

    # 체크포인트 타입별 처리
    if request.checkpoint_id == 0:
        # 출발지 - 출발역까지 도보 안내
        return await _handle_departure_checkpoint(request, station, db)

    elif request.checkpoint_id == 1:
        # 출발역 출구
        return await _handle_exit_checkpoint(request, station, db)

    elif request.checkpoint_id == 2:
        # 출발역 승강장
        return await _handle_platform_checkpoint(request, station, db)

    elif request.checkpoint_id == 3:
        # 승강장 대기
        return await _handle_waiting_checkpoint(request, station, db)

    elif request.checkpoint_id == 4:
        # 열차 탑승
        return await _handle_riding_checkpoint(request, station, db)

    elif request.checkpoint_id == 5:
        # 도착역 승강장
        return await _handle_arrival_platform_checkpoint(request, station, db)

    elif request.checkpoint_id == 6:
        # 도착역 출구
        return await _handle_exit_checkpoint(request, station, db)

    elif request.checkpoint_id == 7:
        # 충전소
        return await _handle_charging_checkpoint(request, station, db)

    else:
        # 기타 체크포인트
        return CheckpointGuideResponse(
            checkpoint_id=request.checkpoint_id,
            checkpoint_type="기타",
            guide_text="경로를 따라 이동하세요.",
            status="정상"
        )


async def _handle_departure_checkpoint(
    request: CheckpointGuideRequest,
    station: Station,
    db: Session
) -> CheckpointGuideResponse:
    """출발지 체크포인트 처리 - 출발역까지 도보 안내"""

    # 체크포인트 데이터에서 도보 안내 정보 추출 (route.py에서 전달)
    guide_parts = []

    guide_parts.append(f"🚶 {station.name}으로 이동합니다.")

    # exit_number가 있으면 해당 출구 정보 조회
    if request.exit_number:
        exit_obj = db.query(Exit).filter(
            Exit.station_id == station.station_id,
            Exit.exit_number == request.exit_number
        ).first()

        if exit_obj:
            guide_parts.append(f"\n📍 {request.exit_number}번 출구로 가세요.")

            if exit_obj.has_elevator:
                if hasattr(exit_obj, 'elevator_location') and exit_obj.elevator_location:
                    guide_parts.append(f"엘리베이터는 {exit_obj.elevator_location}에 있습니다.")
                else:
                    guide_parts.append("이 출구에 엘리베이터가 있습니다.")

            if hasattr(exit_obj, 'landmark') and exit_obj.landmark:
                guide_parts.append(f"({exit_obj.landmark} 근처)")

            if hasattr(exit_obj, 'has_slope') and exit_obj.has_slope:
                slope_warning = getattr(exit_obj, 'slope_info', '경사로 주의')
                guide_parts.append(f"\n⚠️ {slope_warning}")

    guide_text = " ".join(guide_parts)

    return CheckpointGuideResponse(
        checkpoint_id=request.checkpoint_id,
        checkpoint_type="출발지",
        guide_text=guide_text,
        status="정상",
        db_data={"station_name": station.name, "exit_number": request.exit_number}
    )


async def _handle_waiting_checkpoint(
    request: CheckpointGuideRequest,
    station: Station,
    db: Session
) -> CheckpointGuideResponse:
    """승강장 대기 체크포인트 - 실시간 열차 도착 정보 (강화)"""

    # 실시간 열차 도착 정보 조회
    realtime_arrivals = RealtimeSubwayAPI.get_realtime_station_arrival(station.name)

    guide_parts = []
    guide_parts.append(f"⏱️ {station.name} 승강장에서 대기 중입니다.")

    # 방향 필터링 (request에 direction이 있으면)
    direction = getattr(request, 'direction', None)
    filtered_arrivals = realtime_arrivals

    if direction and realtime_arrivals:
        # 요청된 방향의 열차만 필터링
        filtered_arrivals = [
            arr for arr in realtime_arrivals
            if direction in arr.get('train_line_name', '') or direction in arr.get('terminal_station_name', '')
        ]
        if not filtered_arrivals:
            filtered_arrivals = realtime_arrivals

    if filtered_arrivals:
        first_train = filtered_arrivals[0]
        arrival_seconds = first_train.get('arrival_seconds', 180)
        arrival_minutes = first_train.get('arrival_minutes', 3)
        arrival_message = first_train.get('arrival_message', '')
        arrival_detail = first_train.get('arrival_detail', '')
        terminal = first_train.get('terminal_station_name', '')

        # 도착 상태별 안내
        if arrival_message in ['도착', '진입']:
            guide_parts.append(f"\n\n🚇 열차가 {arrival_message}합니다!")
            guide_parts.append("탑승 준비를 해주세요.")
        elif arrival_seconds <= 60:
            guide_parts.append(f"\n\n🚇 곧 열차가 도착합니다! (약 {arrival_seconds}초)")
        else:
            guide_parts.append(f"\n\n🚇 약 {arrival_minutes}분 후 열차가 도착합니다.")

        # 행선지 안내
        if terminal:
            guide_parts.append(f"\n행선지: {terminal}행")

        # 상세 위치 정보
        if arrival_detail and arrival_message not in ['도착', '진입']:
            guide_parts.append(f"\n현재 위치: {arrival_detail}")

        # 급행/막차 안내
        train_status = first_train.get('train_status', '일반')
        if train_status in ['급행', '특급']:
            guide_parts.append(f"\n⚡ {train_status} 열차입니다.")

        if first_train.get('is_last_train'):
            guide_parts.append("\n⚠️ 막차입니다!")

        # 다음 열차 정보
        if len(filtered_arrivals) > 1:
            second_train = filtered_arrivals[1]
            second_minutes = second_train.get('arrival_minutes', 0)
            if second_minutes > 0:
                guide_parts.append(f"\n\n다음 열차: 약 {second_minutes}분 후")

    else:
        guide_parts.append("\n\n🚇 곧 열차가 도착합니다.")

    guide_parts.append("\n\n⚠️ 안전선 안쪽에서 기다려주세요.")

    guide_text = " ".join(guide_parts)

    return CheckpointGuideResponse(
        checkpoint_id=request.checkpoint_id,
        checkpoint_type="승강장_대기",
        guide_text=guide_text,
        status="정상",
        api_data={
            "arrivals": filtered_arrivals[:3] if filtered_arrivals else [],
            "total_arrivals": len(realtime_arrivals)
        }
    )


async def _handle_riding_checkpoint(
    request: CheckpointGuideRequest,
    station: Station,
    db: Session
) -> CheckpointGuideResponse:
    """열차 탑승 체크포인트 - 이동 중 안내 (실시간 정보 강화)"""
    from app.models import Route

    guide_parts = []
    guide_parts.append(f"🚇 열차에 탑승하셨습니다.")

    # 목적지 정보
    guide_parts.append(f"\n\n📍 목적지: {station.name}")

    # 노선 정보에서 소요 시간과 역 개수 조회
    line = getattr(request, 'line', None)
    start_station = getattr(request, 'start_station_name', None)

    if line and start_station:
        # DB에서 경로 정보 조회
        route = db.query(Route).filter(
            Route.start_station_name.like(f"%{start_station}%"),
            Route.end_station_name.like(f"%{station.name}%"),
            Route.line == line
        ).first()

        if route:
            guide_parts.append(f"\n예상 소요 시간: 약 {route.estimated_time_minutes}분")

    # 실시간 열차 위치로 도착역 접근 확인
    realtime_arrivals = RealtimeSubwayAPI.get_realtime_station_arrival(station.name)

    approaching_train = None
    if realtime_arrivals:
        # 도착역에 접근 중인 열차 찾기
        for arr in realtime_arrivals:
            arrival_seconds = arr.get('arrival_seconds', 999)
            if arrival_seconds <= 180:  # 3분 이내
                approaching_train = arr
                break

    if approaching_train:
        arrival_minutes = approaching_train.get('arrival_minutes', 0)
        arrival_message = approaching_train.get('arrival_message', '')

        if arrival_message in ['도착', '진입']:
            guide_parts.append(f"\n\n🔔 곧 {station.name}에 도착합니다!")
            guide_parts.append("하차 준비를 해주세요.")
        elif arrival_minutes <= 2:
            guide_parts.append(f"\n\n🔔 약 {arrival_minutes}분 후 {station.name}에 도착합니다.")
            guide_parts.append("하차 준비를 해주세요.")
        else:
            guide_parts.append(f"\n\n약 {arrival_minutes}분 후 도착 예정입니다.")
            guide_parts.append("편안히 이동하세요.")
    else:
        guide_parts.append("\n\n편안히 이동하세요.")
        guide_parts.append("도착역이 가까워지면 알려드리겠습니다.")

    # 하차 위치 안내
    car_position = getattr(request, 'car_position', None)
    if car_position:
        guide_parts.append(f"\n\n💡 하차 시 {car_position}에서 내리세요.")

    guide_text = " ".join(guide_parts)

    return CheckpointGuideResponse(
        checkpoint_id=request.checkpoint_id,
        checkpoint_type="열차_탑승",
        guide_text=guide_text,
        status="정상",
        api_data={
            "approaching": approaching_train is not None,
            "arrival_info": approaching_train
        }
    )


async def _handle_charging_checkpoint(
    request: CheckpointGuideRequest,
    station: Station,
    db: Session
) -> CheckpointGuideResponse:
    """충전소 체크포인트 - 휠체어 충전소 안내"""
    from app.models import ChargingStation

    # 충전소 정보 조회
    charger = db.query(ChargingStation).filter(
        ChargingStation.station_id == station.station_id
    ).first()

    # Open API에서 충전소 정보 조회
    api_chargers = SeoulMetroAPI.get_wheelchair_chargers(station.name)

    guide_parts = []

    if charger or api_chargers:
        guide_parts.append(f"🔋 {station.name}에 휠체어 충전소가 있습니다.")

        if charger:
            guide_parts.append(f"\n📍 위치: {charger.location}")
            if charger.floor_level:
                guide_parts.append(f"({charger.floor_level})")

        if api_chargers:
            for c in api_chargers[:2]:
                guide_parts.append(f"\n• {c.get('location', '')} ({c.get('floor', '')})")
                guide_parts.append(f"  이용료: {c.get('usage_fee', '무료')}")
    else:
        guide_parts.append(f"ℹ️ {station.name} 근처 충전소 정보를 확인 중입니다.")

    guide_text = " ".join(guide_parts)

    return CheckpointGuideResponse(
        checkpoint_id=request.checkpoint_id,
        checkpoint_type="충전소",
        guide_text=guide_text,
        status="정상",
        db_data={"charger": charger is not None},
        api_data={"chargers": api_chargers}
    )


async def _handle_exit_checkpoint(
    request: CheckpointGuideRequest,
    station: Station,
    db: Session
) -> CheckpointGuideResponse:
    """
    출입구 체크포인트 처리 (5단계)
    
    기획 문서:
    [백엔드 처리 5단계]
    1. DB: 엘리베이터 위치 = "출구 왼쪽 10m"
    2. API: 엘리베이터 상태 = "정상"
    3. RAG: "점자 안내판 있음"
    4. LLM: 3개 데이터 통합 → 안내문 생성
    5. TTS: 음성 출력
    """

    # 1단계: DB 조회 (출입구 + 편의시설)
    db_data = {}
    exit_obj = None

    if request.exit_number:
        exit_obj = db.query(Exit).filter(
            Exit.station_id == station.station_id,
            Exit.exit_number == request.exit_number
        ).first()

        if exit_obj:
            db_data = {
                "exit_number": exit_obj.exit_number,
                "has_elevator": exit_obj.has_elevator,
                "elevator_type": exit_obj.elevator_type,
                "description": exit_obj.description,
                "floor_level": exit_obj.floor_level,
                "gps": {
                    "lat": float(exit_obj.latitude),
                    "lon": float(exit_obj.longitude)
                } if exit_obj.latitude else None,
                # 새로운 배리어프리 필드들
                "elevator_location": getattr(exit_obj, 'elevator_location', None),
                "elevator_button_info": getattr(exit_obj, 'elevator_button_info', None),
                "elevator_time_seconds": getattr(exit_obj, 'elevator_time_seconds', None),
                "gate_direction": getattr(exit_obj, 'gate_direction', None),
                "landmark": getattr(exit_obj, 'landmark', None)
            }

    # 역 편의시설 정보 추가
    from app.models import StationFacility
    facility = db.query(StationFacility).filter(
        StationFacility.station_id == station.station_id
    ).first()

    if facility:
        db_data["facilities"] = {
            "has_nursing_room": facility.has_nursing_room,
            "has_meeting_place": facility.has_meeting_place,
            "has_auto_kiosk": facility.has_auto_kiosk
        }

    # 2단계: Open API 조회 (실시간 엘리베이터 상태)
    elevator_status = SeoulMetroAPI.get_elevator_status(request.station_name)
    exit_closure = SeoulMetroAPI.check_exit_closure(
        request.station_name,
        request.exit_number
    )

    # 엘리베이터 상세 정보 (getWksnElvtr API)
    elevator_details = []
    if elevator_status.get('elevators'):
        for elev in elevator_status['elevators']:
            if elev.get('exit_number') == request.exit_number:
                elevator_details.append({
                    "location": elev.get('location', ''),  # "출구 왼쪽 10m"
                    "floor_info": elev.get('floor_info', ''),  # "지상 ~ 지하1층"
                    "status": elev.get('status', '정상'),
                    "last_check": elev.get('last_check_date', '')
                })

    api_data = {
        "elevator_status": elevator_status,
        "elevator_details": elevator_details,
        "exit_closure": exit_closure
    }

    # 3단계: 상태 판단
    status = "정상"
    alternative_route = None

    # 출입구 폐쇄 확인
    if exit_closure.get('is_closed', False):
        status = "경고"
        alternative_route = {
            "reason": exit_closure.get('reason', ''),
            "alternative": exit_closure.get('alternative', ''),
            "end_date": exit_closure.get('end_date', '')
        }

    # 엘리베이터 고장 확인
    elif not elevator_status.get('all_working', True):
        if request.need_elevator:
            status = "주의"
            # API 실시간 데이터에서 정상 작동하는 외부 엘리베이터 출구 찾기
            import re
            working_elevator_exits = []
            for elev in elevator_status.get('elevators', []):
                location = elev.get('location', '')
                match = re.search(r'(\d+)번\s*출입구', location)
                if match and elev.get('status') == '정상':
                    working_elevator_exits.append(match.group(1))

            # 정상 작동하는 엘리베이터 출구 중 현재 출구가 아닌 것 찾기
            alternative_exit = None
            for exit_num in working_elevator_exits:
                if exit_num != request.exit_number:
                    alt_exit = db.query(Exit).filter(
                        Exit.station_id == station.station_id,
                        Exit.exit_number == exit_num
                    ).first()
                    if alt_exit:
                        alternative_exit = alt_exit
                        break

            if alternative_exit:
                alternative_route = {
                    "reason": "엘리베이터 점검 중",
                    "alternative": f"{alternative_exit.exit_number}번 출구",
                    "alternative_gps": {
                        "lat": float(alternative_exit.latitude),
                        "lon": float(alternative_exit.longitude)
                    } if alternative_exit.latitude else None
                }

    # 4단계: 친절하고 자세한 안내문 생성 ⭐
    guide_text = _build_detailed_exit_guide(
        station=station,
        exit_obj=exit_obj,
        db_data=db_data,
        elevator_details=elevator_details,
        exit_closure=exit_closure,
        alternative_route=alternative_route,
        need_elevator=request.need_elevator
    )

    # 5단계: RAG로 추가 팁 보강
    rag_tip = rag_service.generate_guide(
        question=f"{request.station_name} {request.exit_number}번 출구 이용 팁",
        db_data=db_data,
        api_data=api_data
    )
    if rag_tip and len(rag_tip) > 20:
        guide_text += f"\n\n💡 {rag_tip}"

    return CheckpointGuideResponse(
        checkpoint_id=request.checkpoint_id,
        checkpoint_type="출입구",
        guide_text=guide_text,
        status=status,
        db_data=db_data,
        api_data=api_data,
        alternative_route=alternative_route
    )


def _build_detailed_exit_guide(
    station: Station,
    exit_obj: Exit,
    db_data: Dict,
    elevator_details: List[Dict],
    exit_closure: Dict,
    alternative_route: Optional[Dict],
    need_elevator: bool
) -> str:
    """DB + API 데이터로 자세한 출입구 안내문 생성 (UI 이미지 기준 개선)"""

    guide_parts = []

    # 1. 도착 인사
    guide_parts.append(f"🚇 {station.name} {db_data.get('exit_number', '')}번 출구에 도착하셨습니다.")

    # 2. 출입구 폐쇄 경고
    if exit_closure.get('is_closed', False):
        guide_parts.append(f"\n\n⚠️ 죄송합니다. 현재 이 출구는 {exit_closure.get('reason', '공사')}로 인해 사용하실 수 없습니다.")
        if alternative_route:
            guide_parts.append(f"대신 {alternative_route['alternative']}을 이용해주세요.")
            if alternative_route.get('end_date'):
                guide_parts.append(f"({alternative_route['end_date']}까지 폐쇄 예정)")
        return " ".join(guide_parts)

    # 3. 엘리베이터 상세 안내 (핵심 개선!)
    if need_elevator and db_data.get('has_elevator'):
        guide_parts.append(f"\n\n🛗 엘리베이터 상태: 정상 운행")

        # 엘리베이터 위치 (DB 필드 우선 사용)
        elevator_location = db_data.get('elevator_location')
        if not elevator_location and elevator_details:
            elevator_location = elevator_details[0].get('location', '')

        if elevator_location:
            guide_parts.append(f"\n위치: {elevator_location}")

        # 버튼 안내 (UI 이미지: "지하 2층 버튼을 누르세요")
        button_info = db_data.get('elevator_button_info')
        if button_info:
            guide_parts.append(f"\n{button_info}")
        elif db_data.get('floor_level'):
            floor = db_data['floor_level']
            if 'B' in floor:
                guide_parts.append(f"\n지하 {floor.replace('B', '')}층 버튼을 누르세요.")

        # 소요 시간 (UI 이미지: "약 1분 정도 걸려요")
        elevator_time = db_data.get('elevator_time_seconds')
        if elevator_time:
            minutes = elevator_time // 60
            if minutes >= 1:
                guide_parts.append(f"\n약 {minutes}분 정도 걸려요.")
            else:
                guide_parts.append(f"\n약 {elevator_time}초 정도 걸려요.")

        # 실시간 상태 확인
        if elevator_details:
            elev = elevator_details[0]
            if elev.get('status') != '정상':
                guide_parts.append(f"\n⚠️ 현재 {elev.get('status')}입니다.")
                if alternative_route:
                    guide_parts.append(f"{alternative_route['alternative']} 엘리베이터를 이용해주세요.")

        # 하차 후 방향 안내 (UI 이미지: "하차 후 승강장에 진입하세요")
        gate_direction = db_data.get('gate_direction')
        if gate_direction:
            guide_parts.append(f"\n\n{gate_direction}")
        else:
            guide_parts.append("\n\n하차 후 승강장에 진입하세요.")

    elif need_elevator and not db_data.get('has_elevator'):
        guide_parts.append("\n\n⚠️ 이 출구에는 엘리베이터가 없습니다.")
        if alternative_route:
            guide_parts.append(f"{alternative_route['alternative']}에 엘리베이터가 있으니 그쪽으로 이동해주세요.")

    # 4. 상세 위치 설명 (랜드마크)
    if db_data.get('description'):
        guide_parts.append(f"\n\n📍 {db_data['description']}")

    # 5. 편의시설 안내 (간소화)
    facilities = db_data.get('facilities', {})
    facility_list = []
    if facilities.get('has_nursing_room'):
        facility_list.append("수유실")
    if facilities.get('has_meeting_place'):
        facility_list.append("만남의 장소")
    if facilities.get('has_auto_kiosk'):
        facility_list.append("무인발매기")

    if facility_list:
        guide_parts.append(f"\n\n🏢 이 역에는 {', '.join(facility_list)}이 있습니다.")

    return " ".join(guide_parts)


async def _handle_platform_checkpoint(
    request: CheckpointGuideRequest,
    station: Station,
    db: Session
) -> CheckpointGuideResponse:
    """
    승강장 체크포인트 처리 (5단계)
    """

    # 1단계: DB 조회 (승강장 정보 + 연단 정보)
    from app.models import PlatformInfo, PlatformEdge

    direction = request.get_direction()

    platform = db.query(PlatformInfo).filter(
        PlatformInfo.station_id == station.station_id,
        PlatformInfo.direction.contains(direction)
    ).first()

    db_data = {
        "station": station.name,
        "line": request.line or station.line,
        "direction": direction,
        "platform_type": platform.platform_type if platform else None,
        "floor_level": platform.floor_level if platform else None
    }

    # 연단(승강장 끝) 정보 조회
    if platform:
        edges = db.query(PlatformEdge).filter(
            PlatformEdge.platform_id == platform.platform_id
        ).all()

        db_data["edges"] = [
            {
                "car_position": edge.car_position,  # "본선 오이도 방면 1-3"
                "car_number": edge.car_number,  # 1, 2, 3, ... 10
                "door_number": edge.door_number,  # 1, 2, 3, 4
                "gap_width": edge.gap_width,  # "넓음", "보통", "좁음"
                "height_diff": edge.height_diff,  # "낮음", "보통", "높음"
                "platform_shape": edge.platform_shape  # "곡선", "직선"
            }
            for edge in edges
        ]

    # 2단계: Open API 조회 (실시간 열차 정보)
    elevator_status = SeoulMetroAPI.get_elevator_status(request.station_name)

    # 실시간 열차 도착 정보 ⭐ (RealtimeSubwayAPI 사용)
    realtime_arrivals = RealtimeSubwayAPI.get_realtime_station_arrival(request.station_name)

    # 다음 열차 정보 추출
    train_arrival = {
        "next_train_minutes": 3,  # 기본값
        "train_direction": direction,
        "is_express": False
    }

    if realtime_arrivals:
        # 첫 번째 도착 예정 열차
        first_train = realtime_arrivals[0]
        arrival_seconds = first_train.get('arrival_seconds', 180)
        train_arrival = {
            "next_train_minutes": max(1, arrival_seconds // 60),
            "train_direction": first_train.get('train_line_name', direction),
            "is_express": first_train.get('train_status', '일반') in ['급행', '특급', 'ITX'],
            "arrival_message": first_train.get('arrival_detail', ''),
            "last_car": first_train.get('is_last_train', False)
        }

    api_data = {
        "elevator_status": elevator_status,
        "train_arrival": train_arrival
    }

    # 3단계: 자세한 안내문 생성
    guide_text = _build_detailed_platform_guide(
        station=station,
        platform=platform,
        db_data=db_data,
        train_arrival=train_arrival,
        need_elevator=request.need_elevator
    )

    # 4단계: RAG로 추가 팁 보강
    rag_tip = rag_service.generate_guide(
        question=f"{request.station_name} 승강장에서 빠르게 타는 방법",
        db_data=db_data,
        api_data=api_data
    )
    if rag_tip and len(rag_tip) > 20:
        guide_text += f"\n\n💡 {rag_tip}"

    return CheckpointGuideResponse(
        checkpoint_id=request.checkpoint_id,
        checkpoint_type="승강장",
        guide_text=guide_text,
        status="정상",
        db_data=db_data,
        api_data=api_data
    )


def _build_detailed_platform_guide(
    station: Station,
    platform: Optional[PlatformInfo],
    db_data: Dict,
    train_arrival: Dict,
    need_elevator: bool
) -> str:
    """DB + API 데이터로 자세한 승강장 안내문 생성"""
    
    guide_parts = []

    # 1. 승강장 도착 인사
    guide_parts.append(f"🚉 {station.name} {db_data.get('direction', '')} 승강장에 도착하셨습니다.")

    # 2. 층 정보
    if db_data.get('floor_level'):
        floor = db_data['floor_level']
        if 'B' in floor:
            guide_parts.append(f"지하 {floor.replace('B', '')}층입니다.")
        else:
            guide_parts.append(f"{floor}층입니다.")

    # 3. 승강장 타입 설명
    if db_data.get('platform_type'):
        ptype = db_data['platform_type']
        if ptype == "섬식":
            guide_parts.append("\n양쪽에서 열차가 들어오는 섬식 승강장입니다.")
        elif ptype == "상대식":
            guide_parts.append("\n방향별로 승강장이 나뉘어 있습니다.")

    # 4. 최적 탑승 위치 안내 (연단 정보 활용)
    edges = db_data.get('edges', [])
    if edges:
        if need_elevator:
            # 연단간격이 넓고 높이차가 낮은 칸 찾기 (휠체어 승하차 편함)
            best_edges = [e for e in edges if e.get('gap_width') == '넓음' and e.get('height_diff') == '낮음']
            if best_edges:
                car_nums = sorted(set(e.get('car_number') for e in best_edges if e.get('car_number')))
                if car_nums:
                    guide_parts.append(f"\n\n🎯 {car_nums[0]}-{car_nums[-1] if len(car_nums) > 1 else car_nums[0]}번째 칸 위치에서 기다려주세요.")
                    guide_parts.append("이곳은 승강장과 열차 사이 간격이 좁아 승하차가 편합니다.")
                    guide_parts.append("도착역에서 내리실 때 엘리베이터와 가장 가까운 위치입니다.")
        else:
            # 일반 사용자는 중간 칸 찾기
            middle_edges = [e for e in edges if e.get('car_number') and 5 <= e.get('car_number') <= 6]
            if middle_edges:
                guide_parts.append(f"\n\n🎯 5-6번째 칸 중간 위치에서 기다려주세요.")

    # 5. 실시간 열차 도착 정보
    if train_arrival.get('next_train_minutes'):
        minutes = train_arrival['next_train_minutes']
        if minutes <= 1:
            guide_parts.append(f"\n\n🚇 곧 열차가 도착합니다. 안전선 안쪽에서 기다려주세요.")
        else:
            guide_parts.append(f"\n\n🚇 약 {minutes}분 후 열차가 도착합니다.")

    # 6. 안전 안내
    guide_parts.append("\n\n⚠️ 열차가 완전히 멈춘 후 타세요. 서두르지 마세요.")

    # 7. 다음 단계
    guide_parts.append("열차 문이 열리면 천천히 탑승하세요.")

    return " ".join(guide_parts)


async def _handle_arrival_platform_checkpoint(
    request: CheckpointGuideRequest,
    station: Station,
    db: Session
) -> CheckpointGuideResponse:
    """
    도착역 승강장 체크포인트 처리 - 하차 후 출구까지 상세 안내
    (UI 이미지: "7-8번째 칸에서 하차 후 우측으로 가세요")
    """
    from app.models import ElevatorExitMapping

    # 1단계: DB 조회
    db_data = {
        "station": station.name,
        "line": station.line
    }

    # 엘리베이터 있는 출입구 찾기
    exits_with_elevator = db.query(Exit).filter(
        Exit.station_id == station.station_id,
        Exit.has_elevator == True
    ).all()

    if exits_with_elevator:
        db_data["elevator_exits"] = [e.exit_number for e in exits_with_elevator]

    # 엘리베이터-출구 매핑 정보 조회
    elevator_mappings = db.query(ElevatorExitMapping).filter(
        ElevatorExitMapping.station_id == station.station_id
    ).all()

    # 2단계: Open API 조회
    elevator_status = SeoulMetroAPI.get_elevator_status(request.station_name)

    # 해당 역의 엘리베이터만 필터링
    station_key = station.name.replace("역", "")
    filtered_elevators = []
    for elev in elevator_status.get('elevators', []):
        elev_station = elev.get('station_name', '').replace("역", "")
        if station_key == elev_station.replace("(2)", "").replace("(8)", "").strip():
            filtered_elevators.append(elev)

    api_data = {
        "elevator_status": {
            "elevators": filtered_elevators,
            "all_working": all(e.get('status') == '정상' for e in filtered_elevators) if filtered_elevators else True
        }
    }

    # 3단계: 상세 안내문 생성 (UI 이미지 기준)
    guide_parts = []

    guide_parts.append(f"🚉 {station.name}에 도착하셨습니다.")
    guide_parts.append("\n\n하차를 준비하세요.")

    # 출구 및 엘리베이터 안내
    if elevator_mappings:
        # 첫 번째 매핑 정보 사용
        mapping = elevator_mappings[0]

        car_position = f"{mapping.car_position_start}-{mapping.car_position_end}번째 칸" if mapping.car_position_start else ""
        direction = mapping.direction_from_train or "앞쪽"

        if car_position:
            guide_parts.append(f"\n{car_position}에서 하차 후 {direction}으로 가세요.")

        if mapping.elevator_location:
            guide_parts.append(f"\n\n🛗 {mapping.elevator_location}에 있는 엘리베이터를 이용하시면")
            guide_parts.append(f"{mapping.connected_exit}번 출구로 나가실 수 있습니다.")

        if mapping.walking_distance_meters:
            time_seconds = mapping.walking_time_seconds or (mapping.walking_distance_meters // 1.2)
            time_minutes = max(1, int(time_seconds // 60))
            guide_parts.append(f"\n\n📍 추천, 큰길우선, 계단회피")
            guide_parts.append(f"\n약 {time_minutes}분")

    elif exits_with_elevator:
        # 매핑 정보가 없으면 기본 출구 안내
        primary_exit = exits_with_elevator[0]
        guide_parts.append(f"\n\n🛗 {primary_exit.exit_number}번 출구로 가세요.")
        guide_parts.append("엘리베이터가 있습니다.")

        if len(exits_with_elevator) > 1:
            other_exits = ", ".join([f"{e.exit_number}번" for e in exits_with_elevator[1:3]])
            guide_parts.append(f"\n\n또는 {other_exits} 출구도 엘리베이터가 있습니다.")
    else:
        guide_parts.append("\n\n안내 표지판을 따라 출구로 이동하세요.")

    # 4단계: RAG로 추가 팁 보강
    rag_tip = rag_service.generate_guide(
        question=f"{station.name} 하차 후 엘리베이터 이용 팁",
        db_data=db_data,
        api_data=api_data
    )
    if rag_tip and len(rag_tip) > 20:
        guide_parts.append(f"\n\n💡 {rag_tip}")

    guide_text = " ".join(guide_parts)

    return CheckpointGuideResponse(
        checkpoint_id=request.checkpoint_id,
        checkpoint_type="도착역_승강장",
        guide_text=guide_text,
        status="정상",
        db_data=db_data,
        api_data=api_data
    )


@router.get("/realtime/{station_name}")
async def get_realtime_info(station_name: str):
    """
    역의 실시간 정보 조회
    
    - 엘리베이터 상태
    - 출입구 폐쇄 여부
    - 휠체어 충전소 위치
    """

    elevator_status = SeoulMetroAPI.get_elevator_status(station_name)
    exit_closures = SeoulMetroAPI.check_exit_closure(station_name)
    chargers = SeoulMetroAPI.get_wheelchair_chargers(station_name)

    return {
        "station": station_name,
        "elevator_status": elevator_status,
        "exit_closures": exit_closures,
        "chargers": chargers
    }
