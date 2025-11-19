"""
Route Cache Service
경로 검색 결과를 캐시하여 네비게이션 API에서 route_id로 조회 가능하게 함
"""
from typing import Dict, Optional
from datetime import datetime, timedelta
import threading
import random

class RouteCache:
    """인메모리 경로 캐시 (Redis로 업그레이드 가능)"""

    def __init__(self):
        self._cache: Dict[int, Dict] = {}
        self._lock = threading.Lock()
        self._ttl_hours = 24  # 24시간 후 만료

    def generate_route_id(self) -> int:
        """유니크한 route_id 생성"""
        # 타임스탬프 기반 + 랜덤으로 유니크 ID 생성
        timestamp = int(datetime.now().timestamp() * 1000) % 1000000000
        random_suffix = random.randint(100, 999)
        return timestamp + random_suffix

    def save_route(
        self,
        route_id: int,
        start_station: str,
        end_station: str,
        line: str,
        direction: str,
        checkpoints: list,
        need_elevator: bool = False
    ) -> None:
        """경로 정보 저장"""
        with self._lock:
            self._cache[route_id] = {
                "start_station": start_station,
                "end_station": end_station,
                "line": line,
                "direction": direction,
                "checkpoints": checkpoints,
                "need_elevator": need_elevator,
                "created_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(hours=self._ttl_hours)
            }

    def get_route(self, route_id: int) -> Optional[Dict]:
        """route_id로 경로 정보 조회"""
        with self._lock:
            route = self._cache.get(route_id)

            if not route:
                return None

            # 만료 체크
            if datetime.now() > route["expires_at"]:
                del self._cache[route_id]
                return None

            return route

    def get_checkpoint_data(self, route_id: int, checkpoint_id: int) -> Optional[Dict]:
        """특정 체크포인트 데이터 조회"""
        route = self.get_route(route_id)

        if not route:
            return None

        for cp in route.get("checkpoints", []):
            if cp.get("id") == checkpoint_id:
                return cp.get("data", {})

        return None

    def cleanup_expired(self) -> int:
        """만료된 캐시 정리"""
        with self._lock:
            now = datetime.now()
            expired = [
                route_id for route_id, route in self._cache.items()
                if now > route["expires_at"]
            ]

            for route_id in expired:
                del self._cache[route_id]

            return len(expired)

    def get_stats(self) -> Dict:
        """캐시 통계"""
        with self._lock:
            return {
                "total_routes": len(self._cache),
                "oldest": min(
                    (r["created_at"] for r in self._cache.values()),
                    default=None
                ),
                "newest": max(
                    (r["created_at"] for r in self._cache.values()),
                    default=None
                )
            }


# 글로벌 인스턴스
route_cache = RouteCache()
