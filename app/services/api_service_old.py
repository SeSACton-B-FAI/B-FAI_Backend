"""
Seoul Open API Service Layer with Caching
"""
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger

from app.config import settings


# 글로벌 캐시
api_cache: Dict[str, tuple] = {}
CACHE_DURATION = timedelta(minutes=settings.API_CACHE_DURATION_MINUTES)
API_KEY = settings.SEOUL_OPEN_API_KEY
REALTIME_API_KEY = settings.SEOUL_REALTIME_API_KEY


class SeoulMetroAPI:
    """서울교통공사 Open API 클라이언트"""

    BASE_URL = "http://openapi.seoul.go.kr:8088"
    REALTIME_BASE_URL = "http://swopenAPI.seoul.go.kr/api/subway"

    @staticmethod
    def _make_url(service_name: str, start_idx: int = 1, end_idx: int = 1000) -> str:
        """일반 API URL 생성"""
        return f"{SeoulMetroAPI.BASE_URL}/{API_KEY}/json/{service_name}/{start_idx}/{end_idx}/"

    @staticmethod
    def _make_realtime_url(service_name: str, start_idx: int = 0, end_idx: int = 5, param: str = "") -> str:
        """실시간 API URL 생성"""
        if param:
            return f"{SeoulMetroAPI.REALTIME_BASE_URL}/{REALTIME_API_KEY}/json/{service_name}/{start_idx}/{end_idx}/{param}"
        return f"{SeoulMetroAPI.REALTIME_BASE_URL}/{REALTIME_API_KEY}/json/{service_name}/{start_idx}/{end_idx}/"

    @staticmethod
    def _get_cached_or_fetch(cache_key: str, url: str, timeout: int = 10) -> Optional[Dict]:
        """캐시 확인 후 API 호출"""
        now = datetime.now()

        # 1. 캐시 확인
        if cache_key in api_cache:
            data, timestamp = api_cache[cache_key]
            if now - timestamp < CACHE_DURATION:
                logger.info(f"✅ Cache hit: {cache_key}")
                return data

        # 2. API 호출
        logger.info(f"🌐 API call: {cache_key}")
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            # 3. 캐시 저장
            api_cache[cache_key] = (data, now)
            return data

        except Exception as e:
            logger.error(f"⚠️ API Error for {cache_key}: {e}")
            return None


    @staticmethod
    def get_elevator_status(station_name: str) -> Dict:
        """
        엘리베이터 상태 조회 (SeoulMetroFaciInfo)

        Returns:
            {
                "elevators": [
                    {"name": "외부#1", "location": "1번 출입구", "status": "사용가능", "floors": "B1-1F"},
                    ...
                ],
                "all_working": True/False
            }
        """
        cache_key = f"elevator_{station_name}"
        url = SeoulMetroAPI._make_url("SeoulMetroFaciInfo", 1, 3000)

        data = SeoulMetroAPI._get_cached_or_fetch(cache_key, url)

        if not data:
            return {"elevators": [], "all_working": True}

        try:
            all_data = data['SeoulMetroFaciInfo']['row']

            # 해당 역만 필터링
            filtered = [
                d for d in all_data
                if station_name in d.get('STN_NM', '') or station_name in d.get('STN_NM', '').replace('(', '').replace(')', '')
            ]

            # 엘리베이터만 파싱
            elevators = []
            all_working = True

            for item in filtered:
                if item['ELVTR_SE'] == 'EV':  # 엘리베이터만
                    elevator = {
                        "name": item['ELVTR_NM'],
                        "location": item['INSTL_PSTN'],
                        "status": item['USE_YN'],
                        "floors": item['OPR_SEC']
                    }
                    elevators.append(elevator)

                    if item['USE_YN'] != '사용가능':
                        all_working = False

            return {
                "elevators": elevators,
                "all_working": all_working
            }

        except Exception as e:
            logger.error(f"⚠️ Error parsing elevator data: {e}")
            return {"elevators": [], "all_working": True}


    @staticmethod
    def check_exit_closure(station_name: str, exit_number: Optional[int] = None) -> Dict:
        """
        출입구 폐쇄 여부 확인 (TbSubwayLineDetail)

        Returns:
            {
                "is_closed": True/False,
                "reason": "폐쇄 사유",
                "alternative": "대체 출입구",
                "end_date": "2027-09-16"
            }
        """
        url = SeoulMetroAPI._make_url("TbSubwayLineDetail", 1, 100)

        data = SeoulMetroAPI._get_cached_or_fetch("exit_closures", url)

        if not data:
            return {"is_closed": False}

        try:
            closures = data['TbSubwayLineDetail']['row']

            for closure in closures:
                station_match = station_name in closure['SBWY_STNS_NM']

                if exit_number:
                    exit_match = f"{exit_number}번" in closure['CLSG_PLC']
                else:
                    exit_match = True

                if station_match and exit_match:
                    return {
                        "is_closed": True,
                        "reason": closure['CLSG_RSN'],
                        "alternative": closure['RPLC_PATH'],
                        "end_date": closure['END_YMD'][:10]
                    }

            return {"is_closed": False}

        except Exception as e:
            logger.error(f"⚠️ Error checking exit closure: {e}")
            return {"is_closed": False}


    @staticmethod
    def get_wheelchair_chargers(station_name: str) -> List[Dict]:
        """
        휠체어 충전소 정보 조회 (getWksnWhclCharge)

        Returns:
            [
                {
                    "station": "종각",
                    "floor": "B1",
                    "count": 1,
                    "location": "3, 4번 출구쪽 게이트 방면 45m 지점"
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_url("getWksnWhclCharge", 1, 100)

        data = SeoulMetroAPI._get_cached_or_fetch("wheelchair_chargers", url)

        if not data:
            return []

        try:
            items = data['response']['body']['items']['item']

            if not isinstance(items, list):
                items = [items]

            chargers = []
            for item in items:
                if station_name in item['stnNm']:
                    chargers.append({
                        "station": item['stnNm'],
                        "floor": item['stnFlr'],
                        "count": int(item['elctcFacCnt']),
                        "location": item['dtlPstn']
                    })

            return chargers

        except Exception as e:
            logger.error(f"⚠️ Error getting charger info: {e}")
            return []


    @staticmethod
    def get_elevator_details(station_name: str) -> List[Dict]:
        """
        교통약자용 엘리베이터 상세 정보 (getWksnElvtr)

        Returns:
            [
                {
                    "name": "엘리베이터-동묘앞 상행 10-3 내부#2",
                    "location": "신설동 방면10-3",
                    "start_floor": "B2",
                    "end_floor": "B1",
                    "status": "M" (사용가능)
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_url("getWksnElvtr", 1, 3000)

        data = SeoulMetroAPI._get_cached_or_fetch(f"elevator_details_{station_name}", url)

        if not data:
            return []

        try:
            items = data['response']['body']['items']['item']

            if not isinstance(items, list):
                items = [items]

            elevators = []
            for item in items:
                if station_name in item['stnNm']:
                    elevators.append({
                        "name": item['fcltNm'],
                        "location": item['dtlPstn'],
                        "start_floor": item['bgngFlr'],
                        "end_floor": item['endFlr'],
                        "status": item['oprtngSitu']  # M=사용가능, S=보수중, D=삭제
                    })

            return elevators

        except Exception as e:
            logger.error(f"⚠️ Error getting elevator details: {e}")
            return []


    @staticmethod
    def get_shortest_path(start_station: str, end_station: str, search_datetime: Optional[str] = None) -> Dict:
        """
        최단경로 이동정보 (getShtrmPath)

        Args:
            start_station: 출발역명 (예: "강남")
            end_station: 도착역명 (예: "잠실")
            search_datetime: 검색일시 (YYYY-MM-DD HH:MM:SS 형식, 기본값: 현재시각)

        Returns:
            {
                "total_distance": 6700,  # 총 거리(m)
                "total_time": 690,  # 총 소요시간(초)
                "total_fare": 1550,  # 교통카드 요금
                "transit_count": 0,  # 환승 횟수
                "route": [...]
            }
        """
        if not search_datetime:
            search_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # URL 인코딩 필요
        import urllib.parse
        encoded_datetime = urllib.parse.quote(search_datetime)
        
        url = f"{SeoulMetroAPI.BASE_URL}/{API_KEY}/json/getShtrmPath/1/50/{start_station}/{end_station}/{encoded_datetime}"

        cache_key = f"shortest_path_{start_station}_{end_station}"
        data = SeoulMetroAPI._get_cached_or_fetch(cache_key, url)

        if not data or 'body' not in data or not data['body']:
            return {
                "total_distance": 0,
                "total_time": 0,
                "total_fare": 0,
                "transit_count": 0,
                "route": []
            }

        try:
            body = data['body']
            paths = body.get('paths', [])

            route = []
            for item in paths:
                dptre_stn = item.get('dptreStn', {})
                arvl_stn = item.get('arvlStn', {})
                
                route.append({
                    "depart_station": dptre_stn.get('stnNm', ''),
                    "depart_line": dptre_stn.get('lineNm', ''),
                    "arrive_station": arvl_stn.get('stnNm', ''),
                    "arrive_line": arvl_stn.get('lineNm', ''),
                    "distance": int(item.get('stnSctnDstc', 0)),
                    "time": int(item.get('reqHr', 0)),
                    "train_no": item.get('trainno', ''),
                    "train_depart": item.get('trainDptreTm', ''),
                    "train_arrive": item.get('trainArvlTm', ''),
                    "is_transfer": item.get('trsitYn', 'N') == 'Y',
                    "is_express": item.get('etrnYn', 'N') == 'Y'
                })

            return {
                "total_distance": int(body.get('totalDstc', 0)),
                "total_time": int(body.get('totalreqHr', 0)),  # 초 단위
                "total_fare": int(body.get('totalCardCrg', 0)),
                "transit_count": int(body.get('trsitNmtm', 0)),
                "route": route
            }

        except Exception as e:
            logger.error(f"⚠️ Error getting shortest path: {e}")
            return {
                "total_distance": 0,
                "total_time": 0,
                "total_fare": 0,
                "transit_count": 0,
                "route": []
            }


    @staticmethod
    def get_safety_platform(station_name: str) -> List[Dict]:
        """
        안전발판 보유현황 (getWksnSafePlfm)

        플랫폼과 열차 사이 틈새를 메우는 안전발판 정보 조회

        Returns:
            [
                {
                    "facility_name": "안전발판",
                    "platform_count": 2,  # 안전발판 개수
                    "station_number": "123",
                    "created_date": "2024-01-15",
                    "manager_phone": "02-1234-5678"
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_url("getWksnSafePlfm", 1, 1000)

        data = SeoulMetroAPI._get_cached_or_fetch(f"safety_platform_{station_name}", url)

        if not data:
            return []

        try:
            items = data['response']['body']['items']['item']

            if not isinstance(items, list):
                items = [items]

            platforms = []
            for item in items:
                if station_name in item['stnNm']:
                    platforms.append({
                        "facility_name": item['fcltNm'],
                        "platform_count": int(item.get('sftyScfldEn', 0)),
                        "station_number": item['stnNo'],
                        "created_date": item.get('crtrYmd', '')[:10] if item.get('crtrYmd') else '',
                        "manager_phone": item.get('mngrTelno', '')
                    })

            return platforms

        except Exception as e:
            logger.error(f"⚠️ Error getting safety platform info: {e}")
            return []


    @staticmethod
    def get_wheelchair_lift(station_name: str) -> List[Dict]:
        """
        휠체어리프트 정보 (getWksnWhcllift)

        수직 이동을 위한 휠체어 리프트 시설 정보 조회

        Returns:
            [
                {
                    "facility_number": "L001",
                    "facility_name": "휠체어리프트-1번출구",
                    "station_number": "123",
                    "lift_sequence": 1,
                    "management_number": "M001",
                    "start_floor": "B1",
                    "end_floor": "1F",
                    "length": 1500,  # mm
                    "width": 800,  # mm
                    "weight_limit": 300,  # kg
                    "status": "M"  # M=사용가능, S=보수중
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_url("getWksnWhcllift", 1, 1000)

        data = SeoulMetroAPI._get_cached_or_fetch(f"wheelchair_lift_{station_name}", url)

        if not data:
            return []

        try:
            items = data['response']['body']['items']['item']

            if not isinstance(items, list):
                items = [items]

            lifts = []
            for item in items:
                if station_name in item['stnNm']:
                    lifts.append({
                        "facility_number": item.get('fcltNo', ''),
                        "facility_name": item['fcltNm'],
                        "station_number": item['stnNo'],
                        "lift_sequence": int(item.get('elvtrSn', 0)),
                        "management_number": item.get('mngNo', ''),
                        "start_floor": item['bgngFlr'],
                        "end_floor": item['endFlr'],
                        "length": int(item.get('elvtrLen', 0)),
                        "width": int(item.get('elvtrWdthBt', 0)),
                        "weight_limit": int(item.get('limitWht', 0)),
                        "status": item.get('oprtngSitu', 'M')  # M=사용가능, S=보수중
                    })

            return lifts

        except Exception as e:
            logger.error(f"⚠️ Error getting wheelchair lift info: {e}")
            return []


    @staticmethod
    def get_realtime_train_position(line_name: str) -> List[Dict]:
        """
        실시간 열차위치정보 (realtimePosition)

        Args:
            line_name: 호선명 (예: "2호선")

        Returns:
            [
                {
                    "subway_id": "1002",
                    "subway_name": "2호선",
                    "station_id": "1002000233",
                    "station_name": "강남",
                    "train_no": "2234",
                    "last_reception_date": "2025-11-18",
                    "reception_time": "14:30:25",
                    "updown_line": "0",  # 0:상행/내선, 1:하행/외선
                    "terminal_station_id": "1002000201",
                    "terminal_station_name": "시청",
                    "train_status": "1",  # 0:진입, 1:도착, 2:출발, 3:전역출발
                    "direct_at": "0",  # 1:급행, 0:일반, 7:특급
                    "last_car_at": "0"  # 1:막차, 0:아님
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_realtime_url("realtimePosition", 0, 100, line_name)
        cache_key = f"realtime_position_{line_name}"
        
        data = SeoulMetroAPI._get_cached_or_fetch(cache_key, url, timeout=5)

        if not data:
            return []

        try:
            items = data.get('realtimePositionList', [])

            trains = []
            for item in items:
                trains.append({
                    "subway_id": item.get('subwayId', ''),
                    "subway_name": item.get('subwayNm', ''),
                    "station_id": item.get('statnId', ''),
                    "station_name": item.get('statnNm', ''),
                    "train_no": item.get('trainNo', ''),
                    "last_reception_date": item.get('lastRecptnDt', ''),
                    "reception_time": item.get('recptnDt', ''),
                    "updown_line": item.get('updnLine', ''),
                    "terminal_station_id": item.get('statnTid', ''),
                    "terminal_station_name": item.get('statnTnm', ''),
                    "train_status": item.get('trainSttus', ''),
                    "direct_at": item.get('directAt', '0'),
                    "last_car_at": item.get('lstcarAt', '0')
                })

            return trains

        except Exception as e:
            logger.error(f"⚠️ Error getting realtime train position: {e}")
            return []


    @staticmethod
    def get_realtime_station_arrival(station_name: str) -> List[Dict]:
        """
        실시간 역 도착정보 (realtimeStationArrival)

        Args:
            station_name: 역명 (예: "강남")

        Returns:
            [
                {
                    "subway_id": "1002",
                    "updown_line": "상행",
                    "train_line_name": "잠실행 - 구로디지털단지방면",
                    "previous_station_id": "1002000234",
                    "next_station_id": "1002000232",
                    "station_id": "1002000233",
                    "station_name": "강남",
                    "transfer_count": "2",
                    "order_key": "11234",
                    "subway_list": "1002,1007",
                    "station_list": "1002000233,1007000000",
                    "train_status": "일반",
                    "arrival_time": "120",  # 초 단위
                    "train_no": "2234",
                    "terminal_station_id": "1002000201",
                    "terminal_station_name": "시청",
                    "reception_time": "2025-11-18 14:30:25",
                    "arrival_message_2": "도착",
                    "arrival_message_3": "강남 도착",
                    "arrival_code": "1",  # 0:진입, 1:도착, 2:출발, 3:전역출발, 4:전역진입, 5:전역도착, 99:운행중
                    "last_car_at": "0"
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_realtime_url("realtimeStationArrival", 0, 10, station_name)
        cache_key = f"realtime_arrival_{station_name}"
        
        # 실시간 데이터는 캐시 시간을 짧게 (30초)
        data = SeoulMetroAPI._get_cached_or_fetch(cache_key, url, timeout=5)

        if not data:
            return []

        try:
            items = data.get('realtimeArrivalList', [])

            arrivals = []
            for item in items:
                arrivals.append({
                    "subway_id": item.get('subwayId', ''),
                    "updown_line": item.get('updnLine', ''),
                    "train_line_name": item.get('trainLineNm', ''),
                    "previous_station_id": item.get('statnFid', ''),
                    "next_station_id": item.get('statnTid', ''),
                    "station_id": item.get('statnId', ''),
                    "station_name": item.get('statnNm', ''),
                    "transfer_count": item.get('trnsitCo', '0'),
                    "order_key": item.get('ordkey', ''),
                    "subway_list": item.get('subwayList', ''),
                    "station_list": item.get('statnList', ''),
                    "train_status": item.get('btrainSttus', '일반'),
                    "arrival_time": item.get('barvlDt', '0'),
                    "train_no": item.get('btrainNo', ''),
                    "terminal_station_id": item.get('bstatnId', ''),
                    "terminal_station_name": item.get('bstatnNm', ''),
                    "reception_time": item.get('recptnDt', ''),
                    "arrival_message_2": item.get('arvlMsg2', ''),
                    "arrival_message_3": item.get('arvlMsg3', ''),
                    "arrival_code": item.get('arvlCd', '99'),
                    "last_car_at": item.get('lstcarAt', '0')
                })

            return arrivals

        except Exception as e:
            logger.error(f"⚠️ Error getting realtime station arrival: {e}")
            return []


    @staticmethod
    def get_wheelchair_lift(station_name: str) -> List[Dict]:
        """
        휠체어리프트 정보 (getWksnWhcllift)

        Returns:
            [
                {
                    "facility_number": "L001",
                    "facility_name": "휠체어리프트-1번출구",
                    "station_number": "123",
                    "lift_sequence": 1,
                    "management_number": "M001",
                    "start_floor": "B1",
                    "end_floor": "1F",
                    "length": 1500,  # mm
                    "width": 800,  # mm
                    "weight_limit": 300,  # kg
                    "status": "M"  # M=사용가능, S=보수중
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_url("getWksnWhcllift", 1, 1000)

        data = SeoulMetroAPI._get_cached_or_fetch(f"wheelchair_lift_{station_name}", url)

        if not data:
            return []

        try:
            response_body = data.get('getWksnWhcllift', {})
            items = response_body.get('row', [])

            if not isinstance(items, list):
                items = [items]

            lifts = []
            for item in items:
                if station_name in item.get('stnNm', ''):
                    lifts.append({
                        "facility_number": item.get('fcltNo', ''),
                        "facility_name": item.get('fcltNm', ''),
                        "station_number": item.get('stnNo', ''),
                        "lift_sequence": int(item.get('elvtrSn', 0)),
                        "management_number": item.get('mngNo', ''),
                        "start_floor": item.get('bgngFlr', ''),
                        "end_floor": item.get('endFlr', ''),
                        "length": int(item.get('elvtrLen', 0)),
                        "width": int(item.get('elvtrWdthBt', 0)),
                        "weight_limit": int(item.get('limitWht', 0)),
                        "status": item.get('oprtngSitu', 'M')
                    })

            return lifts

        except Exception as e:
            logger.error(f"⚠️ Error getting wheelchair lift info: {e}")
            return []


    @staticmethod
    def get_facility_elevator(station_name: str = None) -> List[Dict]:
        """
        편의시설위치정보 엘리베이터 현황 (getFcElvtr)

        Returns:
            [
                {
                    "line_name": "2호선",
                    "station_code": "233",
                    "station_name": "강남",
                    "nearby_exit_number": "3",
                    "operation_status": "M",  # M:사용가능, D:삭제, S:보수중, T:중지, I:점검중, B:공사중
                    "facility_number": "F001",
                    "facility_name": "엘리베이터-3번출구",
                    "station_number": "233",
                    "created_date": "2024-01-15",
                    "elevator_sequence": 1,
                    "management_number": "M001",
                    "detail_position": "3번 출구 왼쪽 10m",
                    "start_floor_type": "지상",
                    "start_floor": "1F",
                    "end_floor_type": "지하",
                    "end_floor": "B1",
                    "capacity_people": 15,
                    "capacity_weight": 1000
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_url("getFcElvtr", 1, 3000)

        cache_key = f"facility_elevator_{station_name}" if station_name else "facility_elevator_all"
        data = SeoulMetroAPI._get_cached_or_fetch(cache_key, url)

        if not data:
            return []

        try:
            response_body = data.get('getFcElvtr', {})
            items = response_body.get('row', [])

            if not isinstance(items, list):
                items = [items]

            elevators = []
            for item in items:
                # 역 이름 필터링
                if station_name and station_name not in item.get('stnNm', ''):
                    continue

                elevators.append({
                    "line_name": item.get('lineNm', ''),
                    "station_code": item.get('stnCd', ''),
                    "station_name": item.get('stnNm', ''),
                    "nearby_exit_number": item.get('vcntEntrcNo', ''),
                    "operation_status": item.get('oprtngSitu', 'M'),
                    "facility_number": item.get('fcltNo', ''),
                    "facility_name": item.get('fcltNm', ''),
                    "station_number": item.get('stnNo', ''),
                    "created_date": item.get('crtrYmd', '')[:10] if item.get('crtrYmd') else '',
                    "elevator_sequence": int(item.get('elvtrSn', 0)),
                    "management_number": item.get('mngNo', ''),
                    "detail_position": item.get('dtlPstn', ''),
                    "start_floor_type": item.get('bgngFlrGrndUdgdSe', ''),
                    "start_floor": item.get('bgngFlr', ''),
                    "end_floor_type": item.get('endFlrGrndUdgdSe', ''),
                    "end_floor": item.get('endFlr', ''),
                    "capacity_people": int(item.get('pscpNope', 0)),
                    "capacity_weight": int(item.get('pscpWht', 0))
                })

            return elevators

        except Exception as e:
            logger.error(f"⚠️ Error getting facility elevator info: {e}")
            return []


    @staticmethod
    def get_subway_elevator_location(station_name: str = None) -> List[Dict]:
        """
        지하철역 주변 엘리베이터 위치 공간정보 (tbTraficElvtr)

        Returns:
            [
                {
                    "node_type": "엘리베이터",
                    "node_wkt": "POINT(127.027619 37.497952)",
                    "node_id": "N001",
                    "node_type_code": "EV",
                    "district_code": "11",
                    "district_name": "강남구",
                    "town_code": "11680",
                    "town_name": "역삼동",
                    "subway_station_code": "233",
                    "subway_station_name": "강남"
                },
                ...
            ]
        """
        url = SeoulMetroAPI._make_url("tbTraficElvtr", 1, 3000)

        cache_key = f"subway_elevator_location_{station_name}" if station_name else "subway_elevator_location_all"
        data = SeoulMetroAPI._get_cached_or_fetch(cache_key, url)

        if not data:
            return []

        try:
            response_body = data.get('tbTraficElvtr', {})
            items = response_body.get('row', [])

            if not isinstance(items, list):
                items = [items]

            locations = []
            for item in items:
                # 역 이름 필터링
                if station_name and station_name not in item.get('SBWY_STN_NM', ''):
                    continue

                locations.append({
                    "node_type": item.get('NODE_TYPE', ''),
                    "node_wkt": item.get('NODE_WKT', ''),
                    "node_id": item.get('NODE_ID', ''),
                    "node_type_code": item.get('NODE_TYPE_CD', ''),
                    "district_code": item.get('SGG_CD', ''),
                    "district_name": item.get('SGG_NM', ''),
                    "town_code": item.get('EMD_CD', ''),
                    "town_name": item.get('EMD_NM', ''),
                    "subway_station_code": item.get('SBWY_STN_CD', ''),
                    "subway_station_name": item.get('SBWY_STN_NM', '')
                })

            return locations

        except Exception as e:
            logger.error(f"⚠️ Error getting subway elevator location: {e}")
            return []


# 편의 함수
def get_station_realtime_info(station_name: str) -> Dict:
    """
    역의 모든 실시간 정보를 한 번에 조회

    Returns:
        {
            "elevators": [...],
            "all_elevators_working": True/False,
            "exit_closures": {...},
            "chargers": [...],
            "elevator_details": [...],
            "safety_platforms": [...],
            "wheelchair_lifts": [...],
            "facility_elevators": [...],
            "subway_elevator_locations": [...],
            "realtime_arrivals": [...]
        }
    """
    return {
        "elevators": SeoulMetroAPI.get_elevator_status(station_name),
        "exit_closures": SeoulMetroAPI.check_exit_closure(station_name),
        "chargers": SeoulMetroAPI.get_wheelchair_chargers(station_name),
        "elevator_details": SeoulMetroAPI.get_elevator_details(station_name),
        "safety_platforms": SeoulMetroAPI.get_safety_platform(station_name),
        "wheelchair_lifts": SeoulMetroAPI.get_wheelchair_lift(station_name),
        "facility_elevators": SeoulMetroAPI.get_facility_elevator(station_name),
        "subway_elevator_locations": SeoulMetroAPI.get_subway_elevator_location(station_name),
        "realtime_arrivals": SeoulMetroAPI.get_realtime_station_arrival(station_name)
    }
