"""
CSV 데이터를 PostgreSQL DB에 임포트하는 스크립트

CSV 인코딩 정보:
- stations.csv: UTF-8
- station_exit_coordinates.csv: UTF-8
- facilities.csv: EUC-KR
- 서울교통공사_*.csv: EUC-KR

기획 문서: [최종] 비파이 실시간 길안내 서비스.md
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import (
    Station, StationFacility, Exit, PlatformInfo,
    PlatformEdge, Route, ExitToPlatform, OptimalBoarding,
    TransferInfo, ChargingStation
)


# CSV 파일 경로
# Docker 컨테이너 내부에서는 /app/static_data
# 로컬에서는 backend/../static_data
if os.path.exists("/app/static_data"):
    CSV_BASE_PATH = Path("/app/static_data")
else:
    CSV_BASE_PATH = Path(__file__).parent.parent.parent / "static_data"


def init_database():
    """데이터베이스 초기화 (테이블 생성)"""
    print("📦 Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully!")


def import_stations(db: Session):
    """
    stations.csv 임포트
    인코딩: UTF-8
    """
    print("\n📍 Importing stations...")

    file_path = CSV_BASE_PATH / "stations.csv"
    df = pd.read_csv(file_path, encoding='utf-8')

    count = 0
    for _, row in df.iterrows():
        station_id = int(row['station_id'])
        
        # 중복 체크
        existing = db.query(Station).filter(Station.station_id == station_id).first()
        
        if not existing:
            station = Station(
                station_id=station_id,
                name=row['name'],
                line=row['line'],
                latitude=float(row['lat']),
                longitude=float(row['lon'])
            )
            db.add(station)
            count += 1

    db.commit()
    print(f"✅ Imported {count} new stations (skipped {len(df) - count} duplicates)")


def import_facilities(db: Session):
    """
    facilities.csv 임포트
    인코딩: EUC-KR
    """
    print("\n🏢 Importing station facilities...")

    file_path = CSV_BASE_PATH / "facilities.csv"
    df = pd.read_csv(file_path, encoding='euc-kr')

    count = 0
    for _, row in df.iterrows():
        try:
            station_name = row['지하철역명']
            station = db.query(Station).filter(Station.name.contains(station_name[:2])).first()

            if station:
                # 중복 체크
                existing = db.query(StationFacility).filter(
                    StationFacility.station_id == station.station_id
                ).first()
                
                if not existing:
                    facility = StationFacility(
                        station_id=station.station_id,
                        station_code=row['지하철역ID'],
                        line=row['호선'],
                        has_elevator=(row['엘리베이터유무'] == 'Y'),
                        has_wheelchair_lift=(row['휘체어리프트유무'] == 'Y') if '휘체어리프트유무' in row else False,
                        has_transfer_parking=(row['환승주차자유무'] == 'N') if '환승주차자유무' in row else False,
                    )
                    db.add(facility)
                    count += 1
        except Exception as e:
            print(f"⚠️ Error importing facility: {e}")
            continue

    db.commit()
    print(f"✅ Imported {count} station facilities")


def import_exits(db: Session):
    """
    출입구 정보 임포트
    
    데이터 소스:
    1. station_exit_coordinates.csv (UTF-8) - 모든 출입구 GPS 좌표
    2. 서울교통공사 휠체어경사로 설치 현황_20240331.csv (EUC-KR) - 엘리베이터 정보
    """
    print("\n🚪 Importing exits with GPS coordinates...")

  # 1. 출입구 GPS 좌표 로드
    coords_file = CSV_BASE_PATH / "station_exit_coordinates.csv"
    # utf-8-sig가 안 먹힐 경우를 대비해 utf-8로 읽고 강제 처리
    coords_df = pd.read_csv(coords_file, encoding='utf-8') 
    
    # ✅ [핵심] 컬럼명 강제 청소 (BOM 문자 제거 + 공백 제거)
    coords_df.columns = coords_df.columns.str.replace('\ufeff', '').str.strip()
    
    # 확인용 디버그 코드 (그대로 두셔도 됩니다)
    print(f"🔍 Cleaned Columns: {coords_df.columns.tolist()}")

    # 2. 엘리베이터 정보 로드 (EUC-KR)
    elevator_file = CSV_BASE_PATH / "서울교통공사 휠체어경사로 설치 현황_20240331.csv"
    elevator_df = pd.read_csv(elevator_file, encoding='euc-kr')

    # 3. 엘리베이터 있는 출입구 딕셔너리 생성
    elevator_exits = {}  # {역명: [출입구번호, ...]}
    for _, row in elevator_df.iterrows():
        if row['구분'] == '외부E/V' and '#' in str(row['위치']):
            station_name = row['역명']
            try:
                exit_num = str(row['위치']).replace('#', '').strip()
                if station_name not in elevator_exits:
                    elevator_exits[station_name] = []
                elevator_exits[station_name].append(exit_num)
            except:
                continue

    # 4. 모든 출입구 임포트
    count = 0
    for _, row in coords_df.iterrows():
        try:
            station_id = int(row['station_id'])
            station_name = row['station_name'].replace('역', '')
            exit_number_str = str(row['exit_number'])
            latitude = float(row['lat'])
            longitude = float(row['lon'])

            # 엘리베이터 유무 확인
            has_elevator = False
            if station_name in elevator_exits:
                has_elevator = exit_number_str in elevator_exits[station_name]

            # 중복 체크
            existing = db.query(Exit).filter(
                Exit.station_id == station_id,
                Exit.exit_number == exit_number_str
            ).first()

            if not existing:
                exit_obj = Exit(
                    station_id=station_id,
                    exit_number=exit_number_str,
                    has_elevator=has_elevator,
                    elevator_type='외부E/V' if has_elevator else None,
                    latitude=latitude,
                    longitude=longitude
                )
                db.add(exit_obj)
                count += 1
        except Exception as e:
            print(f"⚠️ Error importing exit: {e}")
            continue

    db.commit()

    # 통계 출력
    total_exits = db.query(Exit).count()
    elevator_count = db.query(Exit).filter(Exit.has_elevator == True).count()
    print(f"✅ Imported {count} exits")
    print(f"   📊 Total: {total_exits} exits, {elevator_count} with elevators")


def import_platform_edges(db: Session):
    """
    연단정보.csv 임포트 (샘플만)
    인코딩: EUC-KR
    """
    print("\n🚇 Importing platform edges (sample)...")

    file_path = CSV_BASE_PATH / "서울교통공사_연단정보와 곡선구간 정보.csv"

    try:
        # 너무 크므로 처음 1000개만 임포트
        df = pd.read_csv(file_path, encoding='euc-kr', nrows=1000)

        count = 0
        for _, row in df.iterrows():
            try:
                station_name = row['역명']
                station = db.query(Station).filter(Station.name.contains(station_name[:2])).first()

                if station:
                    edge = PlatformEdge(
                        station_id=station.station_id,
                        line=row['호선'],
                        direction=row['상하선'] if '상하선' in row else None,
                        car_position=row['승강장위치'] if '승강장위치' in row else None,
                        gap_width=row['연단간격'] if '연단간격' in row else None,
                        height_diff=row['높이차'] if '높이차' in row else None,
                        platform_shape=row['승강장선형'] if '승강장선형' in row else None
                    )
                    db.add(edge)
                    count += 1
            except Exception as e:
                continue

        db.commit()
        print(f"✅ Imported {count} platform edges (sample)")
    except Exception as e:
        print(f"⚠️ Error importing platform edges: {e}")


def import_transfer_info(db: Session):
    """
    환승역 정보 임포트
    인코딩: EUC-KR
    """
    print("\n🔄 Importing transfer info...")

    file_path = CSV_BASE_PATH / "서울교통공사_환승역거리 소요시간 정보_20250331.csv"

    try:
        df = pd.read_csv(file_path, encoding='euc-kr')

        count = 0
        for _, row in df.iterrows():
            try:
                station_name = row['환승역명']
                station = db.query(Station).filter(Station.name.contains(station_name[:2])).first()

                if station:
                    transfer = TransferInfo(
                        station_id=station.station_id,
                        from_line=row['호선'],
                        to_line=row['환승노선'],
                        distance_meters=int(row['환승거리']),
                        time_seconds=int(row['환승소요시간'].replace(':', ''))
                    )
                    db.add(transfer)
                    count += 1
            except Exception as e:
                continue

        db.commit()
        print(f"✅ Imported {count} transfer routes")
    except Exception as e:
        print(f"⚠️ Error importing transfer info: {e}")


# 더미 데이터 생성 함수 제거
# routes와 optimal_boarding은 API 호출 시 실시간 계산됨


def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("🚀 B-FAI Database Import Script")
    print("=" * 60)

    # 데이터베이스 초기화
    init_database()

    # 세션 생성
    db = SessionLocal()

    try:
        # CSV 데이터 임포트 (실제 데이터만)
        import_stations(db)
        import_facilities(db)
        import_exits(db)
        import_platform_edges(db)
        import_transfer_info(db)

        print("\n" + "=" * 60)
        print("✅ All data imported successfully!")
        print("=" * 60)

        # 최종 통계
        print("\n📊 Database Statistics:")
        print(f"   Stations: {db.query(Station).count()}")
        print(f"   Exits: {db.query(Exit).count()}")
        print(f"   Facilities: {db.query(StationFacility).count()}")
        print(f"   Platform Edges: {db.query(PlatformEdge).count()}")
        print(f"   Transfer Info: {db.query(TransferInfo).count()}")
        print("\n⚠️  Note: Routes and optimal boarding are calculated in real-time via API")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
