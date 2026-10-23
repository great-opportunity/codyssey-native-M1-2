from fastapi import APIRouter, Query, Response

from ..schemas import DataCreate, DataItem, DataUpdate, Summary
from ..services import data_service
from ..services.summary import build_statistics, build_summary

router = APIRouter(prefix="/api/data", tags=["data"])


# /summary, /statistics 는 /{id} 보다 먼저 선언해야 'summary'가 id로 오인되지 않는다
@router.get("/summary", response_model=Summary, summary="데이터 요약 (프롬프트 주입용)")
def get_summary():
    return build_summary(data_service.list_data())


@router.get("/statistics", summary="[보너스] 상세 통계: 7일 이동평균·월별 평균·최대 상승/하락일")
def get_statistics():
    return build_statistics(data_service.list_data())


@router.get("", response_model=list[DataItem], summary="데이터 목록 조회 (날짜 오름차순)")
def list_data(
    start: str | None = Query(None, description="시작일 YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, description="종료일 YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    return data_service.list_data(start, end)


@router.post("", response_model=DataItem, status_code=201, summary="새 데이터 추가")
def create_data(body: DataCreate):
    return data_service.create_data(body)


@router.put("/{doc_id}", response_model=DataItem, summary="데이터 수정 (보낸 필드만 변경)")
def update_data(doc_id: str, body: DataUpdate):
    return data_service.update_data(doc_id, body)


@router.delete("/{doc_id}", status_code=204, summary="데이터 삭제")
def delete_data(doc_id: str):
    data_service.delete_data(doc_id)
    return Response(status_code=204)
