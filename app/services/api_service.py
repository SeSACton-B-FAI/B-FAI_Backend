"""
Seoul Open API Service Layer - Completely Refactored
두 가지 API 시스템 완벽 분리: 일반 Open API vs 실시간 지하철 API
"""
import requests
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from loguru import logger

from app.config import settings


# 글로벌 캐시
api_cache: Dict[str, tuple] = {}
CACHE_DURATION = timedelta(minutes=settings.API_CACHE_DURATION_MINUTES)

# 두 가지 다른 인증키
GENERAL_API_KEY = settings.SEOUL_OPEN_API_KEY  # 일반인증키
REALTIME_API_KEY = settings.SEOUL_REALTIME_API_KEY  # 지하철 실시간 인증키


class BaseAPIClient:
    """Base API client with caching"""

    @staticmethod
    def _get_cached_or_fetch(cache_key: str, url: str, timeout: int = 10, cache_duration: timedelta = None) -> Optional[Dict]:
        """캐시 확인 후 API 호출"""
        now = datetime.now()
        cache_ttl = cache_duration or CACHE_DURATION

        # 1. 캐시 확인
        if cache_key in api_cache:
            data, timestamp = api_cache[cache_key]
            if now - timestamp < cache_ttl:
                logger.info(f"✅ Cache hit: {cache_key}")
                return data

        # 2. API 호출
        logger.info(f"🌐 API call: {url}")
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            # 3. 에러 응답 체크
            if 'RESULT' in data:
                result = data['RESULT']
                if result.get('CODE') != 'INFO-000':
                    logger.error(f"⚠️ API Error: {result.get('CODE')} - {result.get('MESSAGE')}")
                    return None

            # 4. 캐시 저장
            api_cache[cache_key] = (data, now)
            return data

        except Exception as e:
            logger.error(f"⚠️ API Error for {cache_key}: {e}")
            return None


