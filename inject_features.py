#!/usr/bin/env python3
"""
뉴스레터 다이제스트 HTML에 저장함 기능 inject (v2)
- 저장 버튼을 card-header 밖 (card-body 바로 앞)에 삽입 → onclick 충돌 없음
사용: python3 inject_features.py [입력.html] [출력.html]
"""
import sys, re
from pathlib import Path

OUTPUT_DIR = Path.home() / "newsletter-digest" / "output"
src  = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(OUTPUT_DIR.glob("newsletter_*.html"))[-1]
dest = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_DIR / (src.stem + "_injected.html")

html = src.read_text(encoding="utf-8")

# ── 1. iframe sandbox 패치 ──
html = html.replace(
    'sandbox="allow-same-origin allow-popups"',
    'sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"'
)

# ── 2. card-body 바로 앞에 ☆저장 버튼 삽입 (card-header 밖) ──
def insert_bm_btn(m):
    card_id = m.group(1)  # e.g. "AINews-0"
    btn = (
        f'<button class="bm-btn" id="bm-{card_id}" '
        f'onclick="openQuoteModal(event,this)">☆ 저장</button>\n          '
    )
    return btn + m.group(0)

html = re.sub(
    r'<div class="card-body" id="body-([^"]+)">',
    insert_bm_btn,
    html
)

