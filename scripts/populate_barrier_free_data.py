"""
Open API에서 배리어프리 데이터 수집 및 DB 저장

실행 방법:
    python scripts/populate_barrier_free_data.py

기능:
    1. 엘리베이터 정보 → Exit 테이블 업데이트
    2. 엘리베이터-출구 매핑 → ElevatorExitMapping 테이블
    3. 휠체어 충전소 정보
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Station, Exit, StationFacility
from app.services.api_service import GeneralSeoulAPI
from loguru import logger


def populate_elevator_data():
    """Open API에서 엘리베이터 정보를 가져와 Exit 테이블 업데이트"""

    logger.info("📥 Fetching elevator data from Open API...")

    db = SessionLocal()

    try:
        # 1. Open API에서 전체 엘리베이터 데이터 수집
        elevator_data = GeneralSeoulAPI.get_elevator_status()
        elevators = elevator_data.get('elevators', [])

        logger.info(f"✅ Fetched {len(elevators)} elevators from API")

        # 2. 역별로 그룹화
        station_elevators = {}
        for elev in elevators:
            station_name = elev.get('station_name', '')
            if not station_name:
                continue

            # 역 이름 정규화 (호선 정보 제거)
            clean_name = re.sub(r'\(\d+\)', '', station_name).strip()

            if clean_name not in station_elevators:
                station_elevators[clean_name] = []
            station_elevators[clean_name].append(elev)

        # 3. 각 역의 Exit 테이블 업데이트
        updated_count = 0

        for station_name, elevs in station_elevators.items():
            # DB에서 역 찾기
            station = db.query(Station).filter(
                Station.name.like(f"%{station_name}%")
            ).first()

            if not station:
                continue

            # 외부 엘리베이터 (출구 연결) 찾기
            external_elevators = [
                e for e in elevs
                if '출입구' in e.get('location', '') or '출구' in e.get('location', '')
            ]

            for elev in external_elevators:
                location = elev.get('location', '')

                # 출구 번호 추출
                exit_match = re.search(r'(\d+)번?\s*출', location)
                if not exit_match:
                    continue

                exit_number = exit_match.group(1)

                # Exit 레코드 찾기
                exit_obj = db.query(Exit).filter(
                    Exit.station_id == station.station_id,
                    Exit.exit_number == exit_number
                ).first()

                if exit_obj:
                    # 엘리베이터 정보 업데이트
                    exit_obj.has_elevator = True
                    exit_obj.elevator_type = "외부E/V"

                    # elevator_location 설정 (API 데이터 활용)
                    if not exit_obj.elevator_location:
                        exit_obj.elevator_location = f"{exit_number}번 출입구"

                    # 층 정보에서 버튼 안내 생성
                    floors = elev.get('floors', '')
                    if floors and not exit_obj.elevator_button_info:
                        # "B1-1F" → "지하 1층 버튼을 누르세요"
                        if 'B2' in floors:
                            exit_obj.elevator_button_info = "지하 2층 버튼을 누르세요"
                        elif 'B1' in floors:
                            exit_obj.elevator_button_info = "지하 1층 버튼을 누르세요"

                    # 기본 소요 시간 설정
                    if not exit_obj.elevator_time_seconds:
                        exit_obj.elevator_time_seconds = 60

                    updated_count += 1

        db.commit()
        logger.info(f"✅ Updated {updated_count} exit records with elevator info")

    except Exception as e:
        logger.error(f"❌ Error populating elevator data: {e}")
        db.rollback()
    finally:
        db.close()


def populate_elevator_exit_mapping():
    """엘리베이터-출구 매핑 데이터 생성"""

    logger.info("📥 Creating elevator-exit mapping...")

    db = SessionLocal()

    try:
        from app.models import ElevatorExitMapping

        # Open API에서 엘리베이터 데이터
        elevator_data = GeneralSeoulAPI.get_elevator_status()
        elevators = elevator_data.get('elevators', [])

        # 역별로 내부 엘리베이터 분석
        created_count = 0

        for elev in elevators:
            station_name = elev.get('station_name', '')
            location = elev.get('location', '')
            floors = elev.get('floors', '')
            name = elev.get('name', '')

            if not station_name or not location:
                continue

            # 내부 엘리베이터만 (승강장 연결)
            if '내부' not in name:
                continue

            # 역 찾기
            clean_name = re.sub(r'\(\d+\)', '', station_name).strip()
            station = db.query(Station).filter(
                Station.name.like(f"%{clean_name}%")
            ).first()

            if not station:
                continue

            # 위치에서 방면과 칸 번호 추출
            # 예: "잠실새내 방면6-3" → 방면=잠실새내, 칸=6-3
            direction_match = re.search(r'(.+)\s*방면\s*(\d+)-?(\d+)?', location)
            if direction_match:
                direction = direction_match.group(1).strip()
                car_start = int(direction_match.group(2))
                car_end = int(direction_match.group(3)) if direction_match.group(3) else car_start

                # 연결된 출구 찾기 (가장 가까운 엘리베이터 있는 출구)
                exits_with_elev = db.query(Exit).filter(
                    Exit.station_id == station.station_id,
                    Exit.has_elevator == True
                ).all()

                if exits_with_elev:
                    # 기존 매핑 확인
                    existing = db.query(ElevatorExitMapping).filter(
                        ElevatorExitMapping.station_id == station.station_id,
                        ElevatorExitMapping.elevator_location == location
                    ).first()

                    if not existing:
                        mapping = ElevatorExitMapping(
                            station_id=station.station_id,
                            elevator_name=name,
                            elevator_location=location,
                            elevator_floors=floors,
                            connected_exit=exits_with_elev[0].exit_number,
                            car_position_start=car_start,
                            car_position_end=car_end,
                            direction_from_train="앞쪽" if car_start <= 5 else "뒤쪽",
                            walking_distance_meters=30,
                            walking_time_seconds=30,
                            walking_direction=f"{car_start}-{car_end}번째 칸에서 하차 후 {'앞쪽' if car_start <= 5 else '뒤쪽'}으로 이동하세요"
                        )
                        db.add(mapping)
                        created_count += 1

        db.commit()
        logger.info(f"✅ Created {created_count} elevator-exit mappings")

    except Exception as e:
        logger.error(f"❌ Error creating elevator-exit mapping: {e}")
        db.rollback()
    finally:
        db.close()


def populate_charger_data():
    """휠체어 충전소 정보 업데이트"""

    logger.info("📥 Fetching wheelchair charger data from Open API...")

    db = SessionLocal()

    try:
        # Open API에서 충전소 데이터
        charger_data = GeneralSeoulAPI.get_wheelchair_chargers()

        logger.info(f"✅ Fetched {len(charger_data)} chargers from API")

        # StationFacility 테이블 업데이트
        updated_count = 0

        for charger in charger_data:
            station_name = charger.get('station_name', '')

            if not station_name:
                continue

            # 역 찾기
            station = db.query(Station).filter(
                Station.name.like(f"%{station_name}%")
            ).first()

            if not station:
                continue

            # 편의시설 정보 업데이트
            facility = db.query(StationFacility).filter(
                StationFacility.station_id == station.station_id
            ).first()

            if facility:
                facility.has_wheelchair_charger = True
                updated_count += 1

        db.commit()
        logger.info(f"✅ Updated {updated_count} station facilities with charger info")

    except Exception as e:
        logger.error(f"❌ Error populating charger data: {e}")
        db.rollback()
    finally:
        db.close()


def main():
    """전체 데이터 수집 실행"""

    logger.info("🚀 Starting barrier-free data population...")

    # 1. 엘리베이터 정보
    populate_elevator_data()

    # 2. 엘리베이터-출구 매핑
    populate_elevator_exit_mapping()

    # 3. 충전소 정보
    populate_charger_data()

    logger.info("✅ All data population completed!")


if __name__ == "__main__":
    main()