class GeneralSeoulAPI(BaseAPIClient):
    """
    일반 Seoul Open API 클라이언트
    Base URL: http://openapi.seoul.go.kr:8088/
    Auth Key: 일반인증키 (GENERAL_API_KEY)
    """

    BASE_URL = "http://openapi.seoul.go.kr:8088"

    @staticmethod
    def _build_url(service_name: str, start_idx: int, end_idx: int, **optional_params) -> str:
        """
        URL 생성 (Seoul Open API 표준 형식)
        Format: BASE_URL/KEY/TYPE/SERVICE/START/END/[optional params as path]
        """
        url = f"{GeneralSeoulAPI.BASE_URL}/{GENERAL_API_KEY}/json/{service_name}/{start_idx}/{end_idx}/"

        # Optional parameters are added as path segments, not query string
        if optional_params:
            param_values = [str(v) for v in optional_params.values() if v is not None]
            if param_values:
                url += "/".join(urllib.parse.quote(str(v)) for v in param_values)

        return url

    @staticmethod
    def _fetch_all_pages(service_name: str, page_size: int = 1000, max_total: int = 10000) -> List[Dict]:
        """
        대용량 데이터 페이징 처리
        - SeoulMetroFaciInfo 같은 API는 2830+ 레코드 반환
        """
        all_items = []
        start_idx = 1

        while start_idx < max_total:
            end_idx = min(start_idx + page_size - 1, max_total)
            url = GeneralSeoulAPI._build_url(service_name, start_idx, end_idx)

            cache_key = f"{service_name}_{start_idx}_{end_idx}"

            # 대용량 데이터는 더 긴 캐시 유지 (1시간)
            cache_duration = timedelta(hours=1) if page_size >= 1000 else CACHE_DURATION
            data = GeneralSeoulAPI._get_cached_or_fetch(cache_key, url, cache_duration=cache_duration)

            if not data or service_name not in data:
                break

            service_data = data[service_name]

            # 응답 구조: {SERVICE_NAME: {list_total_count: N, RESULT: {...}, row: [...]}}
            items = service_data.get('row', [])
            if not items:
                break

            if not isinstance(items, list):
                items = [items]

            all_items.extend(items)

            # 총 개수 확인
            total_count = service_data.get('list_total_count', 0)
            logger.info(f"📊 Fetched {len(all_items)}/{total_count} records from {service_name}")

            if end_idx >= total_count:
                break

            start_idx = end_idx + 1

        return all_items


    # ============================================
    # 1. 교통약자 이용시설(승강기) 가동현황
    #    Service: SeoulMetroFaciInfo
    #    대용량 API (2830+ records)
    # ============================================
    @staticmethod
    def get_elevator_status(station_name: str = None) -> Dict:
        """
        엘리베이터/에스컬레이터 가동 상태 조회
        - 전체 데이터를 가져온 후 필터링 (대용량 API)
        - 정확한 역 이름 매칭으로 잠실/잠실나루/잠실새내 구분
        """
        all_items = GeneralSeoulAPI._fetch_all_pages("SeoulMetroFaciInfo", page_size=1000, max_total=3000)

        # 역 이름 필터링 (정확한 매칭)
        if station_name:
            # "역" 제거하고 기본 역 이름 추출
            station_key = station_name.replace("역", "").strip()

            def is_exact_match(item_station_name: str) -> bool:
                """정확한 역 이름 매칭 (잠실 vs 잠실나루 구분)"""
                item_name = item_station_name.replace("역", "").strip()

                # 호선 정보 제거: "잠실(2)" -> "잠실", "강남(2)" -> "강남"
                import re
                item_name = re.sub(r'\(\d+\)', '', item_name).strip()

                # 정확히 일치하는 경우만
                return item_name == station_key

            all_items = [
                item for item in all_items
                if is_exact_match(item.get('STN_NM', ''))
            ]

        # 엘리베이터만 파싱 (ELVTR_SE == 'EV')
        elevators = []
        all_working = True

        for item in all_items:
            if item.get('ELVTR_SE') == 'EV':  # 엘리베이터만 (에스컬레이터 ES 제외)
                status = item.get('USE_YN', 'N')
                is_working = status == 'Y' or status == '사용가능'

                elevator = {
                    "name": item.get('ELVTR_NM', ''),
                    "location": item.get('INSTL_PSTN', ''),
                    "status": "정상" if is_working else "점검중",
                    "floors": item.get('OPR_SEC', ''),
                    "station_code": item.get('STN_CD', ''),
                    "station_name": item.get('STN_NM', '')
                }
                elevators.append(elevator)

                if not is_working:
                    all_working = False

        return {
            "elevators": elevators,
            "all_working": all_working
        }


    # ============================================
    # 2. 출입구 임시폐쇄 공사현황
    #    Service: TbSubwayLineDetail
    # ============================================
    @staticmethod
    def check_exit_closure(station_name: str = None, exit_number: str = None) -> Dict:
        """출입구 폐쇄 여부 확인"""
        url = GeneralSeoulAPI._build_url("TbSubwayLineDetail", 1, 100)
        data = GeneralSeoulAPI._get_cached_or_fetch("exit_closures", url)

        if not data or 'TbSubwayLineDetail' not in data:
            return {"is_closed": False}

        try:
            closures = data['TbSubwayLineDetail'].get('row', [])
            if not isinstance(closures, list):
                closures = [closures]

            for closure in closures:
                station_match = not station_name or station_name in closure.get('SBWY_STNS_NM', '')
                exit_match = not exit_number or f"{exit_number}번" in closure.get('CLSG_PLC', '')

                if station_match and exit_match:
                    return {
                        "is_closed": True,
                        "line": closure.get('LINE', ''),
                        "station": closure.get('SBWY_STNS_NM', ''),
                        "location": closure.get('CLSG_PLC', ''),
                        "reason": closure.get('CLSG_RSN', ''),
                        "alternative": closure.get('RPLC_PATH', ''),
                        "start_date": closure.get('BGNG_YMD', '')[:10],
                        "end_date": closure.get('END_YMD', '')[:10]
                    }

            return {"is_closed": False}

        except Exception as e:
            logger.error(f"⚠️ Error checking exit closure: {e}")
            return {"is_closed": False}


    # ============================================
    # 3. 교통약자용 엘리베이터 상세정보
    #    Service: getWksnElvtr
    # ============================================
    @staticmethod
    def get_elevator_details(station_name: str = None, exit_number: str = None) -> List[Dict]:
        """교통약자용 엘리베이터 상세정보"""
        # 전체 데이터 가져오기
        all_items = GeneralSeoulAPI._fetch_all_pages("getWksnElvtr", page_size=1000, max_total=2000)

        # 필터링
        if station_name:
            station_key = station_name.replace("역", "")
            all_items = [
                item for item in all_items
                if station_key in item.get('stnNm', '').replace("역", "")
            ]

        if exit_number:
            all_items = [
                item for item in all_items
                if exit_number == item.get('vcntEntrcNo', '')
            ]

        elevators = []
        for item in all_items:
            elevators.append({
                "facility_number": item.get('fcltNo', ''),
                "facility_name": item.get('fcltNm', ''),
                "line_name": item.get('lineNm', ''),
                "station_name": item.get('stnNm', ''),
                "exit_number": item.get('vcntEntrcNo', ''),
                "operation_status": item.get('oprtngSitu', 'M'),
                "location": item.get('dtlPstn', ''),
                "start_floor": item.get('bgngFlr', ''),
                "end_floor": item.get('endFlr', ''),
            })

        return elevators


    # ============================================
    # 4. 안전발판 보유현황
    #    Service: getWksnSafePlfm
    # ============================================
    @staticmethod
    def get_safety_platform(station_name: str = None) -> List[Dict]:
        """안전발판 보유현황"""
        all_items = GeneralSeoulAPI._fetch_all_pages("getWksnSafePlfm", page_size=1000, max_total=1000)

        if station_name:
            station_key = station_name.replace("역", "")
            all_items = [
                item for item in all_items
                if station_key in item.get('stnNm', '').replace("역", "")
            ]

        platforms = []
        for item in all_items:
            platforms.append({
                "facility_name": item.get('fcltNm', ''),
                "has_platform": item.get('sftyScfldEn', '') == 'Y',
                "line_name": item.get('lineNm', ''),
                "station_name": item.get('stnNm', ''),
            })

        return platforms


    # ============================================
    # 5. 휠체어 급속충전기 현황
    #    Service: getWksnWhclCharge
    # ============================================
    @staticmethod
    def get_wheelchair_chargers(station_name: str = None) -> List[Dict]:
        """휠체어 급속충전기 현황"""
        all_items = GeneralSeoulAPI._fetch_all_pages("getWksnWhclCharge", page_size=1000, max_total=1000)

        if station_name:
            station_key = station_name.replace("역", "")
            all_items = [
                item for item in all_items
                if station_key in item.get('stnNm', '').replace("역", "")
            ]

        chargers = []
        for item in all_items:
            chargers.append({
                "facility_name": item.get('fcltNm', ''),
                "line_name": item.get('lineNm', ''),
                "station_name": item.get('stnNm', ''),
                "connector_type": item.get('cnnctrSe', ''),
                "floor": item.get('stnFlr', ''),
                "charger_count": int(item.get('elctcFacCnt', 0)),
                "location": item.get('dtlPstn', ''),
                "usage_fee": item.get('utztnCrg', '무료'),
            })

        return chargers


    # ============================================
    # 6. 휠체어리프트 현황
    #    Service: getWksnWhcllift
    # ============================================
    @staticmethod
    def get_wheelchair_lifts(station_name: str = None) -> List[Dict]:
        """휠체어리프트 현황"""
        all_items = GeneralSeoulAPI._fetch_all_pages("getWksnWhcllift", page_size=1000, max_total=1000)

        if station_name:
            station_key = station_name.replace("역", "")
            all_items = [
                item for item in all_items
                if station_key in item.get('stnNm', '').replace("역", "")
            ]

        lifts = []
        for item in all_items:
            lifts.append({
                "facility_name": item.get('fcltNm', ''),
                "line_name": item.get('lineNm', ''),
                "station_name": item.get('stnNm', ''),
                "exit_number": item.get('vcntEntrcNo', ''),
                "operation_status": item.get('oprtngSitu', 'M'),
            })

        return lifts


    # ============================================
    # 7. 최단경로 이동정보
    #    Service: getShtrmPath
    # ============================================
    @staticmethod
    def get_shortest_path(
        start_station: str,
        end_station: str,
        search_datetime: str = None,
        search_type: str = "duration"
    ) -> Dict:
        """
        최단경로 이동정보
        - search_type: duration(최소시간), distance(최단거리), transfer(최소환승)
        """
        if not search_datetime:
            search_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # URL 구성 (필수 파라미터만 path에 포함)
        url = f"{GeneralSeoulAPI.BASE_URL}/{GENERAL_API_KEY}/json/getShtrmPath/1/50/{urllib.parse.quote(start_station)}/{urllib.parse.quote(end_station)}/{urllib.parse.quote(search_datetime)}"

        cache_key = f"shortest_path_{start_station}_{end_station}_{search_type}"
        data = GeneralSeoulAPI._get_cached_or_fetch(cache_key, url, timeout=15)

        if not data or 'getShtrmPath' not in data:
            return {"total_distance": 0, "total_time": 0, "route": []}

        try:
            result = data['getShtrmPath']
            items = result.get('row', [])
            if not isinstance(items, list):
                items = [items]

            route = []
            total_distance = 0
            total_time = 0

            for item in items:
                distance = int(item.get('stnSctnDstc', 0))
                time_min = int(item.get('reqHr', 0))

                total_distance += distance
                total_time += time_min

                route.append({
                    "station_name": item.get('stnNm', ''),
                    "line_name": item.get('lineNm', ''),
                    "distance": distance,
                    "time": time_min,
                })

            return {
                "total_distance": total_distance,
                "total_time": total_time,
                "route": route
            }

        except Exception as e:
            logger.error(f"⚠️ Error getting shortest path: {e}")
            return {"total_distance": 0, "total_time": 0, "route": []}


