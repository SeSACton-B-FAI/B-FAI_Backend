"""
SQLAlchemy models for B-FAI database
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Text, ForeignKey,
    DECIMAL, TIMESTAMP, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Station(Base):
    """역 정보 (기준 테이블)"""
    __tablename__ = "stations"

    station_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    line = Column(String(20), nullable=False, index=True)
    latitude = Column(DECIMAL(10, 8), nullable=False)
    longitude = Column(DECIMAL(11, 8), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    facilities = relationship("StationFacility", back_populates="station", cascade="all, delete-orphan")
    exits = relationship("Exit", back_populates="station", cascade="all, delete-orphan")
    platforms = relationship("PlatformInfo", back_populates="station", cascade="all, delete-orphan")
    routes_start = relationship("Route", foreign_keys="Route.start_station_id", back_populates="start_station")
    routes_end = relationship("Route", foreign_keys="Route.end_station_id", back_populates="end_station")

    def __repr__(self):
        return f"<Station(name='{self.name}', line='{self.line}')>"


class StationFacility(Base):
    """역 편의시설 정보"""
    __tablename__ = "station_facilities"

    facility_id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.station_id", ondelete="CASCADE"), nullable=False)
    station_code = Column(String(10))
    line = Column(String(20))
    has_elevator = Column(Boolean, default=False)
    has_wheelchair_lift = Column(Boolean, default=False)
    has_transfer_parking = Column(Boolean, default=False)
    has_bike_storage = Column(Boolean, default=False)
    has_auto_kiosk = Column(Boolean, default=False)
    has_meeting_place = Column(Boolean, default=False)
    has_nursing_room = Column(Boolean, default=False)

    # Relationship
    station = relationship("Station", back_populates="facilities")

    def __repr__(self):
        return f"<StationFacility(station_id={self.station_id}, has_elevator={self.has_elevator})>"


class Exit(Base):
    """출입구 정보"""
    __tablename__ = "exits"
    __table_args__ = (UniqueConstraint('station_id', 'exit_number', name='_station_exit_uc'),)

    exit_id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.station_id", ondelete="CASCADE"), nullable=False)
    exit_number = Column(String(10), nullable=False)  # "1", "2-1", "2-2" 등 지원
    has_elevator = Column(Boolean, default=False, index=True)
    elevator_type = Column(String(50))  # "외부E/V", "계단형리프트" 등
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    floor_level = Column(String(10))  # "B1", "1F" 등
    description = Column(Text)  # "출구 왼쪽 10m" 등

    # Relationship
    station = relationship("Station", back_populates="exits")
    exit_to_platforms = relationship("ExitToPlatform", back_populates="exit", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Exit(station_id={self.station_id}, exit_number={self.exit_number}, has_elevator={self.has_elevator})>"


class PlatformInfo(Base):
    """승강장 정보"""
    __tablename__ = "platform_info"

    platform_id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.station_id", ondelete="CASCADE"), nullable=False)
    line = Column(String(20))
    direction = Column(String(50))  # "잠실 방면", "시청 방면"
    platform_type = Column(String(20))  # "섬식", "상대식"
    floor_level = Column(String(10))  # "B2", "B3"

    # Relationship
    station = relationship("Station", back_populates="platforms")
    platform_edges = relationship("PlatformEdge", back_populates="platform", cascade="all, delete-orphan")
    exit_to_platforms = relationship("ExitToPlatform", back_populates="platform", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PlatformInfo(station_id={self.station_id}, direction='{self.direction}')>"


class PlatformEdge(Base):
    """승강장 연단 정보 (칸별 상세 정보)"""
    __tablename__ = "platform_edges"

    edge_id = Column(Integer, primary_key=True, index=True)
    platform_id = Column(Integer, ForeignKey("platform_info.platform_id", ondelete="CASCADE"))
    station_id = Column(Integer, ForeignKey("stations.station_id", ondelete="CASCADE"), nullable=False, index=True)
    line = Column(String(20))
    direction = Column(String(50))
    car_position = Column(String(50))  # "본선 오이도 방면 1-3"
    car_number = Column(Integer, index=True)  # 1, 2, 3, ... 10
    door_number = Column(Integer)  # 1, 2, 3, 4
    gap_width = Column(String(20))  # "넓음", "보통", "좁음"
    height_diff = Column(String(20))  # "낮음", "보통", "높음"
    platform_shape = Column(String(20))  # "곡선", "직선"

    # Relationship
    platform = relationship("PlatformInfo", back_populates="platform_edges")

    def __repr__(self):
        return f"<PlatformEdge(station_id={self.station_id}, car_number={self.car_number}, gap='{self.gap_width}')>"


class Route(Base):
    """경로 정보"""
    __tablename__ = "routes"
    __table_args__ = (UniqueConstraint('start_station_id', 'end_station_id', 'line', name='_route_uc'),)

    route_id = Column(Integer, primary_key=True, index=True)
    start_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    end_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    line = Column(String(20))
    direction = Column(String(50))
    estimated_time_minutes = Column(Integer)
    distance_meters = Column(Integer)
    transfer_required = Column(Boolean, default=False)

    # Relationships
    start_station = relationship("Station", foreign_keys=[start_station_id], back_populates="routes_start")
    end_station = relationship("Station", foreign_keys=[end_station_id], back_populates="routes_end")
    optimal_boarding = relationship("OptimalBoarding", back_populates="route", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Route(start_station_id={self.start_station_id}, end_station_id={self.end_station_id})>"


class ExitToPlatform(Base):
    """출구 → 승강장 매핑"""
    __tablename__ = "exit_to_platform"

    mapping_id = Column(Integer, primary_key=True, index=True)
    exit_id = Column(Integer, ForeignKey("exits.exit_id", ondelete="CASCADE"), nullable=False)
    platform_id = Column(Integer, ForeignKey("platform_info.platform_id", ondelete="CASCADE"), nullable=False)
    distance_meters = Column(Integer)
    walking_time_seconds = Column(Integer)
    has_elevator_route = Column(Boolean, default=False)
    direction_description = Column(Text)  # "엘리베이터 내려서 직진"

    # Relationships
    exit = relationship("Exit", back_populates="exit_to_platforms")
    platform = relationship("PlatformInfo", back_populates="exit_to_platforms")

    def __repr__(self):
        return f"<ExitToPlatform(exit_id={self.exit_id}, platform_id={self.platform_id})>"


class OptimalBoarding(Base):
    """최적 탑승 칸 정보"""
    __tablename__ = "optimal_boarding"

    boarding_id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.route_id", ondelete="CASCADE"), nullable=False, unique=True)
    recommended_car_start = Column(Integer)  # 7
    recommended_car_end = Column(Integer)  # 8
    reason = Column(Text)  # "잠실역 4번 출구 엘리베이터와 가장 가까움"

    # Relationship
    route = relationship("Route", back_populates="optimal_boarding")

    def __repr__(self):
        return f"<OptimalBoarding(route_id={self.route_id}, cars={self.recommended_car_start}-{self.recommended_car_end})>"


class TransferInfo(Base):
    """환승 정보"""
    __tablename__ = "transfer_info"

    transfer_id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.station_id", ondelete="CASCADE"), nullable=False)
    from_line = Column(String(20))
    to_line = Column(String(20))
    distance_meters = Column(Integer)
    time_seconds = Column(Integer)

    def __repr__(self):
        return f"<TransferInfo(station_id={self.station_id}, {self.from_line} → {self.to_line})>"


class ChargingStation(Base):
    """휠체어 충전소 정보"""
    __tablename__ = "charging_stations"

    charging_id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.station_id", ondelete="CASCADE"), nullable=False)
    location = Column(String(100))
    floor_level = Column(String(10))  # "B1", "B2" 등
    charger_count = Column(Integer, default=1)
    available = Column(Boolean, default=True)
    charging_time_minutes = Column(Integer)  # 예상 충전 시간

    def __repr__(self):
        return f"<ChargingStation(station_id={self.station_id}, location='{self.location}')>"
