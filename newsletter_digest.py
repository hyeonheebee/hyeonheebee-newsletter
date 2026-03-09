#!/usr/bin/env python3
"""
Newsletter Digest - 네이버 메일 뉴스레터 자동 수집 & 정리
실행: python3 ~/newsletter-digest/newsletter_digest.py
옵션: --days 14  (기본 10일, 실행 시 직접 입력 가능)
"""

import imaplib
import email
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
import os
import re
import sys
import argparse
import getpass
import subprocess
from pathlib import Path

# ──────────────────────────────────────────────
#  의존 패키지 자동 설치
# ──────────────────────────────────────────────
def ensure_packages():
    for pkg, imp in [("beautifulsoup4", "bs4"), ("html2text", "html2text")]:
        try:
            __import__(imp)
        except ImportError:
            print(f"📦 {pkg} 설치 중...")
            os.system(f"pip3 install {pkg} -q")

ensure_packages()

from bs4 import BeautifulSoup
import html2text as _html2text

# ──────────────────────────────────────────────
#  설정
# ──────────────────────────────────────────────
IMAP_SERVER = "imap.naver.com"
IMAP_PORT   = 993

NEWSLETTERS = {
    "GeekNews Weekly":    ["news@hada.io"],
    "오렌지레터 산리":     ["orangeletter@myorange.io"],
    "모두레터":           ["modulabs01-gmail.com@send.stibee.com"],
    "밑미 meet me":       ["hello@nicetomeetme.kr"],
    "NEWNEEK":            ["whatsup@newneek.co"],
    "어피티 잘쓸레터":     ["moneyletter@uppity.co.kr"],
    "소마코":             ["smk@goldenax.co.kr"],
    "응답하라 마케팅":     ["marsinmarine@maily.so"],
    "데일리뉴스럴":       ["neusral.news@neusral.com", "wire@neusral.com"],
    "요즘IT":             ["yozm_help@wishket.com"],
    "큐레터":             ["hey@qletter.co.kr"],
    "고구마팜":           ["flyer@gogumafarm.kr"],
    "헤이팝":             ["heypop@design.co.kr"],
    "폴인 fol:in":        ["folin@sf.folin.co"],
    "Latent.Space":       ["swyx@substack.com"],
    "AINews":             ["swyx+ainews@substack.com"],
    "지피터스":           ["support@gpters.org"],
    "미라클레터":         ["miraklelab@mk.co.kr"],
    "BOODING":            ["everybody@booding.co"],
    "Trend A Word":       ["contact@trendaword.com"],
    "서울시청":           ["inews11@seoul.go.kr"],
    "STARTUP WEEKLY":    ["sungmin@glance.media"],
}

OBSIDIAN_VAULT = Path("/Users/shimhyeonhee/Documents/Obsidian Vault")
OUTPUT_DIR     = Path.home() / "newsletter-digest" / "output"

# ──────────────────────────────────────────────
#  유틸리티
# ──────────────────────────────────────────────
def decode_str(s):
    if not s:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s or ""


# "웹에서 보기" 류 링크 키워드
_WEB_LINK_KEYWORDS = [
    "웹에서 보기", "웹에서보기", "온라인으로 보기", "브라우저에서 보기",
    "view in browser", "view online", "read online", "open in browser",
    "view this email", "웹 버전", "web version",
]

