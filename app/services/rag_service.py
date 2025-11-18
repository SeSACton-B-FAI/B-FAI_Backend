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
                    model_name="gpt-4",
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
        """QA Chain 생성 (노인 친화적 프롬프트)"""
        prompt_template = """
당신은 노인분들을 위한 친절한 지하철 안내 도우미입니다.
아래의 정보를 바탕으로 질문에 답변해주세요.

컨텍스트:
{context}

질문: {question}

답변 규칙:
1. 존댓말을 사용하세요 (예: ~하세요, ~입니다)
2. 2-3문장으로 간결하게 설명하세요
3. 구체적인 방향과 위치를 알려주세요
4. 전문 용어는 쉬운 말로 바꿔주세요

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
        """LLM 없이 간단한 템플릿 기반 안내문 생성"""

        # 기본 안내문
        guide = ""

        if db_data:
            if 'exit_number' in db_data:
                guide += f"{db_data.get('exit_number')}번 출구로 가시면 됩니다. "

            if 'has_elevator' in db_data and db_data['has_elevator']:
                guide += "엘리베이터가 있습니다. "

        if api_data:
            if 'elevators' in api_data and not api_data.get('all_working', True):
                guide += "현재 일부 엘리베이터가 점검 중입니다. "

        if not guide:
            guide = "안내 정보를 준비 중입니다. 잠시만 기다려주세요."

        return guide


    def initialize_subway_knowledge(self):
        """지하철 기본 지식 초기화 (최초 1회 실행)"""
        logger.info("📚 Initializing subway knowledge base...")

        # 기본 지식 추가
        base_knowledge = [
            # 엘리베이터 이용 방법
            "지하철 엘리베이터를 이용하려면 출입구에서 엘리베이터 표시를 따라가세요. 대부분의 엘리베이터는 출입구 왼쪽이나 오른쪽에 위치합니다.",
            "엘리베이터 버튼을 누를 때는 가고자 하는 층을 확인하세요. B1은 지하 1층, B2는 지하 2층입니다.",

            # 승강장 찾기
            "승강장에 도착하면 전광판을 보고 목적지 방면을 확인하세요. 예를 들어 잠실역으로 가려면 '잠실 방면' 승강장으로 가세요.",
            "승강장에서 기다릴 때는 안전선 안쪽에 서세요. 열차가 도착하면 내리는 분들을 먼저 기다린 후 타세요.",

            # 환승 방법
            "환승역에서는 표지판을 따라가면 됩니다. 환승하는 노선의 번호와 색깔을 기억하세요.",
            "환승 통로가 길 수 있으니 여유 있게 이동하세요. 엘리베이터가 있는 환승역도 많습니다.",

            # 출구 찾기
            "목적지 역에 도착하면 출구 번호를 확인하세요. 각 출구는 서로 다른 방향으로 나갑니다.",
            "엘리베이터가 있는 출구로 나가려면 역무원에게 문의하거나 안내도를 확인하세요.",
        ]

        metadatas = [{"source": "기본지식", "category": category}
                    for category in ["엘리베이터", "엘리베이터", "승강장", "승강장",
                                    "환승", "환승", "출구", "출구"]]

        self.add_documents(base_knowledge, metadatas)

        logger.info("✅ Subway knowledge base initialized!")


# Global RAG service instance
rag_service = RAGService()
