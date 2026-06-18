from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path, encoding="utf-8-sig")
load_dotenv(encoding="utf-8-sig")

_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
_LINK_LINE_PREFIX = "🔗 원문 보기:"


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


_DEFAULT_DELAY_SECONDS = _env_float("SUMMARY_DELAY_SECONDS", 1.25)
_DEFAULT_MAX_RETRIES = _env_int("SUMMARY_MAX_RETRIES", 1)

log = logging.getLogger("news-summarizer")


def _require_api_key() -> str:
    raw = os.getenv("GEMINI_API_KEY")
    if not raw:
        log.critical(
            "required_environment_missing",
            extra={"event": "required_environment_missing", "env_var": "GEMINI_API_KEY"},
        )
        raise RuntimeError(
            "GEMINI_API_KEY가 설정되어 있지 않습니다. "
            "news-summarizer-service/.env 파일에 GEMINI_API_KEY=... 형태로 추가하세요."
        )
    api_key = raw.strip().strip("\ufeff").strip().strip('"').strip("'")
    if not api_key:
        log.critical(
            "required_environment_empty",
            extra={"event": "required_environment_empty", "env_var": "GEMINI_API_KEY"},
        )
        raise RuntimeError("GEMINI_API_KEY가 비어 있습니다.")
    return api_key


def _extract_response_text(resp: Any) -> str:
    """generate_content 응답에서 텍스트를 안정적으로 추출한다."""
    text = (getattr(resp, "text", None) or "").strip()
    if text:
        return text

    candidates = getattr(resp, "candidates", None) or []
    if not candidates:
        prompt_fb = getattr(resp, "prompt_feedback", None)
        block = getattr(prompt_fb, "block_reason", None) if prompt_fb else None
        raise RuntimeError(
            "Gemini 응답에 텍스트가 없습니다."
            + (f" (차단 사유: {block})" if block else "")
        )

    parts = getattr(getattr(candidates[0], "content", None), "parts", None) or []
    chunks = []
    for p in parts:
        t = getattr(p, "text", None)
        if t:
            chunks.append(t)
    out = "".join(chunks).strip()
    if not out:
        finish = getattr(candidates[0], "finish_reason", None)
        raise RuntimeError(
            "Gemini 응답에서 본문을 읽을 수 없습니다."
            + (f" (finish_reason: {finish})" if finish else "")
        )
    return out


def _is_retryable_rate_limit(exc: BaseException) -> bool:
    try:
        from google.api_core import exceptions as gexc

        if isinstance(exc, gexc.ResourceExhausted):
            return True
    except Exception:
        pass

    name = type(exc).__name__
    if name in ("ResourceExhausted", "TooManyRequests"):
        return True

    s = str(exc).lower()
    return (
        "429" in s
        or "resource exhausted" in s
        or "quota" in s
        or "rate limit" in s
        or "too many requests" in s
    )