def find_web_link(html: str) -> str:
    """뉴스레터 HTML에서 '웹에서 보기' 링크를 찾아 반환"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if any(kw.lower() in text for kw in _WEB_LINK_KEYWORDS):
            return a["href"]
    return ""


def extract_content(msg):
    """
    이메일에서 HTML 원본과 텍스트(fallback) 모두 추출.
    반환: (html_raw, text_fallback)
    """
    h2t = _html2text.HTML2Text()
    h2t.ignore_links  = False
    h2t.ignore_images = True
    h2t.body_width    = 0

    html_payload  = ""
    plain_payload = ""

    parts = list(msg.walk()) if msg.is_multipart() else [msg]
    for part in parts:
        ct      = part.get_content_type()
        charset = part.get_content_charset() or "utf-8"
        try:
            raw = part.get_payload(decode=True)
            if raw is None:
                continue
            decoded = raw.decode(charset, errors="replace")
            if ct == "text/html" and not html_payload:
                html_payload = decoded
            elif ct == "text/plain" and not plain_payload:
                plain_payload = decoded
        except Exception:
            continue

    if html_payload:
        # script / style 제거 (보안)
        soup = BeautifulSoup(html_payload, "html.parser")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        clean_html = str(soup)
        text_fallback = h2t.handle(clean_html).strip()
        return clean_html, text_fallback

    return "", plain_payload.strip()


# ──────────────────────────────────────────────
#  IMAP 수집
# ──────────────────────────────────────────────
def fetch_newsletters(naver_email, password, days=7):
    print(f"\n🔗 imap.naver.com 연결 중...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(naver_email, password)
    except imaplib.IMAP4.error as e:
        print(f"❌ 로그인 실패: {e}")
        print("💡 네이버 메일 → 환경설정 → POP3/IMAP 설정에서 IMAP이 활성화되어 있는지 확인하세요.")
        sys.exit(1)

    # 모든 폴더 목록 가져오기 (네이버는 전체메일 폴더 없음)
    _, folder_list = mail.list()
    skip_folders = {"Sent Messages", "Drafts", "Deleted Messages", "Junk"}
    folders_to_search = []
    for folder_info in folder_list:
        raw = folder_info.decode("utf-8", errors="replace")
        # 폴더명 추출: 마지막 토큰
        parts = raw.rsplit('" ', 1)
        fname = parts[-1].strip().strip('"') if len(parts) >= 2 else "INBOX"
        if fname not in skip_folders:
            folders_to_search.append(fname)

    since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    print(f"📅 검색 기간: 최근 {days}일 (since {since_date})")
    print(f"📁 스캔 폴더 {len(folders_to_search)}개: {folders_to_search}")

    sender_map = {}
    for name, addrs in NEWSLETTERS.items():
        for addr in addrs:
            sender_map[addr.lower()] = name

    results = {}
    matched = 0
    seen_ids = set()  # 중복 방지

    for folder in folders_to_search:
        try:
            status, _ = mail.select(f'"{folder}"')
            if status != "OK":
                continue
        except Exception:
            continue

        _, msg_ids = mail.search(None, f"SINCE {since_date}")
        ids = msg_ids[0].split() if msg_ids[0] else []
        if ids:
            print(f"  {folder}: {len(ids)}개")

        for msg_id in ids:
            uid_key = f"{folder}:{msg_id.decode()}"
            if uid_key in seen_ids:
                continue
            seen_ids.add(uid_key)

            try:
                _, data = mail.fetch(msg_id, "(RFC822)")
                raw = data[0][1]
                msg = email.message_from_bytes(raw)

                from_raw = decode_str(msg.get("From", "")).lower()
                nl_name  = None
                for addr, name in sender_map.items():
                    if addr in from_raw:
                        nl_name = name
                        break
                if not nl_name:
                    continue

                subject  = decode_str(msg.get("Subject", "(제목 없음)"))
                date_str = msg.get("Date", "")
                try:
                    date = parsedate_to_datetime(date_str).replace(tzinfo=None)
                except Exception:
                    date = datetime.now()

                html_raw, text_fallback = extract_content(msg)
                web_link = find_web_link(html_raw)

                results.setdefault(nl_name, []).append({
                    "subject":  subject,
                    "date":     date,
                    "html":     html_raw,
                    "text":     text_fallback,
                    "web_link": web_link,
                    "from":     from_raw,
                })
                matched += 1

            except Exception:
                continue

    mail.logout()

    for name in results:
        results[name].sort(key=lambda x: x["date"], reverse=True)

    print(f"✅ {len(results)}개 뉴스레터 / {matched}개 메일 수집 완료\n")
    return results


# ──────────────────────────────────────────────
#  HTML 생성
# ──────────────────────────────────────────────
def generate_html(results, days):
    today = datetime.now().strftime("%Y-%m-%d")
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    found   = sorted(results.keys())
    missing = [n for n in NEWSLETTERS if n not in results]
    total   = sum(len(v) for v in results.values())

    def slug(name):
        return re.sub(r"[^a-zA-Z0-9가-힣]", "-", name)

    # ── 사이드바 ──
    sidebar_items = ""
    for name in found:
        cnt = len(results[name])
        sidebar_items += (
            f'<a href="#{slug(name)}">'
            f'{name}'
            f'<span class="badge">{cnt}</span>'
            f'</a>\n'
        )
    if missing:
        sidebar_items += (
            f'<div class="no-mail">수신 없음 ({len(missing)}개)<br>'
            + "<br>".join(missing)
            + "</div>"
        )

    # ── 카드에 북마크 버튼 추가 (data 속성으로 메타정보 포함) ──
    sections = ""
    for name in found:
        items_html = ""
        for i, item in enumerate(results[name]):
            card_id  = f"{slug(name)}-{i}"
            date_fmt = item["date"].strftime("%m/%d %H:%M")
            date_iso = item["date"].strftime("%Y-%m-%d")
            web_link = item.get("web_link", "")

            # 원문 링크 버튼
            web_btn = ""
            if web_link:
                web_btn = (
                    f'<a class="web-link-btn" href="{web_link}" '
                    f'target="_blank" onclick="event.stopPropagation()">🔗 원문 보기</a>'
                )

            # 북마크 버튼
            subj_escaped = item['subject'].replace('"', '&quot;').replace("'", "&#39;")
            link_escaped = web_link.replace('"', '&quot;')
            bm_btn = (
                f'<button class="bm-btn" id="bm-{card_id}" '
                f'onclick="toggleBookmark(event, \'{card_id}\', \'{name}\', \'{date_iso}\', \'{subj_escaped}\', \'{link_escaped}\')" '
                f'title="저장함에 저장">☆</button>'
            )

            # 본문
            if item["html"]:
                # 모든 링크가 새 탭에서 열리도록 <base target="_blank"> 삽입
                html_for_iframe = item["html"]
                base_tag = '<base target="_blank">'
                if "<head>" in html_for_iframe.lower():
                    html_for_iframe = html_for_iframe.replace("<head>", f"<head>{base_tag}", 1)
                    html_for_iframe = html_for_iframe.replace("<HEAD>", f"<HEAD>{base_tag}", 1)
                else:
                    html_for_iframe = base_tag + html_for_iframe
                srcdoc = html_for_iframe.replace('"', "&quot;")
                body_content = (
                    f'<iframe class="nl-iframe" srcdoc="{srcdoc}" '
                    f'sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" '
                    f'onload="resizeIframe(this)"></iframe>'
                )
            else:
                text_escaped = (
                    item["text"]
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                body_content = f'<pre class="content-text">{text_escaped}</pre>'

            items_html += f"""
        <div class="card" id="card-{card_id}" data-nl="{name}" data-date="{date_iso}" data-subject="{subj_escaped}" data-link="{link_escaped}">
          <div class="card-header" onclick="toggle('{card_id}')">
            <span class="card-subject">{item['subject']}</span>
            <span class="card-meta">
              {web_btn}
              <span class="card-date">{date_fmt}</span>
              {bm_btn}
              <span class="toggle-btn" id="btn-{card_id}">펼치기 ▼</span>
            </span>
          </div>
          <div class="card-body" id="body-{card_id}">
            {body_content}
          </div>
        </div>"""

        sections += f"""
      <section id="{slug(name)}">
        <h2 class="section-title">{name}</h2>
        {items_html}
      </section>"""

    if missing:
        sections += f"""
      <section>
        <h2 class="section-title muted">이번 주 수신 없음</h2>
        <div class="missing-list">{', '.join(missing)}</div>
      </section>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>뉴스레터 다이제스트 {today}</title>