# ── 3. </body> 직전에 저장함 기능 삽입 ──
FEATURES = r"""
<!-- ── 저장함 inject v2 ── -->
<div id="quote-modal" style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);align-items:center;justify-content:center;">
  <div style="background:#fff;border-radius:14px;padding:22px 24px;width:420px;max-width:90vw;box-shadow:0 8px 32px rgba(0,0,0,.2);">
    <div style="font-size:13px;font-weight:800;margin-bottom:4px;color:#1c1c2e">📌 구절 저장</div>
    <div id="qm-meta" style="font-size:11px;color:#6b7280;margin-bottom:12px"></div>
    <textarea id="qm-text" placeholder="저장할 구절을 붙여넣으세요&#10;(비워두면 제목만 저장됩니다)" style="width:100%;height:100px;border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px;font-size:13px;font-family:inherit;resize:vertical;outline:none;line-height:1.7;box-sizing:border-box;"></textarea>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button id="qm-save-btn" style="flex:1;padding:9px;background:#5b5ef4;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer">저장</button>
      <button id="qm-cancel-btn" style="padding:9px 16px;background:#f4f5f7;border:1px solid #e5e7eb;border-radius:8px;font-size:13px;cursor:pointer;color:#6b7280">취소</button>
    </div>
  </div>
</div>
<div id="nl-toast" style="display:none;position:fixed;bottom:28px;right:28px;background:#1c1c2e;color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;font-weight:600;box-shadow:0 4px 16px rgba(0,0,0,.2);z-index:10000"></div>
<style>
  .bm-btn {
    display:none;
    background:#eef2ff; border:1px solid #c7d2fe;
    border-radius:0 0 6px 6px;
    cursor:pointer; font-size:11px; padding:3px 10px;
    color:#5b5ef4; transition:all .15s; white-space:nowrap;
    width:100%; text-align:right;
  }
  .bm-btn:hover { background:#5b5ef4; color:#fff; }
  .bm-btn.saved { background:#fef3c7; border-color:#fcd34d; color:#d97706; }
  .card:hover .bm-btn { display:block; }
  .bm-btn.saved { display:block !important; }

  .sidebar { padding:0 !important; gap:0 !important; display:flex !important; flex-direction:column !important; }
  .sidebar-tabs { display:flex; border-bottom:1px solid var(--border); flex-shrink:0; }
  .sidebar-tab { flex:1; padding:10px 4px; font-size:11px; font-weight:700; text-align:center; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent; transition:all .15s; user-select:none; }
  .sidebar-tab.active { color:var(--accent); border-bottom-color:var(--accent); }
  .sidebar-panel { flex:1; overflow-y:auto; }
  .sidebar-panel.hidden { display:none !important; }
  .saved-badge { background:#f87171; color:#fff; border-radius:10px; padding:1px 6px; font-size:10px; font-weight:700; margin-left:4px; display:none; }
  .saved-empty { padding:28px 16px; text-align:center; font-size:12px; color:#aaa; line-height:2; }
  .saved-group { margin-bottom:0; }
  .saved-group-header { display:flex; align-items:center; gap:6px; padding:10px 14px 8px; font-size:12px; font-weight:800; color:#fff; background:var(--accent); }
  .saved-group + .saved-group { margin-top:10px; }
  .saved-item { margin:0; padding:12px 14px; background:var(--card-bg); border-bottom:1px solid var(--border); font-size:12px; position:relative; }
  .saved-item:last-child { border-bottom:none; }
  .saved-item-actions { position:absolute; top:8px; right:8px; display:flex; gap:2px; }
  .saved-item-del, .saved-item-copy { background:none; border:none; cursor:pointer; font-size:12px; padding:2px 4px; border-radius:4px; color:#d1d5db; }
  .saved-item-del:hover { color:#f87171; background:#fff1f1; }
  .saved-item-copy:hover { color:var(--accent); background:#eef2ff; }
  .saved-item-quote { font-size:12px; color:#1c1c2e; line-height:1.7; border-left:3px solid var(--accent); padding-left:8px; margin:0 0 6px; white-space:pre-wrap; word-break:break-word; }
  .saved-item-subject { font-size:10px; color:var(--muted); margin-bottom:4px; }
  .saved-item-link { font-size:10px; color:var(--accent); text-decoration:none; }
  .saved-item-link:hover { text-decoration:underline; }
  .saved-actions { padding:8px 10px; display:flex; gap:6px; flex-shrink:0; border-top:1px solid var(--border); }
  .saved-copy-btn { flex:1; padding:8px; font-size:12px; font-weight:700; background:var(--accent); color:#fff; border:none; border-radius:7px; cursor:pointer; }
  .saved-copy-btn:hover { opacity:.85; }
  .saved-clear-btn { padding:8px 10px; font-size:11px; color:var(--muted); background:var(--bg); border:1px solid var(--border); border-radius:7px; cursor:pointer; }
</style>
<script>
(function() {
  // ── resizeIframe 패치: iframe 링크 새 탭으로 열기 ──
  var _origResize = window.resizeIframe;
  window.resizeIframe = function(iframe) {
    try {
      var doc = iframe.contentWindow.document;
      if (doc.head && !doc.head.querySelector('base')) {
        var base = doc.createElement('base');
        base.target = '_blank';
        doc.head.insertBefore(base, doc.head.firstChild);
      }
    } catch(e) {}
    if (typeof _origResize === 'function') _origResize(iframe);
  };

  // ── 사이드바 탭 구조 재구성 ──
  var sidebar = document.querySelector('.sidebar');
  if (sidebar) {
    var origHTML = sidebar.innerHTML;

    var tabsEl = document.createElement('div');
    tabsEl.className = 'sidebar-tabs';

    var t1 = document.createElement('div');
    t1.className = 'sidebar-tab active'; t1.id = 'tab-list'; t1.textContent = '📋 목록';
    t1.onclick = function() { switchSavedTab('list'); };

    var t2 = document.createElement('div');
    t2.className = 'sidebar-tab'; t2.id = 'tab-saved';
    t2.innerHTML = '📌 저장함<span class="saved-badge" id="saved-badge"></span>';
    t2.onclick = function() { switchSavedTab('saved'); };

    tabsEl.appendChild(t1);
    tabsEl.appendChild(t2);

    var panelList = document.createElement('div');
    panelList.className = 'sidebar-panel'; panelList.id = 'panel-list';
    panelList.innerHTML = origHTML;

    var panelSaved = document.createElement('div');
    panelSaved.className = 'sidebar-panel hidden'; panelSaved.id = 'panel-saved';
    panelSaved.innerHTML = '<div id="saved-list"></div>';

    var actionsEl = document.createElement('div');
    actionsEl.className = 'saved-actions'; actionsEl.id = 'saved-actions';
    actionsEl.style.display = 'none';
    actionsEl.innerHTML =
      '<button class="saved-copy-btn" id="copy-all-btn">📋 공유용 텍스트 복사</button>' +
      '<button class="saved-clear-btn" id="clear-all-btn">전체 삭제</button>';

    sidebar.innerHTML = '';
    sidebar.appendChild(tabsEl);
    sidebar.appendChild(panelList);
    sidebar.appendChild(panelSaved);
    sidebar.appendChild(actionsEl);

    document.getElementById('copy-all-btn').onclick = copyAllSaved;
    document.getElementById('clear-all-btn').onclick = clearAllSaved;
  }

  // ── 모달 이벤트 ──
  var modal = document.getElementById('quote-modal');
  document.getElementById('qm-save-btn').onclick = submitQuoteModal;
  document.getElementById('qm-cancel-btn').onclick = closeQuoteModal;
  modal.onclick = function(e) { if (e.target === this) closeQuoteModal(); };
  document.onkeydown = function(e) { if (e.key === 'Escape') closeQuoteModal(); };

  updateSavedBadge();
  renderSaved();
})();

// ── openQuoteModal (카드 버튼에서 직접 호출) ──
var _qmData = null;
function openQuoteModal(e, btn) {
  e.stopPropagation();
  var cardId  = btn.id.replace('bm-', '');
  // 버튼은 card-header 다음 형제 → previousElementSibling = card-header
  var header  = btn.previousElementSibling;
  var card    = btn.parentElement;
  var section = card.closest('section');
  var nl      = section ? (section.querySelector('.section-title') || {textContent:''}).textContent.trim() : '';
  var date    = (header && header.querySelector('.card-date') || {textContent:''}).textContent.trim();
  var subject = (header && header.querySelector('.card-subject') || {textContent:''}).textContent.trim();
  var linkEl  = header && header.querySelector('.web-link-btn');
  var link    = linkEl ? linkEl.href : '';

  _qmData = { cardId: cardId, nl: nl, date: date, subject: subject, link: link };
  document.getElementById('qm-meta').textContent = nl + (date ? ' · ' + date : '');
  document.getElementById('qm-text').value = '';
  document.getElementById('quote-modal').style.display = 'flex';
  setTimeout(function() { document.getElementById('qm-text').focus(); }, 50);
}
function closeQuoteModal() {
  document.getElementById('quote-modal').style.display = 'none';
  _qmData = null;
}
function submitQuoteModal() {
  if (!_qmData) return;
  var quote = document.getElementById('qm-text').value.trim();
  var saved = getSaved();
  saved.push({
    id: _qmData.cardId + '-q' + Date.now(),
    nl: _qmData.nl, date: _qmData.date,
    subject: _qmData.subject, link: _qmData.link, quote: quote
  });
  setSaved(saved);
  renderSaved();
  var btn = document.getElementById('bm-' + _qmData.cardId);
  if (btn) { btn.classList.add('saved'); btn.textContent = '★ 저장됨'; }
  closeQuoteModal();
  showNlToast(quote ? '구절이 저장됐어요 💬' : '저장함에 추가됐어요 ★');
  flashSavedTab();
}

// ── 탭 전환 ──
function switchSavedTab(tab) {
  document.getElementById('tab-list').classList.toggle('active', tab === 'list');
  document.getElementById('tab-saved').classList.toggle('active', tab === 'saved');
  document.getElementById('panel-list').classList.toggle('hidden', tab !== 'list');
  document.getElementById('panel-saved').classList.toggle('hidden', tab !== 'saved');
  var actions = document.getElementById('saved-actions');
  if (actions) actions.style.display = (tab === 'saved' && getSaved().length > 0) ? 'flex' : 'none';
}

// ── localStorage ──
var STORAGE_KEY = 'nl-saved-2026-03-02';
function getSaved() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch(e) { return []; }
}
function setSaved(arr) { localStorage.setItem(STORAGE_KEY, JSON.stringify(arr)); updateSavedBadge(); }
function updateSavedBadge() {
  var n = getSaved().length;
  var b = document.getElementById('saved-badge');
  if (b) { b.textContent = n || ''; b.style.display = n > 0 ? 'inline' : 'none'; }
}

// ── 이모지 맵 ──
var NL_EMOJI = {
  'GeekNews Weekly':'🖥️','NEWNEEK':'🌍','미라클레터':'✨','AINews':'🤖',
  'STARTUP WEEKLY':'🚀','데일리뉴스럴':'📡','요즘IT':'💻','어피티 잘쓸레터':'💰',
  '지피터스':'🧠','폴인 fol:in':'📖','헤이팝':'🎨','소마코':'📣',
  '큐레터':'💌','Latent.Space':'🔬','오렌지레터 산리':'🍊','모두레터':'🤝',
  '밑미 meet me':'🌿','고구마팜':'🌱','BOODING':'🏠','Trend A Word':'📈',
  '서울시청':'🏛️','응답하라 마케팅':'📢'
};
function nlEmoji(n) { return NL_EMOJI[n] || '📰'; }
function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── 저장함 렌더링 ──
function renderSaved() {
  var saved = getSaved();
  var container = document.getElementById('saved-list');
  if (!container) return;
  if (saved.length === 0) {
    container.innerHTML = '<div class="saved-empty">아직 저장된 항목이 없어요.<br>카드에 마우스를 올려<br>☆ 저장 버튼을 눌러보세요!</div>';
    var a = document.getElementById('saved-actions');
    if (a) a.style.display = 'none';
    return;
  }
  var groups = [], gmap = {};
  saved.forEach(function(s, i) {
    if (!gmap[s.nl]) { gmap[s.nl] = []; groups.push(s.nl); }
    gmap[s.nl].push({ s: s, i: i });
  });
  var h = '';
  groups.forEach(function(nl) {
    h += '<div class="saved-group"><div class="saved-group-header">' + nlEmoji(nl) + ' ' + escHtml(nl) + '</div>';
    gmap[nl].forEach(function(item) {
      var s = item.s, i = item.i;
      var qh = s.quote
        ? '<div class="saved-item-quote">' + escHtml(s.quote) + '</div>'
        : '<div class="saved-item-quote" style="color:var(--muted);font-style:italic">[' + escHtml(s.subject) + ']</div>';
      var lh = s.link ? '<a class="saved-item-link" href="' + escHtml(s.link) + '" target="_blank">🔗 원문 보기</a>' : '';
      h += '<div class="saved-item">'
        + '<div class="saved-item-actions">'
        + '<button class="saved-item-copy" data-idx="' + i + '" title="이 항목만 복사">📋</button>'
        + '<button class="saved-item-del" data-idx="' + i + '" title="삭제">✕</button>'
        + '</div>'
        + qh
        + '<div class="saved-item-subject">' + escHtml(s.subject) + '</div>'
        + lh + '</div>';
    });
    h += '</div>';
  });
  container.innerHTML = h;
  container.onclick = function(e) {
    var c = e.target.closest('.saved-item-copy');
    var d = e.target.closest('.saved-item-del');
    if (c) copySingle(parseInt(c.dataset.idx));
    if (d) deleteSaved(parseInt(d.dataset.idx));
  };
  var onSaved = document.getElementById('panel-saved') &&
    !document.getElementById('panel-saved').classList.contains('hidden');
  var a = document.getElementById('saved-actions');
  if (a) a.style.display = onSaved ? 'flex' : 'none';
  // 이미 저장된 카드 버튼 표시
  var ids = new Set(saved.map(function(s) { return s.id.split('-q')[0]; }));
  ids.forEach(function(id) {
    var btn = document.getElementById('bm-' + id);
    if (btn) { btn.classList.add('saved'); btn.textContent = '★ 저장됨'; }
  });
}

function deleteSaved(idx) {
  var saved = getSaved(); saved.splice(idx, 1); setSaved(saved); renderSaved();
}
function clearAllSaved() {
  if (!confirm('저장함을 모두 비울까요?')) return; setSaved([]); renderSaved();
}
function formatItem(s) {
  var body = s.quote ? s.quote : '[' + s.subject + ']';
  var src  = s.link ? '출처: ' + s.nl + ' (' + s.link + ')' : '출처: ' + s.nl;
  return body + '\n- ' + src;
}
function copySingle(idx) {
  var s = getSaved()[idx]; if (!s) return;
  navigator.clipboard.writeText(formatItem(s))
    .then(function() { showNlToast('복사됐어요! 붙여넣기 하세요 📋'); })
    .catch(function() { prompt('복사하세요:', formatItem(s)); });
}
function copyAllSaved() {
  var saved = getSaved(); if (!saved.length) return;
  var groups = [], gmap = {};
  saved.forEach(function(s) {
    if (!gmap[s.nl]) { gmap[s.nl] = []; groups.push(s.nl); }
    gmap[s.nl].push(s);
  });
  var text = groups.map(function(nl) {
    return nlEmoji(nl) + ' ' + nl + '\n' + gmap[nl].map(formatItem).join('\n\n');
  }).join('\n\n──────────\n\n');
  navigator.clipboard.writeText(text)
    .then(function() { showNlToast('클립보드에 복사됐어요! 붙여넣기 하세요 📋'); })
    .catch(function() { prompt('복사하세요:', text); });
}
var _toastTimer = null;
function showNlToast(msg) {
  var t = document.getElementById('nl-toast');
  t.textContent = msg; t.style.display = 'block';
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function() { t.style.display = 'none'; }, 2200);
}
function flashSavedTab() {
  var t = document.getElementById('tab-saved');
  if (t) { t.style.color = '#f59e0b'; setTimeout(function() { t.style.color = ''; }, 800); }
}
</script>
"""

last_idx = html.rfind('</body>')
if last_idx == -1:
    print("❌ </body> 태그를 찾지 못했습니다.")
    import sys; sys.exit(1)

html = html[:last_idx] + FEATURES + html[last_idx:]
dest.write_text(html, encoding="utf-8")
print(f"✅ {dest}")