class RealtimeSubwayAPI(BaseAPIClient):
    """
    실시간 지하철 API 클라이언트
    Base URL: http://swopenAPI.seoul.go.kr/api/subway/
    Auth Key: 지하철 실시간 인증키 (REALTIME_API_KEY)
    """

    BASE_URL = "http://swopenAPI.seoul.go.kr/api/subway"

    @staticmethod
    def _build_url(service_name: str, start_idx: int, end_idx: int, required_param: str) -> str:
        """
        실시간 API URL 생성
        Format: BASE_URL/KEY/TYPE/SERVICE/START/END/REQUIRED_PARAM
        """
        return f"{RealtimeSubwayAPI.BASE_URL}/{REALTIME_API_KEY}/json/{service_name}/{start_idx}/{end_idx}/{urllib.parse.quote(required_param)}"


    # ============================================
    # 1. 실시간 열차위치정보
    #    Service: realtimePosition
    # ============================================
    @staticmethod
    def get_realtime_train_position(line_name: str) -> List[Dict]:
        """
        실시간 열차위치정보
        Args:
            line_name: 호선명 (예: "2호선", "1호선")
        """
        url = RealtimeSubwayAPI._build_url("realtimePosition", 0, 100, line_name)
        cache_key = f"realtime_position_{line_name}"

        # 실시간 데이터는 짧은 캐시 (1분)
        data = RealtimeSubwayAPI._get_cached_or_fetch(
            cache_key, url, timeout=5, cache_duration=timedelta(minutes=1)
        )

        if not data:
            return []

        try:
            # 응답 구조: {realtimePositionList: [...]} 또는 {errorMessage: {...}}
            items = data.get('realtimePositionList', [])
            if not isinstance(items, list):
                items = [items]

            trains = []
            for item in items:
                trains.append({
                    "subway_id": item.get('subwayId', ''),
                    "subway_name": item.get('subwayNm', ''),
                    "station_name": item.get('statnNm', ''),
                    "train_no": item.get('trainNo', ''),
                    "updown_line": item.get('updnLine', ''),  # 0:상행, 1:하행
                    "terminal_station_name": item.get('statnTnm', ''),
                    "train_status": item.get('trainSttus', ''),  # 0:진입, 1:도착, 2:출발, 3:전역출발
                    "is_express": item.get('directAt', '0') in ['1', '7'],
                    "is_last_train": item.get('lstcarAt', '0') == '1'
                })

            return trains

        except Exception as e:
            logger.error(f"⚠️ Error getting realtime train position: {e}")
            return []


    # ============================================
    # 2. 실시간 역 도착정보
    #    Service: realtimeStationArrival
    # ============================================
    @staticmethod
    def get_realtime_station_arrival(station_name: str) -> List[Dict]:
        """
        실시간 역 도착정보
        Args:
            station_name: 역명 (예: "강남", "잠실") - "역" 제외
        """
        # "역" 제거
        station_key = station_name.replace("역", "")

        url = RealtimeSubwayAPI._build_url("realtimeStationArrival", 0, 10, station_key)
        cache_key = f"realtime_arrival_{station_key}"

        # 실시간 데이터는 짧은 캐시 (1분)
        data = RealtimeSubwayAPI._get_cached_or_fetch(
            cache_key, url, timeout=5, cache_duration=timedelta(minutes=1)
        )

        if not data:
            return []

        try:
            # 응답 구조: {realtimeArrivalList: [...]}
            items = data.get('realtimeArrivalList', [])
            if not isinstance(items, list):
                items = [items]

            arrivals = []
            for item in items:
                # 도착 시간 (초 단위)
                arrival_seconds = int(item.get('barvlDt', '0'))
                arrival_minutes = arrival_seconds // 60

                arrivals.append({
                    "subway_id": item.get('subwayId', ''),
                    "updown_line": item.get('updnLine', ''),  # "상행" or "하행"
                    "train_line_name": item.get('trainLineNm', ''),  # "성수행 - 구로디지털단지방면"
                    "station_name": item.get('statnNm', ''),
                    "train_status": item.get('btrainSttus', '일반'),  # 급행, 일반, 특급
                    "arrival_seconds": arrival_seconds,
                    "arrival_minutes": arrival_minutes,
                    "train_no": item.get('btrainNo', ''),
                    "terminal_station_name": item.get('bstatnNm', ''),
                    "arrival_message": item.get('arvlMsg2', ''),  # "도착", "출발", "진입"
                    "arrival_detail": item.get('arvlMsg3', ''),  # "12분 후 (광명사거리)"
                    "arrival_code": item.get('arvlCd', '99'),  # 0:진입, 1:도착, 2:출발, 99:운행중
                    "is_last_train": item.get('lstcarAt', '0') == '1'
                })

            return arrivals

        except Exception as e:
            logger.error(f"⚠️ Error getting realtime station arrival: {e}")
            return []


# ============================================
# 편의 함수: 역의 모든 정보 한 번에 조회
# ============================================
def get_station_realtime_info(station_name: str) -> Dict:
    """역의 모든 실시간 정보를 한 번에 조회"""
    return {
        "elevator_status": GeneralSeoulAPI.get_elevator_status(station_name),
        "exit_closures": GeneralSeoulAPI.check_exit_closure(station_name),
        "chargers": GeneralSeoulAPI.get_wheelchair_chargers(station_name),
        "train_arrivals": RealtimeSubwayAPI.get_realtime_station_arrival(station_name)
    }


# 하위 호환성을 위한 alias
SeoulMetroAPI = GeneralSeoulAPI