<style>
  :root {{
    --sidebar-w: 230px;
    --accent:   #5b5ef4;
    --bg:       #f4f5f7;
    --card-bg:  #ffffff;
    --text:     #1c1c2e;
    --muted:    #6b7280;
    --border:   #e5e7eb;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text); font-size: 14px;
  }}
  .sidebar {{
    position: fixed; left: 0; top: 0;
    width: var(--sidebar-w); height: 100vh;
    background: #fff; border-right: 1px solid var(--border);
    overflow-y: auto; padding: 0;
    display: flex; flex-direction: column;
  }}
  .sidebar-tabs {{
    display: flex; border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }}
  .sidebar-tab {{
    flex: 1; padding: 10px 4px; font-size: 11px; font-weight: 700;
    text-align: center; cursor: pointer; color: var(--muted);
    border-bottom: 2px solid transparent; transition: all .15s;
    user-select: none;
  }}
  .sidebar-tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .sidebar-panel {{ flex: 1; overflow-y: auto; padding: 10px 0; }}
  .sidebar-panel.hidden {{ display: none; }}
  .sidebar a {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 14px; font-size: 13px; color: var(--text);
    text-decoration: none; border-radius: 6px; margin: 0 6px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: background .15s;
  }}
  .sidebar a:hover {{ background: var(--bg); color: var(--accent); }}
  .badge {{
    flex-shrink: 0; background: var(--accent); color: #fff;
    border-radius: 10px; padding: 1px 7px;
    font-size: 10px; font-weight: 700; margin-left: 6px;
  }}
  .no-mail {{
    padding: 10px 16px; font-size: 11px; color: #aaa;
    line-height: 1.8; border-top: 1px solid var(--border); margin-top: 8px;
  }}
  /* 저장함 패널 — 뉴스레터 섹션 스타일 */
  .saved-empty {{
    padding: 28px 16px; text-align: center;
    font-size: 12px; color: #aaa; line-height: 2;
  }}
  .saved-group {{ margin-bottom: 0; }}
  .saved-group-header {{
    display: flex; align-items: center; gap: 6px;
    padding: 10px 14px 8px;
    font-size: 12px; font-weight: 800; color: #fff;
    background: var(--accent);
    letter-spacing: .02em;
  }}
  .saved-group + .saved-group {{ margin-top: 10px; }}
  .saved-item {{
    margin: 0; padding: 12px 14px;
    background: var(--card-bg);
    border-bottom: 1px solid var(--border);
    font-size: 12px; position: relative;
  }}
  .saved-item:last-child {{ border-bottom: none; }}
  .saved-item-actions {{
    position: absolute; top: 8px; right: 8px;
    display: flex; gap: 2px;
  }}
  .saved-item-del, .saved-item-copy {{
    background: none; border: none; cursor: pointer;
    font-size: 12px; padding: 2px 4px; border-radius: 4px;
    color: #d1d5db; transition: all .1s;
  }}
  .saved-item-del:hover {{ color: #f87171; background: #fff1f1; }}
  .saved-item-copy:hover {{ color: var(--accent); background: #eef2ff; }}
  .saved-item-quote {{
    font-size: 12px; color: #1c1c2e; line-height: 1.7;
    border-left: 3px solid var(--accent); padding-left: 8px;
    margin: 0 0 6px; white-space: pre-wrap; word-break: break-word;
  }}
  .saved-item-subject {{
    font-size: 10px; color: var(--muted); line-height: 1.4;
    margin-bottom: 4px;
  }}
  .saved-item-link {{
    font-size: 10px; color: var(--accent); text-decoration: none;
  }}
  .saved-item-link:hover {{ text-decoration: underline; }}
  .saved-actions {{
    padding: 8px 10px; display: flex; gap: 6px; flex-shrink: 0;
    border-top: 1px solid var(--border);
  }}
  .saved-copy-btn {{
    flex: 1; padding: 8px; font-size: 12px; font-weight: 700;
    background: var(--accent); color: #fff; border: none;
    border-radius: 7px; cursor: pointer; transition: opacity .15s;
  }}
  .saved-copy-btn:hover {{ opacity: .85; }}
  .saved-clear-btn {{
    padding: 8px 10px; font-size: 11px; color: var(--muted);
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 7px; cursor: pointer;
  }}
  .saved-badge {{
    flex-shrink: 0; background: #f87171; color: #fff;
    border-radius: 10px; padding: 1px 6px;
    font-size: 10px; font-weight: 700; margin-left: 4px;
    display: none;
  }}
  /* 북마크 버튼 */
  .bm-btn {{
    background: none; border: none; cursor: pointer;
    font-size: 15px; padding: 0 2px; line-height: 1;
    transition: transform .15s; color: #d1d5db;
    flex-shrink: 0;
  }}
  .bm-btn:hover {{ transform: scale(1.2); color: #f59e0b; }}
  .bm-btn.saved {{ color: #f59e0b; }}
  /* 토스트 */
  #toast {{
    display: none; position: fixed; bottom: 28px; right: 28px;
    background: #1c1c2e; color: #fff;
    padding: 10px 18px; border-radius: 8px;
    font-size: 13px; font-weight: 600;
    box-shadow: 0 4px 16px rgba(0,0,0,.2);
    z-index: 10000; animation: fadeup .25s ease;
  }}
  @keyframes fadeup {{
    from {{ opacity:0; transform:translateY(8px); }}
    to   {{ opacity:1; transform:translateY(0); }}
  }}
  /* 메인 */
  .main {{
    margin-left: var(--sidebar-w); padding: 36px 40px;
    max-width: calc(var(--sidebar-w) + 820px);
  }}
  .page-header {{ margin-bottom: 36px; }}
  .page-header h1 {{ font-size: 22px; font-weight: 800; margin-bottom: 4px; }}
  .page-header .meta {{ color: var(--muted); font-size: 13px; }}
  section {{ margin-bottom: 48px; }}
  .section-title {{
    font-size: 16px; font-weight: 800; color: var(--accent);
    border-left: 4px solid var(--accent); padding-left: 10px; margin-bottom: 14px;
  }}
  .section-title.muted {{ color: #aaa; border-color: #ddd; }}
  .card {{
    background: var(--card-bg); border: 1px solid var(--border);
    border-radius: 10px; margin-bottom: 10px;
    overflow: hidden; transition: box-shadow .15s;
  }}
  .card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,.06); }}
  .card-header {{
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 12px; padding: 14px 18px; cursor: pointer;
  }}
  .card-header:hover {{ background: #fafafa; }}
  .card-subject {{ font-size: 14px; font-weight: 600; flex: 1; line-height: 1.5; }}
  .card-meta {{
    display: flex; align-items: center; gap: 8px;
    flex-shrink: 0; padding-top: 2px;
  }}
  .card-date {{ font-size: 11px; color: var(--muted); }}
  .toggle-btn {{
    font-size: 11px; color: var(--accent);
    cursor: pointer; white-space: nowrap; font-weight: 600;
  }}
  .web-link-btn {{
    font-size: 11px; color: var(--accent);
    background: #eef2ff; border: 1px solid #c7d2fe;
    border-radius: 4px; padding: 2px 8px;
    text-decoration: none; white-space: nowrap;
    transition: background .15s;
  }}
  .web-link-btn:hover {{ background: #e0e7ff; }}
  .card-body {{
    display: none; border-top: 1px solid var(--border);
  }}
  .card-body.open {{ display: block; }}
  .nl-iframe {{
    width: 100%; border: none; display: block;
    min-height: 400px; max-height: 700px;
  }}
  .content-text {{
    white-space: pre-wrap; font-family: inherit;
    font-size: 13px; line-height: 1.85; color: #374151;
    padding: 16px 18px;
  }}
  .missing-list {{
    background: var(--card-bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px 18px;
    color: var(--muted); font-size: 13px; line-height: 2;
  }}
  @media (max-width: 720px) {{
    .sidebar {{ display: none; }}
    .main {{ margin-left: 0; padding: 16px; }}
  }}
</style>
</head>
<body>
<div id="quote-modal" style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);align-items:center;justify-content:center;">
  <div style="background:#fff;border-radius:14px;padding:22px 24px;width:420px;max-width:90vw;box-shadow:0 8px 32px rgba(0,0,0,.2);">
    <div style="font-size:13px;font-weight:800;margin-bottom:4px;color:#1c1c2e">📌 구절 저장</div>
    <div id="qm-meta" style="font-size:11px;color:#6b7280;margin-bottom:12px"></div>
    <textarea id="qm-text" placeholder="저장할 구절을 붙여넣으세요&#10;(비워두면 제목만 저장됩니다)" style="width:100%;height:100px;border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px;font-size:13px;font-family:inherit;resize:vertical;outline:none;line-height:1.7"></textarea>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button onclick="submitQuoteModal()" style="flex:1;padding:9px;background:#5b5ef4;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer">저장</button>
      <button onclick="closeQuoteModal()" style="padding:9px 16px;background:#f4f5f7;border:1px solid #e5e7eb;border-radius:8px;font-size:13px;cursor:pointer;color:#6b7280">취소</button>
    </div>
  </div>
</div>
<div id="toast"></div>
<nav class="sidebar">
  <div class="sidebar-tabs">
    <div class="sidebar-tab active" id="tab-list" onclick="switchTab('list')">📋 목록</div>
    <div class="sidebar-tab" id="tab-saved" onclick="switchTab('saved')">
      📌 저장함<span class="saved-badge" id="saved-badge">0</span>
    </div>
  </div>
  <div class="sidebar-panel" id="panel-list">
    {sidebar_items}
  </div>
  <div class="sidebar-panel hidden" id="panel-saved">
    <div id="saved-list">
      <div class="saved-empty">아직 저장된 항목이 없어요.<br>카드의 ☆ 버튼이나<br>텍스트 선택으로 저장하세요!</div>
    </div>
  </div>
  <div class="saved-actions" id="saved-actions" style="display:none">
    <button class="saved-copy-btn" onclick="copyAllSaved()">📋 공유용 텍스트 복사</button>
    <button class="saved-clear-btn" onclick="clearAllSaved()">전체 삭제</button>
  </div>
</nav>
<main class="main">
  <div class="page-header">
    <h1>📰 뉴스레터 다이제스트</h1>
    <p class="meta">{since} ~ {today} &nbsp;·&nbsp; {len(found)}개 뉴스레터 &nbsp;·&nbsp; 총 {total}개 메일</p>
  </div>
  {sections}
</main>
<script>
// ── 펼치기/접기 ──
function toggle(id) {{
  const body = document.getElementById('body-' + id);
  const btn  = document.getElementById('btn-'  + id);
  const open = body.classList.toggle('open');
  btn.textContent = open ? '접기 ▲' : '펼치기 ▼';
}}
function resizeIframe(iframe) {{
  try {{
    const doc = iframe.contentWindow.document;
    if (!doc.head.querySelector('base')) {{
      const base = doc.createElement('base');
      base.target = '_blank';
      doc.head.insertBefore(base, doc.head.firstChild);
    }}
    const h = doc.body.scrollHeight;
    iframe.style.height = Math.min(Math.max(h + 40, 400), 700) + 'px';
  }} catch(e) {{}}
}}

// ── 저장함 탭 전환 ──
function switchTab(tab) {{
  document.getElementById('tab-list').classList.toggle('active', tab === 'list');
  document.getElementById('tab-saved').classList.toggle('active', tab === 'saved');
  document.getElementById('panel-list').classList.toggle('hidden', tab !== 'list');
  document.getElementById('panel-saved').classList.toggle('hidden', tab !== 'saved');
  document.getElementById('saved-actions').style.display =
    (tab === 'saved' && getSaved().length > 0) ? 'flex' : 'none';
}}

// ── localStorage 헬퍼 ──
const STORAGE_KEY = 'nl-saved-{today}';
function getSaved() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }}
  catch(e) {{ return []; }}
}}
function setSaved(arr) {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(arr));
  updateBadge();
}}
function updateBadge() {{
  const n = getSaved().length;
  const badge = document.getElementById('saved-badge');
  badge.textContent = n;
  badge.style.display = n > 0 ? 'inline' : 'none';
}}

// ── 구절 입력 모달 ──
let _qmData = null;
function openQuoteModal(cardId, nl, date, subject, link) {{
  _qmData = {{ cardId, nl, date, subject, link }};
  document.getElementById('qm-meta').textContent = nl + ' · ' + date;
  document.getElementById('qm-text').value = '';
  const modal = document.getElementById('quote-modal');
  modal.style.display = 'flex';
  setTimeout(() => document.getElementById('qm-text').focus(), 50);
}}
function closeQuoteModal() {{
  document.getElementById('quote-modal').style.display = 'none';
  _qmData = null;
}}
function submitQuoteModal() {{
  if (!_qmData) return;
  const quote = document.getElementById('qm-text').value.trim();
  const saved = getSaved();
  saved.push({{
    id: _qmData.cardId + '-q' + Date.now(),
    nl: _qmData.nl, date: _qmData.date,
    subject: _qmData.subject, link: _qmData.link, quote
  }});
  setSaved(saved); renderSaved();
  const btn = document.getElementById('bm-' + _qmData.cardId);
  if (btn) {{ btn.classList.add('saved'); btn.textContent = '★'; }}
  closeQuoteModal();
  showToast(quote ? '구절이 저장됐어요 💬' : '저장함에 추가됐어요 ★');
  flashTab();
}}

// ── 북마크 버튼: 항상 모달 (여러 구절 추가 가능) ──
function toggleBookmark(e, cardId, nl, date, subject, link) {{
  e.stopPropagation();
  openQuoteModal(cardId, nl, date, subject, link);
}}

function flashTab() {{
  const t = document.getElementById('tab-saved');
  if (t) {{ t.style.color='#f59e0b'; setTimeout(()=>t.style.color='',800); }}
}}
document.getElementById('quote-modal').addEventListener('click', function(e) {{
  if (e.target === this) closeQuoteModal();
}});
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeQuoteModal();
}});