def _is_timeout_or_5xx(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return (
        "timeout" in name
        or "deadline" in name
        or "timeout" in message
        or "deadline exceeded" in message
        or "500" in message
        or "502" in message
        or "503" in message
        or "504" in message
    )


def _normalize_news_item(news: Dict[str, Any]) -> Dict[str, str]:
    title = str(news.get("title", "")).strip()
    link = str(news.get("link", "")).strip()
    category = str(news.get("category", "")).strip()
    rss_description = str(news.get("rss_description", "")).strip()
    if not title or not link:
        raise ValueError("news 입력에는 최소한 'title'과 'link'가 필요합니다.")
    return {
        "title": title,
        "link": link,
        "category": category,
        "rss_description": rss_description,
    }


def _build_batch_prompt(items: List[Dict[str, str]]) -> str:
    indexed_items = [
        {
            "index": i,
            "category": item["category"],
            "title": item["title"],
            "rss_description": item["rss_description"],
            "link": item["link"],
        }
        for i, item in enumerate(items)
    ]
    items_json = json.dumps(indexed_items, ensure_ascii=False, indent=2)
    return f"""
You are a Korean newsletter editor.

Summarize each news item using ONLY its title and rss_description.
Return valid JSON only. No markdown code block.

Output schema:
{{
  "summaries": [
    {{
      "index": 0,
      "summary": "[오늘의 한 줄]: ...\\n\\n[주요 내용]:\\n- ...\\n- ..."
    }}
  ]
}}

Rules:
- Write Korean only.
- Keep each summary under 450 Korean characters.
- Do not invent facts.
- Do not add details not present in title or rss_description.
- Use exactly two bullets under [주요 내용].
- Do not include URLs in the summary.
- Preserve every input index exactly once.
- Return summaries in the same order as input.

Input items:
{items_json}
""".strip()


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _append_link_line(summary: str, link: str) -> str:
    body = summary.strip()
    body = re.sub(r"\n*🔗\s*원문 보기:.*$", "", body, flags=re.DOTALL).strip()
    body = re.sub(r"\n*:link:\s*원문 보기:.*$", "", body, flags=re.DOTALL).strip()
    return f"{body}\n\n{_LINK_LINE_PREFIX} {link}"


def _parse_batch_response(raw_text: str, items: List[Dict[str, str]]) -> List[str]:
    payload_text = _strip_json_fence(raw_text)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini batch JSON 파싱 실패: {exc}") from exc

    summaries_raw = payload.get("summaries")
    if not isinstance(summaries_raw, list):
        raise RuntimeError("Gemini batch 응답에 'summaries' 배열이 없습니다.")
    if len(summaries_raw) != len(items):
        raise RuntimeError(
            f"요약 개수 불일치: 요청 {len(items)}건, 응답 {len(summaries_raw)}건"
        )

    by_index: Dict[int, str] = {}
    for entry in summaries_raw:
        if not isinstance(entry, dict):
            raise RuntimeError("Gemini batch summaries 항목이 객체가 아닙니다.")
        if "index" not in entry:
            raise RuntimeError("Gemini batch 응답에 index가 누락되었습니다.")
        try:
            index = int(entry["index"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Gemini batch index가 정수가 아닙니다.") from exc
        if index in by_index:
            raise RuntimeError(f"Gemini batch index가 중복되었습니다: {index}")
        summary = entry.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise RuntimeError(f"Gemini batch summary가 비어 있거나 문자열이 아닙니다: index={index}")
        by_index[index] = summary.strip()

    expected = set(range(len(items)))
    if set(by_index.keys()) != expected:
        missing = sorted(expected - set(by_index.keys()))
        raise RuntimeError(f"Gemini batch index 누락: {missing}")

    return [_append_link_line(by_index[i], items[i]["link"]) for i in range(len(items))]


def _batch_max_output_tokens(item_count: int) -> int:
    return min(4096, max(1024, 600 * item_count))


def _build_generation_config(item_count: int) -> Any:
    import google.generativeai as genai

    kwargs: Dict[str, Any] = {
        "temperature": 0.35,
        "max_output_tokens": _batch_max_output_tokens(item_count),
    }
    try:
        return genai.GenerationConfig(response_mime_type="application/json", **kwargs)
    except TypeError:
        return genai.GenerationConfig(**kwargs)


def _summarize_batch_with_client(
    client: Any,
    news_list: List[Dict[str, Any]],
    *,
    timeout_seconds: Optional[int],
) -> List[str]:
    _ = timeout_seconds
    if not news_list:
        return []

    items = [_normalize_news_item(news) for news in news_list]
    prompt = _build_batch_prompt(items)
    generation_config = _build_generation_config(len(items))

    try:
        resp = client.generate_content(prompt, generation_config=generation_config)
    except BaseException as exc:
        if _is_timeout_or_5xx(exc):
            log.error(
                "gemini_api_failure",
                extra={
                    "event": "gemini_api_failure",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "batch_size": len(items),
                },
            )
        raise

    raw_text = _extract_response_text(resp)
    if not raw_text:
        raise RuntimeError("Gemini가 비어있는 batch 요약을 반환했습니다.")
    return _parse_batch_response(raw_text, items)


def _summarize_batch_with_retries(
    client: Any,
    news_list: List[Dict[str, Any]],
    *,
    max_retries: int,
    timeout_seconds: Optional[int],
) -> List[str]:
    if max_retries < 1:
        raise ValueError("max_retries는 1 이상이어야 합니다.")

    last_error: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            return _summarize_batch_with_client(
                client,
                news_list,
                timeout_seconds=timeout_seconds,
            )
        except BaseException as exc:
            last_error = exc
            if _is_retryable_rate_limit(exc):
                log.warning(
                    "gemini_batch_rate_limited_no_retry",
                    extra={
                        "event": "gemini_batch_rate_limited_no_retry",
                        "batch_size": len(news_list),
                        "error_type": type(exc).__name__,
                    },
                )
                raise
            if not _is_timeout_or_5xx(exc) or attempt == max_retries - 1:
                raise
            backoff = (2**attempt) + random.uniform(0.0, 0.35)
            log.warning(
                "gemini_batch_retry_backoff",
                extra={
                    "event": "gemini_batch_retry_backoff",
                    "retrying_count": attempt + 1,
                    "max_retries": max_retries,
                    "batch_size": len(news_list),
                    "sleep_seconds": round(backoff, 4),
                    "error_type": type(exc).__name__,
                },
            )
            time.sleep(backoff)

    if last_error is not None:
        raise last_error
    raise RuntimeError("요약 생성에 실패했습니다.")


def summarize_news(
    news: Dict[str, Any],
    *,
    model: str = _DEFAULT_MODEL,
    timeout_seconds: Optional[int] = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> str:
    """
    뉴스 dict(title/link/category 등)를 입력받아 Gemini로 한국어 요약 텍스트를 생성한다.

    출력 포맷(한국어):
    [오늘의 한 줄]: ...
    [주요 내용]:
    - ...
    - ...
    🔗 원문 보기: [URL]
    """
    summaries = summarize_news_list(
        [news],
        model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    return summaries[0]


def iter_summarize_news(
    news_list: List[Dict[str, Any]],
    *,
    model: str = _DEFAULT_MODEL,
    delay_seconds: float = _DEFAULT_DELAY_SECONDS,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    timeout_seconds: Optional[int] = None,
):
    """
    뉴스 리스트를 batch 1회로 요약하며 (원본 dict, 요약 문자열)을 순서대로 보낸다.
    delay_seconds는 API 호환성을 위해 받지만 batch 내부에서는 사용하지 않는다.
    """
    import google.generativeai as genai

    _ = delay_seconds
    if delay_seconds < 0:
        raise ValueError("delay_seconds는 0 이상이어야 합니다.")
    if not news_list:
        return

    api_key = _require_api_key()
    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model)
    summaries = _summarize_batch_with_retries(
        client,
        news_list,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
    )
    for news, summary in zip(news_list, summaries):
        yield news, summary


def summarize_news_list(
    news_list: List[Dict[str, Any]],
    *,
    model: str = _DEFAULT_MODEL,
    delay_seconds: float = _DEFAULT_DELAY_SECONDS,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    timeout_seconds: Optional[int] = None,
) -> List[str]:
    """
    뉴스 dict 리스트를 batch 1회 Gemini 호출로 요약한 문자열 리스트를 반환한다.
    delay_seconds는 API 호환성을 위해 받지만 batch 내부에서는 사용하지 않는다.
    """
    return [
        text
        for _, text in iter_summarize_news(
            news_list,
            model=model,
            delay_seconds=delay_seconds,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
    ]


if __name__ == "__main__":
    from json_logging import setup_service_logging

    setup_service_logging("news-summarizer")
    samples: List[Dict[str, str]] = [
        {
            "category": "IT/테크",
            "title": "Tech Giants Report Quarterly Earnings Amid AI Spending Boom",
            "link": "https://example.com/news/sample-tech-earnings",
        },
    ]

    log.info(
        "summarizer_cli_start",
        extra={"event": "summarizer_cli_start", "sample_count": len(samples)},
    )
    summaries = summarize_news_list(samples)
    for i, summary in enumerate(summaries, start=1):
        log.info(
            "summarizer_cli_result",
            extra={"event": "summarizer_cli_result", "index": i, "summary_preview": summary[:400]},
        )
