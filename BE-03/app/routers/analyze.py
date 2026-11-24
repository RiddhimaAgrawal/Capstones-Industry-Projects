"""The product endpoints. Protected by API key + rate limit + quota."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import analysis
from ..deps import ApiContext, api_key_guard

router = APIRouter(prefix="/v1/analyze", tags=["Text Analysis API"], dependencies=[Depends(api_key_guard)])


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000, examples=["The movie was absolutely wonderful, I loved it!"])


class KeywordsIn(TextIn):
    top_n: int = Field(5, ge=1, le=25)


@router.post("/sentiment", summary="Positive / negative / neutral sentiment with a score in [-1, 1]")
def sentiment(body: TextIn):
    return analysis.sentiment(body.text)


@router.post("/stats", summary="Word, sentence and reading-time statistics")
def stats(body: TextIn):
    return analysis.stats(body.text)


@router.post("/keywords", summary="Most frequent meaningful words")
def keywords(body: KeywordsIn):
    return {"keywords": analysis.keywords(body.text, body.top_n)}