// ── 저장함 렌더링 ──
const NL_EMOJI = {{
  'GeekNews Weekly': '🖥️', 'NEWNEEK': '🌍', '미라클레터': '✨',
  'AINews': '🤖', 'STARTUP WEEKLY': '🚀', '데일리뉴스럴': '📡',
  '요즘IT': '💻', '어피티 잘쓸레터': '💰', '지피터스': '🧠',
  '폴인 fol:in': '📖', '헤이팝': '🎨', '소마코': '📣',
  '큐레터': '💌', 'Latent.Space': '🔬', '오렌지레터 산리': '🍊',
  '모두레터': '🤝', '밑미 meet me': '🌿', '고구마팜': '🌱',
  'BOODING': '🏠', 'Trend A Word': '📈', '서울시청': '🏛️',
  '응답하라 마케팅': '📢',
}};
function nlEmoji(name) {{ return NL_EMOJI[name] || '📰'; }}

function renderSaved() {{
  const saved = getSaved();
  const container = document.getElementById('saved-list');
  if (saved.length === 0) {{
    container.innerHTML = '<div class="saved-empty">아직 저장된 항목이 없어요.<br>☆ 버튼으로 구절을 저장하세요!</div>';
    document.getElementById('saved-actions').style.display = 'none';
    return;
  }}
  const groups = [];
  const groupMap = {{}};
  saved.forEach((s, i) => {{
    if (!groupMap[s.nl]) {{ groupMap[s.nl] = []; groups.push(s.nl); }}
    groupMap[s.nl].push({{ ...s, _idx: i }});
  }});
  container.innerHTML = groups.map(nl => {{
    const items = groupMap[nl];
    const itemsHtml = items.map(s => `
      <div class="saved-item">
        <div class="saved-item-actions">
          <button class="saved-item-copy" onclick="copySingle(${{s._idx}})" title="이 항목만 복사">📋</button>
          <button class="saved-item-del" onclick="deleteSaved(${{s._idx}})" title="삭제">✕</button>
        </div>
        ${{s.quote
          ? `<div class="saved-item-quote">${{s.quote}}</div>`
          : `<div class="saved-item-quote" style="color:var(--muted);font-style:italic">[${{s.subject}}]</div>`
        }}
        <div class="saved-item-subject">${{s.subject}}</div>
        ${{s.link ? `<a class="saved-item-link" href="${{s.link}}" target="_blank">🔗 원문 보기</a>` : ''}}
      </div>
    `).join('');
    return `<div class="saved-group">
      <div class="saved-group-header">${{nlEmoji(nl)}} ${{nl}}</div>
      ${{itemsHtml}}
    </div>`;
  }}).join('');
  const isOnSavedTab = !document.getElementById('panel-saved').classList.contains('hidden');
  document.getElementById('saved-actions').style.display = isOnSavedTab ? 'flex' : 'none';
  const savedCardIds = new Set(saved.map(s => s.id.split('-q')[0]));
  savedCardIds.forEach(cardId => {{
    const btn = document.getElementById('bm-' + cardId);
    if (btn) {{ btn.classList.add('saved'); btn.textContent = '★'; }}
  }});
}}

