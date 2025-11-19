"""
RAG (Retrieval-Augmented Generation) Service
LangChain + ChromaDB + OpenAI를 사용한 컨텍스트 기반 안내문 생성
"""
import os
from typing import List, Dict, Optional
from pathlib import Path

from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from loguru import logger

from app.config import settings


class RAGService:
    """RAG 기반 안내 시스템"""

    def __init__(self):
        self.chroma_db_path = settings.CHROMA_DB_PATH
        self.embeddings = None
        self.vectorstore = None
        self.llm = None
        self.qa_chain = None

        # 디렉토리 생성
        Path(self.chroma_db_path).mkdir(parents=True, exist_ok=True)

        self._initialize()


    def _initialize(self):
        """RAG 시스템 초기화"""
        try:
            # 1. Embedding 모델 로드 (한국어 지원)
            logger.info("📦 Loading embedding model...")
            self.embeddings = HuggingFaceEmbeddings(
                model_name=settings.EMBEDDING_MODEL,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )

            # 2. ChromaDB 로드 또는 생성
            logger.info("🗄️ Loading vector database...")
            self.vectorstore = Chroma(
                persist_directory=self.chroma_db_path,
                embedding_function=self.embeddings
            )

            # 3. LLM 초기화 (OpenAI)
            if settings.OPENAI_API_KEY:
                logger.info("🤖 Initializing LLM...")
                self.llm = ChatOpenAI(
                    model_name="gpt-3.5-turbo",
                    temperature=0.3,
                    openai_api_key=settings.OPENAI_API_KEY
                )

                # 4. QA Chain 생성
                self._create_qa_chain()
            else:
                logger.warning("⚠️ OpenAI API key not set. RAG will use simple retrieval only.")

            logger.info("✅ RAG service initialized successfully!")

        except Exception as e:
            logger.error(f"❌ Error initializing RAG: {e}")


    def _create_qa_chain(self):
        """QA Chain 생성 (노인 친화적 배리어프리 안내 프롬프트)"""
        prompt_template = """
당신은 교통약자(노인, 휠체어 사용자)를 위한 친절한 지하철 배리어프리 안내 도우미입니다.
아래의 정보를 바탕으로 질문에 답변해주세요.

컨텍스트:
{context}

질문: {question}

답변 규칙:
1. 존댓말을 사용하세요 (예: ~하세요, ~입니다)
2. 2-3문장으로 간결하고 명확하게 설명하세요
3. 구체적인 위치와 방향을 알려주세요 (예: "출구 왼쪽 10m", "앞쪽으로 직진")
4. 엘리베이터 관련 정보를 우선적으로 안내하세요
5. 경사로, 계단 등 이동에 주의할 점을 알려주세요
6. 숫자(층수, 거리, 시간)는 정확하게 안내하세요
7. 전문 용어는 쉬운 말로 바꿔주세요 (예: "연단간격" → "승강장과 열차 사이 간격")

답변:
"""

        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )

        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vectorstore.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": PROMPT}
        )


    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None):
        """
        벡터 DB에 문서 추가

        Args:
            texts: 추가할 텍스트 리스트
            metadatas: 메타데이터 리스트 (선택)
        """
        try:
            # 텍스트 분할
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50
            )

            documents = [Document(page_content=text, metadata=meta or {})
                        for text, meta in zip(texts, metadatas or [{}] * len(texts))]

            split_docs = text_splitter.split_documents(documents)

            # 벡터 DB에 추가
            self.vectorstore.add_documents(split_docs)
            self.vectorstore.persist()

            logger.info(f"✅ Added {len(split_docs)} document chunks to vector DB")

        except Exception as e:
            logger.error(f"❌ Error adding documents: {e}")


    def search(self, query: str, k: int = 3) -> List[Dict]:
        """
        유사 문서 검색

        Args:
            query: 검색 쿼리
            k: 반환할 문서 개수

        Returns:
            [{"content": "...", "metadata": {...}}, ...]
        """
        try:
            results = self.vectorstore.similarity_search(query, k=k)

            return [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in results
            ]

        except Exception as e:
            logger.error(f"❌ Error searching documents: {e}")
            return []


    def generate_guide(
        self,
        question: str,
        db_data: Optional[Dict] = None,
        api_data: Optional[Dict] = None
    ) -> str:
        """
        DB + API + RAG를 통합하여 안내문 생성

        Args:
            question: 사용자 질문
            db_data: DB 조회 결과
            api_data: Open API 조회 결과

        Returns:
            생성된 안내문
        """
        try:
            # 1. RAG 검색으로 추가 정보 수집
            rag_results = self.search(question, k=2)

            # 2. 컨텍스트 구성
            context_parts = []

            if db_data:
                context_parts.append(f"DB 정보: {db_data}")

            if api_data:
                context_parts.append(f"실시간 정보: {api_data}")

            if rag_results:
                for result in rag_results:
                    context_parts.append(f"참고 자료: {result['content']}")

            # 3. LLM으로 안내문 생성
            if self.qa_chain:
                full_question = f"""
컨텍스트:
{chr(10).join(context_parts)}

질문: {question}
"""
                response = self.qa_chain.run(full_question)
                return response.strip()

            else:
                # LLM 없으면 간단한 템플릿 사용
                return self._generate_simple_guide(question, db_data, api_data)

        except Exception as e:
            logger.error(f"❌ Error generating guide: {e}")
            return self._generate_simple_guide(question, db_data, api_data)


    def _generate_simple_guide(
        self,
        question: str,
        db_data: Optional[Dict] = None,
        api_data: Optional[Dict] = None
    ) -> str:
        """LLM 없이 체크포인트 타입별 템플릿 기반 안내문 생성"""

        guide_parts = []

        # 체크포인트 타입 확인
        checkpoint_type = db_data.get('checkpoint_type', '') if db_data else ''
        station_name = db_data.get('station_name', '') if db_data else ''
        need_elevator = db_data.get('need_elevator', False) if db_data else False

        # 체크포인트 타입별 안내문
        if '출발지' in checkpoint_type:
            exit_number = db_data.get('exit_number', '1') if db_data else '1'
            guide_parts.append(f"{station_name} {exit_number}번 출구로 이동해주세요.")
            if need_elevator:
                guide_parts.append("엘리베이터가 있는 출구입니다.")

        elif '출구' in checkpoint_type:
            exit_number = db_data.get('exit_number', '1') if db_data else '1'
            if '출발' in checkpoint_type:
                guide_parts.append(f"{station_name} {exit_number}번 출구에 도착하셨습니다.")
                if need_elevator:
                    guide_parts.append("엘리베이터를 이용해 승강장으로 이동하세요.")
            else:
                guide_parts.append(f"{station_name} {exit_number}번 출구입니다.")
                if need_elevator:
                    guide_parts.append("엘리베이터를 이용해 지상으로 나가세요.")

        elif '승강장' in checkpoint_type:
            if '대기' in checkpoint_type:
                guide_parts.append(f"{station_name} 승강장에서 열차를 기다려주세요.")
                guide_parts.append("7-8번째 칸 앞에서 대기하시면 좋습니다.")
            elif '도착' in checkpoint_type:
                guide_parts.append(f"{station_name}에 도착하셨습니다!")
                guide_parts.append("출구 방향으로 이동하세요.")
            else:
                guide_parts.append(f"{station_name} 승강장으로 이동하세요.")

        elif '열차' in checkpoint_type or '탑승' in checkpoint_type:
            guide_parts.append("열차에 탑승하셨습니다.")
            guide_parts.append("도착역에서 하차하세요.")

        elif '충전소' in checkpoint_type:
            guide_parts.append(f"{station_name} 주변 휠체어 충전소를 이용하실 수 있습니다.")

        # 엘리베이터 상태 정보 추가
        if api_data:
            elevator_status = api_data.get('elevator_status', {})
            if elevator_status:
                if elevator_status.get('all_working', True):
                    if need_elevator:
                        guide_parts.append("엘리베이터가 정상 운행 중입니다.")
                else:
                    # 작동하는 엘리베이터 찾아서 안내
                    elevators = elevator_status.get('elevators', [])
                    working_elevators = [e for e in elevators if e.get('status') == '정상']

                    if working_elevators:
                        # 작동하는 엘리베이터 위치 안내
                        locations = [e.get('location', '') for e in working_elevators if e.get('location')]
                        if locations:
                            guide_parts.append(f"일부 엘리베이터가 점검 중입니다. {locations[0]}의 엘리베이터를 이용해주세요.")
                        else:
                            guide_parts.append("일부 엘리베이터가 점검 중입니다. 정상 운행 중인 엘리베이터를 이용해주세요.")
                    else:
                        guide_parts.append("엘리베이터가 점검 중입니다. 역무원에게 도움을 요청하세요.")

            # 열차 도착 정보
            train_arrival = api_data.get('train_arrival', [])
            if train_arrival and isinstance(train_arrival, list) and len(train_arrival) > 0:
                first = train_arrival[0]
                if isinstance(first, dict):
                    minutes = first.get('arrival_minutes', 0)
                    if minutes:
                        guide_parts.append(f"다음 열차가 약 {minutes}분 후 도착합니다.")

        # 기본 메시지
        if not guide_parts:
            return "안내를 진행합니다. 표지판을 따라 이동해주세요."

        return " ".join(guide_parts)


    def initialize_subway_knowledge(self):
        """
        지하철 배리어프리 지식 초기화
        - Open API에서 실시간 데이터 수집
        - DB에서 역별 정보 로딩
        - 하드코딩 없이 동적으로 지식 구축
        """
        logger.info("📚 Initializing barrier-free subway knowledge from API/DB...")

        from app.services.api_service import GeneralSeoulAPI
        from app.database import SessionLocal

        documents = []
        metadatas = []

        # 1. Open API에서 엘리베이터 정보 수집
        try:
            elevator_data = GeneralSeoulAPI.get_elevator_status()

            # 역별로 그룹화
            stations_elevators = {}
            for elev in elevator_data.get('elevators', []):
                station = elev.get('station_name', '')
                if station not in stations_elevators:
                    stations_elevators[station] = []
                stations_elevators[station].append(elev)

            # 역별 엘리베이터 정보를 문서로 변환
            for station, elevators in stations_elevators.items():
                if not station:
                    continue

                # 엘리베이터 위치 정보 추출
                locations = [e.get('location', '') for e in elevators if e.get('location')]
                floors = [e.get('floors', '') for e in elevators if e.get('floors')]

                if locations:
                    doc = f"{station}의 엘리베이터는 {', '.join(locations[:3])}에 있습니다."
                    if floors:
                        doc += f" 운행 구간은 {floors[0]}입니다."

                    documents.append(doc)
                    metadatas.append({
                        "source": "OpenAPI",
                        "category": "엘리베이터",
                        "station": station
                    })

            logger.info(f"✅ Loaded {len(documents)} elevator documents from Open API")

        except Exception as e:
            logger.error(f"❌ Failed to load elevator data from API: {e}")

        # 2. Open API에서 휠체어 충전소 정보 수집
        try:
            charger_data = GeneralSeoulAPI.get_wheelchair_chargers()

            for charger in charger_data:
                station = charger.get('station_name', '')
                location = charger.get('location', '')
                floor = charger.get('floor', '')

                if station and location:
                    doc = f"{station}에 휠체어 충전소가 있습니다. 위치는 {location}"
                    if floor:
                        doc += f" ({floor})"
                    doc += "입니다."

                    documents.append(doc)
                    metadatas.append({
                        "source": "OpenAPI",
                        "category": "충전소",
                        "station": station
                    })

            logger.info(f"✅ Loaded charger documents from Open API")

        except Exception as e:
            logger.error(f"❌ Failed to load charger data from API: {e}")

        # 3. Open API에서 휠체어 리프트 정보 수집
        try:
            lift_data = GeneralSeoulAPI.get_wheelchair_lifts()

            for lift in lift_data:
                station = lift.get('station_name', '')
                location = lift.get('location', '')

                if station and location:
                    doc = f"{station}에 휠체어 리프트가 있습니다. 위치는 {location}입니다."
                    documents.append(doc)
                    metadatas.append({
                        "source": "OpenAPI",
                        "category": "리프트",
                        "station": station
                    })

            logger.info(f"✅ Loaded lift documents from Open API")

        except Exception as e:
            logger.error(f"❌ Failed to load lift data from API: {e}")

        # 4. DB에서 역별 출구/편의시설 정보 로딩
        try:
            db = SessionLocal()
            from app.models import Station, Exit, StationFacility

            stations = db.query(Station).all()

            for station in stations:
                # 엘리베이터 있는 출구 정보
                exits_with_elev = db.query(Exit).filter(
                    Exit.station_id == station.station_id,
                    Exit.has_elevator == True
                ).all()

                if exits_with_elev:
                    exit_numbers = [e.exit_number for e in exits_with_elev]
                    doc = f"{station.name}에서 엘리베이터가 있는 출구는 {', '.join(exit_numbers)}번 출구입니다."

                    # 상세 위치 정보 추가
                    for exit_obj in exits_with_elev[:2]:
                        if hasattr(exit_obj, 'elevator_location') and exit_obj.elevator_location:
                            doc += f" {exit_obj.exit_number}번 출구 엘리베이터는 {exit_obj.elevator_location}에 있습니다."

                    documents.append(doc)
                    metadatas.append({
                        "source": "DB",
                        "category": "출구",
                        "station": station.name
                    })

                # 편의시설 정보
                facility = db.query(StationFacility).filter(
                    StationFacility.station_id == station.station_id
                ).first()

                if facility:
                    facilities = []
                    if facility.has_nursing_room:
                        facilities.append("수유실")
                    if facility.has_wheelchair_charger:
                        facilities.append("휠체어 충전소")
                    if facility.has_meeting_place:
                        facilities.append("만남의 장소")

                    if facilities:
                        doc = f"{station.name}에는 {', '.join(facilities)}이 있습니다."
                        documents.append(doc)
                        metadatas.append({
                            "source": "DB",
                            "category": "편의시설",
                            "station": station.name
                        })

            db.close()
            logger.info(f"✅ Loaded station documents from DB")

        except Exception as e:
            logger.error(f"❌ Failed to load data from DB: {e}")

        # 5. 문서 추가
        if documents:
            self.add_documents(documents, metadatas)
            logger.info(f"✅ Total {len(documents)} documents added to RAG knowledge base")
        else:
            logger.warning("⚠️ No documents loaded - RAG knowledge base is empty")

    def refresh_knowledge(self, station_name: str = None):
        """
        특정 역 또는 전체 지식 새로고침
        - 실시간 API 데이터로 업데이트
        """
        from app.services.api_service import GeneralSeoulAPI

        documents = []
        metadatas = []

        # 엘리베이터 실시간 상태 업데이트
        elevator_data = GeneralSeoulAPI.get_elevator_status(station_name)

        for elev in elevator_data.get('elevators', []):
            station = elev.get('station_name', '')
            location = elev.get('location', '')
            status = elev.get('status', '')
            floors = elev.get('floors', '')

            if station and location:
                doc = f"{station} {location} 엘리베이터는 현재 {status} 상태입니다."
                if floors:
                    doc += f" 운행 구간: {floors}"

                documents.append(doc)
                metadatas.append({
                    "source": "OpenAPI_Realtime",
                    "category": "엘리베이터상태",
                    "station": station
                })

        if documents:
            self.add_documents(documents, metadatas)
            logger.info(f"✅ Refreshed {len(documents)} elevator status documents")


# Global RAG service instance
rag_service = RAGService()
