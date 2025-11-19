"""
DB 마이그레이션: 배리어프리 필드 추가
- Exit 테이블에 상세 안내 필드 추가
- ElevatorExitMapping 테이블 생성
- BarrierFreeRoute 테이블 생성

실행 방법:
    python migrations/add_barrier_free_fields.py
"""

import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.config import settings


def run_migration():
    """마이그레이션 실행"""

    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("🔄 Starting migration: Add barrier-free fields...")

        # 1. Exit 테이블에 새 필드 추가
        print("\n📝 Adding new fields to 'exits' table...")

        exit_columns = [
            ("elevator_location", "VARCHAR(100)", "엘리베이터 위치 (출구 왼쪽 10m)"),
            ("elevator_button_info", "VARCHAR(100)", "버튼 안내 (지하 2층 버튼을 누르세요)"),
            ("elevator_time_seconds", "INTEGER", "엘리베이터 소요 시간"),
            ("gate_direction", "VARCHAR(100)", "개찰구 방향 안내"),
            ("landmark", "VARCHAR(200)", "랜드마크 (스타벅스 옆)"),
            ("has_slope", "BOOLEAN DEFAULT FALSE", "경사로 여부"),
            ("slope_info", "VARCHAR(100)", "경사로 정보"),
        ]

        for column_name, column_type, description in exit_columns:
            try:
                conn.execute(text(f"ALTER TABLE exits ADD COLUMN {column_name} {column_type}"))
                print(f"  ✅ Added: {column_name} ({description})")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  ⏭️  Skipped: {column_name} (already exists)")
                else:
                    print(f"  ❌ Error adding {column_name}: {e}")

        # 2. ElevatorExitMapping 테이블 생성
        print("\n📝 Creating 'elevator_exit_mapping' table...")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS elevator_exit_mapping (
                    mapping_id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    station_id INTEGER NOT NULL,

                    -- 엘리베이터 정보
                    elevator_name VARCHAR(100),
                    elevator_location VARCHAR(100),
                    elevator_floors VARCHAR(50),

                    -- 연결된 출구 정보
                    connected_exit VARCHAR(10),

                    -- 탑승 위치 정보
                    car_position_start INTEGER,
                    car_position_end INTEGER,
                    direction_from_train VARCHAR(50),

                    -- 도보 안내
                    walking_distance_meters INTEGER,
                    walking_time_seconds INTEGER,
                    walking_direction VARCHAR(200),

                    -- 외래 키
                    FOREIGN KEY (station_id) REFERENCES stations(station_id) ON DELETE CASCADE,

                    -- 인덱스
                    INDEX idx_station_id (station_id),
                    INDEX idx_connected_exit (connected_exit)
                )
            """))
            print("  ✅ Created: elevator_exit_mapping")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  ⏭️  Skipped: elevator_exit_mapping (already exists)")
            else:
                print(f"  ❌ Error: {e}")

        # 3. BarrierFreeRoute 테이블 생성
        print("\n📝 Creating 'barrier_free_routes' table...")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS barrier_free_routes (
                    route_id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    station_id INTEGER NOT NULL,

                    -- 경로 타입
                    route_type VARCHAR(50),

                    -- 출발/도착 정보
                    from_location VARCHAR(100),
                    to_location VARCHAR(100),

                    -- 경로 상세
                    distance_meters INTEGER,
                    time_seconds INTEGER,

                    -- 상세 안내
                    step_by_step_guide TEXT,

                    -- 경로 특성
                    has_slope BOOLEAN DEFAULT FALSE,
                    slope_warning VARCHAR(100),
                    has_stairs BOOLEAN DEFAULT FALSE,
                    prefer_big_road BOOLEAN DEFAULT TRUE,

                    -- 추천 점수
                    accessibility_score INTEGER DEFAULT 100,

                    -- 외래 키
                    FOREIGN KEY (station_id) REFERENCES stations(station_id) ON DELETE CASCADE,

                    -- 인덱스
                    INDEX idx_station_id (station_id),
                    INDEX idx_route_type (route_type)
                )
            """))
            print("  ✅ Created: barrier_free_routes")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  ⏭️  Skipped: barrier_free_routes (already exists)")
            else:
                print(f"  ❌ Error: {e}")

        conn.commit()
        print("\n✅ Migration completed successfully!")


def rollback_migration():
    """마이그레이션 롤백"""

    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("🔄 Rolling back migration...")

        # 테이블 삭제
        tables = ["barrier_free_routes", "elevator_exit_mapping"]
        for table in tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                print(f"  ✅ Dropped: {table}")
            except Exception as e:
                print(f"  ❌ Error dropping {table}: {e}")

        # 컬럼 삭제 (Exit 테이블)
        columns = [
            "elevator_location", "elevator_button_info", "elevator_time_seconds",
            "gate_direction", "landmark", "has_slope", "slope_info"
        ]
        for column in columns:
            try:
                conn.execute(text(f"ALTER TABLE exits DROP COLUMN {column}"))
                print(f"  ✅ Dropped column: {column}")
            except Exception as e:
                print(f"  ⏭️  Skipped: {column}")

        conn.commit()
        print("\n✅ Rollback completed!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DB Migration for barrier-free fields")
    parser.add_argument("--rollback", action="store_true", help="Rollback migration")
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        run_migration()