function deleteSaved(idx) {{
  const saved = getSaved();
  const item = saved[idx];
  if (item && !item.quote) {{
    const btn = document.getElementById('bm-' + item.id);
    if (btn) {{ btn.classList.remove('saved'); btn.textContent = '☆'; }}
  }}
  saved.splice(idx, 1);
  setSaved(saved);
  renderSaved();
}}

function clearAllSaved() {{
  if (!confirm('저장함을 모두 비울까요?')) return;
  getSaved().forEach(s => {{
    if (!s.quote) {{
      const btn = document.getElementById('bm-' + s.id);
      if (btn) {{ btn.classList.remove('saved'); btn.textContent = '☆'; }}
    }}
  }});
  setSaved([]);
  renderSaved();
}}

// ── 공유용 텍스트 복사 ──
function formatItem(s) {{
  const body = s.quote ? s.quote : `[${{s.subject}}]`;
  const src  = s.link ? `출처: ${{s.nl}} (${{s.link}})` : `출처: ${{s.nl}}`;
  return `${{body}}\n- ${{src}}`;
}}

function copySingle(idx) {{
  const s = getSaved()[idx];
  if (!s) return;
  navigator.clipboard.writeText(formatItem(s)).then(() => {{
    showToast('복사됐어요! 붙여넣기 하세요 📋');
  }}).catch(() => {{ prompt('아래 텍스트를 복사하세요:', formatItem(s)); }});
}}

