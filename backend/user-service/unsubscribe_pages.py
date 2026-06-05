"""Static HTML pages for unsubscribe confirm/complete (no user-controlled visible text)."""

from __future__ import annotations

import html

_INVALID_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><title>구독 취소</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px 24px;">
  <h1>유효하지 않은 링크입니다</h1>
  <p>링크가 만료되었거나 올바르지 않습니다.</p>
</body>
</html>"""

_ALREADY_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><title>구독 취소</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px 24px;">
  <h1>이미 취소된 구독입니다</h1>
  <p>이 이메일은 이미 구독 취소 처리되었습니다.</p>
</body>
</html>"""

_COMPLETE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><title>구독 취소 완료</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px 24px;">
  <h1>구독이 취소되었습니다</h1>
  <p>더 이상 뉴스레터를 받지 않습니다.</p>
</body>
</html>"""


def confirm_unsubscribe_html(token: str) -> str:
    safe_token = html.escape(token, quote=True)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><title>구독 취소 확인</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px 24px;max-width:480px;margin:0 auto;">
  <h1>구독을 취소하시겠습니까?</h1>
  <p>취소하면 뉴스레터 수신이 중단됩니다.</p>
  <form method="post" action="/unsubscribe" style="margin-top:24px;">
    <input type="hidden" name="token" value="{safe_token}" />
    <button type="submit" style="padding:12px 24px;cursor:pointer;">구독 취소하기</button>
  </form>
</body>
</html>"""


def invalid_link_html() -> str:
    return _INVALID_HTML


def already_unsubscribed_html() -> str:
    return _ALREADY_HTML


def unsubscribe_complete_html() -> str:
    return _COMPLETE_HTML
