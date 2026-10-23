"""환경 변수를 한곳에서 읽는 설정 모듈.

키·주소 같은 값은 코드에 직접 쓰지 않고 전부 환경 변수(.env 또는 Render 설정)에서 읽는다.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # 비용 보호: 답변 1회당 최대 토큰 수
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "600"))

    # 저장소: firestore(기본) 또는 memory(키 없이 로컬 테스트용)
    STORAGE: str = os.getenv("STORAGE", "firestore").lower()
    # 서비스 계정 키 JSON 문자열 전체 (Render 환경 변수로 넣는 방식)
    FIREBASE_SERVICE_ACCOUNT_JSON: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    # 또는 키 파일 경로 (로컬 개발용)
    FIREBASE_SERVICE_ACCOUNT_PATH: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")

    # CORS 허용 도메인 (쉼표 구분). 예: https://my-app.vercel.app,http://localhost:5500
    ALLOWED_ORIGINS: list[str] = _split_csv(
        os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
    )

    DATASET_NAME: str = os.getenv("DATASET_NAME", "비트코인(BTC/USDT) 일별 종가")
    DATASET_UNIT: str = os.getenv("DATASET_UNIT", "USD")


settings = Settings()