function copyAllSaved() {{
  const saved = getSaved();
  if (saved.length === 0) return;
  const groups = [];
  const groupMap = {{}};
  saved.forEach(s => {{
    if (!groupMap[s.nl]) {{ groupMap[s.nl] = []; groups.push(s.nl); }}
    groupMap[s.nl].push(s);
  }});
  const text = groups.map(nl =>
    `${{nlEmoji(nl)}} ${{nl}}\n` + groupMap[nl].map(formatItem).join('\n\n')
  ).join('\n\n──────────\n\n');
  navigator.clipboard.writeText(text).then(() => {{
    showToast('클립보드에 복사됐어요! 붙여넣기 하세요 📋');
  }}).catch(() => {{
    prompt('아래 텍스트를 복사하세요:', text);
  }});
}}

// ── 토스트 ──
let _toastTimer = null;
function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {{ t.style.display = 'none'; }}, 2200);
}}

// ── 초기화 ──
updateBadge();
renderSaved();
</script>
</body>
</html>"""

    return html


# ──────────────────────────────────────────────
#  Obsidian 마크다운 생성
# ──────────────────────────────────────────────
def generate_obsidian_md(results, days):
    today = datetime.now().strftime("%Y-%m-%d")
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    total = sum(len(v) for v in results.values())

    lines = [
        f"# 📰 뉴스레터 다이제스트 {today}",
        "",
        f"- **기간**: {since} ~ {today}",
        f"- **수신**: {len(results)}개 뉴스레터 · {total}개 메일",
        "",
        "---",
        "",
    ]

    for name in sorted(results.keys()):
        lines.append(f"## {name}")
        lines.append("")
        for item in results[name]:
            date_fmt = item["date"].strftime("%Y-%m-%d %H:%M")
            lines.append(f"### {item['subject']}")
            lines.append(f"> {date_fmt}")
            if item["web_link"]:
                lines.append(f"> 🔗 [원문 보기]({item['web_link']})")
            lines.append("")
            text = item["text"]
            if len(text) > 3000:
                text = text[:3000] + "\n\n*(이하 생략 — 전체 내용은 HTML 파일 참조)*"
            lines.append(text)
            lines.append("")
            lines.append("---")
            lines.append("")

    missing = [n for n in NEWSLETTERS if n not in results]
    if missing:
        lines.append("## 이번 주 수신 없음")
        lines.append("")
        for n in missing:
            lines.append(f"- {n}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
#  메인
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="뉴스레터 다이제스트 생성")
    parser.add_argument("--days",    type=int, default=None, help="최근 N일 수집 (기본: 10)")
    parser.add_argument("--email",   type=str, default="", help="네이버 이메일 주소")
    parser.add_argument("--no-open", action="store_true",  help="브라우저 자동 열기 비활성화")
    args = parser.parse_args()

    print("=" * 50)
    print("  📰 뉴스레터 다이제스트")
    print("=" * 50)

    if args.days is None:
        try:
            days_input = input("📅 몇 일치 수집할까요? (Enter = 10일): ").strip()
            args.days = int(days_input) if days_input else 10
        except (ValueError, EOFError):
            args.days = 10
        print(f"  → 최근 {args.days}일 수집")

    naver_email = (
        args.email
        or os.getenv("NAVER_EMAIL")
        or input("네이버 이메일(예: id@naver.com): ").strip()
    )
    password = (
        os.getenv("NAVER_PASSWORD")
        or getpass.getpass("네이버 비밀번호 (입력해도 화면에 표시 안 됨): ")
    )

    results = fetch_newsletters(naver_email, password, args.days)
    if not results:
        print("수집된 뉴스레터가 없습니다. 날짜 범위를 늘려보세요 (--days 14).")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUTPUT_DIR / f"newsletter_{today}.html"
    html_path.write_text(generate_html(results, args.days), encoding="utf-8")
    print(f"📄 HTML  → {html_path}")

    obs_dir = OBSIDIAN_VAULT / "뉴스레터 다이제스트"
    obs_dir.mkdir(parents=True, exist_ok=True)
    md_path = obs_dir / f"{today}_weekly.md"
    md_path.write_text(generate_obsidian_md(results, args.days), encoding="utf-8")
    print(f"📝 Obsidian → {md_path}")

    if not args.no_open:
        subprocess.run(["open", str(html_path)])
        print("\n✨ 완료! 브라우저에서 HTML이 열렸습니다.")
    else:
        print("\n✨ 완료!")


if __name__ == "__main__":
    main()
