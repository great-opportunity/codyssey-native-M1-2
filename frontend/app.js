// 백엔드 주소: Vercel 빌드 때 환경 변수 API_BASE_URL로 config.js가 만들어진다 (build.sh 참고).
const API = ((window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || "http://127.0.0.1:8000").replace(/\/$/, "");

const $ = (sel) => document.querySelector(sel);
const state = { conversationId: null, data: [], editingId: null, sending: false };

// ---------- 공통 ----------
async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(body, res.status));
  return body;
}

function errorText(body, status) {
  const d = body && body.detail;
  if (Array.isArray(d)) return d.map((e) => `${e.loc.slice(-1)[0]}: ${e.msg}`).join(" / ");
  return d || `요청 실패 (${status})`;
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 2) => (n == null ? "-" : Number(n).toLocaleString("ko-KR", { maximumFractionDigits: d }));
const usd = (n) => (n == null ? "-" : "$" + fmt(n));

function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 2200);
}

// AI 답변의 간단한 마크다운(굵게, 목록, 줄바꿈)만 HTML로
function renderMarkdown(text) {
  const lines = esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").split("\n");
  let html = "", list = null;
  for (const line of lines) {
    const m = line.match(/^\s*(?:[-*•]|(\d+)\.)\s+(.*)$/);
    if (m) {
      const tag = m[1] ? "ol" : "ul";
      if (list !== tag) { if (list) html += `</${list}>`; html += `<${tag}>`; list = tag; }
      html += `<li>${m[2]}</li>`;
      continue;
    }
    if (list) { html += `</${list}>`; list = null; }
    if (line.trim()) html += `<p>${line}</p>`;
  }
  return html + (list ? `</${list}>` : "");
}

// ---------- 서버 깨우기 (Render 무료 티어 콜드스타트 대응) ----------
async function wakeServer() {
  const status = $("#serverStatus");
  const slow = setTimeout(() => ($("#coldBanner").hidden = false), 3000);
  for (let i = 0; i < 6; i++) {
    try {
      await api("/");
      clearTimeout(slow);
      $("#coldBanner").hidden = true;
      status.className = "pill pill-ok";
      status.textContent = "서버 연결됨";
      return true;
    } catch (e) {
      await new Promise((r) => setTimeout(r, 5000));
    }
  }
  clearTimeout(slow);
  status.className = "pill pill-err";
  status.textContent = "서버 연결 실패";
  $("#coldBanner").textContent = "서버에 연결하지 못했어요. 잠시 후 새로고침해 주세요.";
  return false;
}

// ---------- 요약 ----------
async function loadSummary() {
  const s = await api("/api/data/summary");
  const changeCls = s.change_pct > 0 ? "up" : s.change_pct < 0 ? "down" : "";
  $("#summaryGrid").innerHTML = [
    ["기간", `${s.start_date ?? "-"}`, `~ ${s.end_date ?? "-"}`],
    ["데이터 개수", `${s.count}개`, "일별 1개씩"],
    ["최신 값", usd(s.latest_value), `기간 변화 <span class="${changeCls}">${s.change_pct > 0 ? "+" : ""}${s.change_pct ?? "-"}%</span>`],
    ["평균", usd(s.mean), `30일 변동성 ${s.volatility_30d ?? "-"}%`],
    ["최고 / 최저", usd(s.max), `${s.max_date ?? ""} / 최저 ${usd(s.min)}`],
  ].map(([l, v, sub]) => `<div class="stat"><div class="stat-label">${l}</div><div class="stat-value">${v}</div><div class="stat-sub">${sub}</div></div>`).join("");

  const badge = $("#trendBadge");
  const icon = { 증가: "▲", 감소: "▼", 유지: "■" }[s.trend] || "·";
  badge.textContent = `최근 추세 ${icon} ${s.trend}`;
  badge.className = "badge " + ({ 증가: "up", 감소: "down", 유지: "flat" }[s.trend] || "");
  $("#trendDetail").textContent = s.trend_detail;
}

// ---------- 채팅 ----------
function addMessage(role, content, extra = {}) {
  $("#welcome")?.remove();
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}` + (extra.error ? " error" : "");
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant" && !extra.error) bubble.innerHTML = renderMarkdown(content);
  else bubble.textContent = content;
  wrap.appendChild(bubble);
  if (extra.tools && extra.tools.length) {
    const tools = document.createElement("div");
    tools.className = "tools";
    tools.innerHTML = extra.tools.map((t) => `<span class="tool-tag" title="${esc(JSON.stringify(t.arguments))}">🔧 ${esc(t.name)}</span>`).join("");
    wrap.appendChild(tools);
  }
  $("#messages").appendChild(wrap);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return wrap;
}

function showTyping() {
  const el = addMessage("assistant", "");
  el.querySelector(".bubble").innerHTML =
    '<span class="typing"><i></i><i></i><i></i></span><span class="typing-text">데이터 확인하고 답변 만드는 중…</span>';
  return el;
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || state.sending) return;
  state.sending = true;
  $("#sendBtn").disabled = true;
  $("#chatInput").value = "";
  autoGrow();
  addMessage("user", text);
  const typing = showTyping();
  try {
    const res = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, conversation_id: state.conversationId }),
    });
    typing.remove();
    addMessage("assistant", res.reply, { tools: res.tool_calls });
    state.conversationId = res.conversation_id;
    await loadConversations();
  } catch (e) {
    typing.remove();
    addMessage("assistant", "⚠️ " + e.message, { error: true });
  } finally {
    state.sending = false;
    $("#sendBtn").disabled = false;
    $("#chatInput").focus();
  }
}

function resetChat() {
  state.conversationId = null;
  $("#messages").innerHTML = `
    <div class="welcome" id="welcome">
      <p class="welcome-title">무엇이든 물어보세요 👋</p>
      <p class="muted">저장된 비트코인 일별 종가 데이터를 바탕으로 답해요.</p>
      <div class="chips">
        <button class="chip" type="button">최근 일주일 추세 어때?</button>
        <button class="chip" type="button">기간 중 최고가와 최저가는 언제였어?</button>
        <button class="chip" type="button">9월 한 달 흐름을 요약해줘</button>
        <button class="chip" type="button">가장 크게 오른 날은?</button>
      </div>
    </div>`;
  highlightConversation();
}

function autoGrow() {
  const ta = $("#chatInput");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
}

// ---------- 대화 기록 ----------
async function loadConversations() {
  const list = await api("/api/conversations");
  $("#convEmpty").hidden = list.length > 0;
  $("#convList").innerHTML = list.map((c) => `
    <li class="conv-item" data-id="${c.id}">
      <div class="conv-text">
        <div class="conv-title">${esc(c.title || "제목 없음")}</div>
        <div class="conv-meta">${c.message_count}개 메시지 · ${new Date(c.updated_at).toLocaleDateString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</div>
      </div>
      <button class="conv-del" type="button" aria-label="대화 삭제" data-del="${c.id}">✕</button>
    </li>`).join("");
  highlightConversation();
}

function highlightConversation() {
  document.querySelectorAll(".conv-item").forEach((el) =>
    el.classList.toggle("active", el.dataset.id === state.conversationId));
}

async function openConversation(id) {
  try {
    const conv = await api(`/api/conversations/${id}`);
    state.conversationId = id;
    $("#messages").innerHTML = "";
    conv.messages.forEach((m) => addMessage(m.role, m.content));
    highlightConversation();
    switchTab("chat");
    scrollToChatOnMobile();
  } catch (e) {
    toast("대화를 불러오지 못했어요: " + e.message);
  }
}

async function deleteConversation(id) {
  if (!confirm("이 대화를 삭제할까요?")) return;
  try {
    await api(`/api/conversations/${id}`, { method: "DELETE" });
    if (state.conversationId === id) resetChat();
    await loadConversations();
    toast("대화를 삭제했어요");
  } catch (e) {
    toast("삭제 실패: " + e.message);
  }
}

// 모바일에선 대화 목록이 채팅 아래에 있어서, 대화를 열면 채팅 쪽으로 올려 준다
function scrollToChatOnMobile() {
  if (matchMedia("(max-width: 900px)").matches) $("#tab-chat").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- 데이터 관리 ----------
async function loadData(flashId) {
  state.data = await api("/api/data");
  $("#dataCount").textContent = `(${state.data.length}개)`;
  // 최신 날짜가 위로 오게
  $("#dataBody").innerHTML = [...state.data].reverse().map((d) => `
    <tr data-id="${d.id}" class="${d.id === flashId ? "flash" : ""}">
      <td>${d.date}</td>
      <td class="num">${fmt(d.value)}</td>
      <td>${esc(d.memo || "")}</td>
      <td>
        <button class="btn-link" type="button" data-edit="${d.id}">수정</button>
        <button class="btn-link danger" type="button" data-remove="${d.id}">삭제</button>
      </td>
    </tr>`).join("");
  await loadStatistics();
}

function setFormMsg(text, ok) {
  const el = $("#formMsg");
  el.textContent = text;
  el.className = "form-msg " + (ok ? "ok" : "err");
}

function startEdit(id) {
  const d = state.data.find((x) => x.id === id);
  if (!d) return;
  state.editingId = id;
  $("#fDate").value = d.date;
  $("#fValue").value = d.value;
  $("#fMemo").value = d.memo || "";
  $("#formTitle").textContent = `데이터 수정 (${d.date})`;
  $("#fSubmit").textContent = "수정 저장";
  $("#fCancel").hidden = false;
  setFormMsg("", true);
  $("#dataForm").scrollIntoView({ behavior: "smooth", block: "center" });
}

function cancelEdit() {
  state.editingId = null;
  $("#dataForm").reset();
  $("#formTitle").textContent = "새 데이터 추가";
  $("#fSubmit").textContent = "추가";
  $("#fCancel").hidden = true;
}

async function submitData(e) {
  e.preventDefault();
  const body = { date: $("#fDate").value, value: Number($("#fValue").value), memo: $("#fMemo").value };
  const editing = state.editingId;
  try {
    const saved = editing
      ? await api(`/api/data/${editing}`, { method: "PUT", body: JSON.stringify(body) })
      : await api("/api/data", { method: "POST", body: JSON.stringify(body) });
    cancelEdit();
    setFormMsg(`✅ ${saved.date} 데이터를 ${editing ? "수정" : "추가"}했어요 (값 ${fmt(saved.value)})`, true);
    await Promise.all([loadData(saved.id), loadSummary()]);
  } catch (err) {
    setFormMsg("❌ " + err.message, false);
  }
}

async function removeData(id) {
  const d = state.data.find((x) => x.id === id);
  if (!confirm(`${d ? d.date : ""} 데이터를 삭제할까요?`)) return;
  try {
    await api(`/api/data/${id}`, { method: "DELETE" });
    setFormMsg(`🗑️ ${d ? d.date : ""} 데이터를 삭제했어요`, true);
    if (state.editingId === id) cancelEdit();
    await Promise.all([loadData(), loadSummary()]);
  } catch (err) {
    setFormMsg("❌ " + err.message, false);
  }
}

function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

function exportCsv() {
  const quote = (s) => `"${String(s).replace(/"/g, '""')}"`;
  const rows = state.data.map((d) => [d.date, d.value, quote(d.memo || "")].join(","));
  // ﻿: 엑셀에서 한글 메모가 깨지지 않게
  download("btc_data.csv", "﻿date,value,memo\n" + rows.join("\n"), "text/csv;charset=utf-8");
}

function exportJson() {
  download("btc_data.json", JSON.stringify(state.data.map(({ date, value, memo }) => ({ date, value, memo })), null, 2), "application/json");
}

// ---------- 통계 + 그래프 (보너스) ----------
async function loadStatistics() {
  const s = await api("/api/data/statistics");
  drawChart(s.series);
  const last = s.monthly[s.monthly.length - 1];
  $("#extraStats").innerHTML = s.best_day ? [
    ["최대 상승일", `+${s.best_day.return_pct}%`, s.best_day.date],
    ["최대 하락일", `${s.worst_day.return_pct}%`, s.worst_day.date],
    ["상승 / 하락 일수", `${s.up_days} / ${s.down_days}일`, `상승 비율 ${Math.round((s.up_days / (s.up_days + s.down_days)) * 100)}%`],
    ["이번 달 평균", usd(last.mean), `${last.month} (${last.count}일)`],
  ].map(([l, v, sub]) => `<div class="stat"><div class="stat-label">${l}</div><div class="stat-value">${v}</div><div class="stat-sub">${sub}</div></div>`).join("") : "";
}

function drawChart(series) {
  const box = $("#chart");
  if (!series.length) { box.innerHTML = '<p class="muted">데이터가 2개 이상 있어야 그래프가 보여요.</p>'; return; }
  const W = box.clientWidth || 700, H = box.clientHeight || 260;
  const pad = { t: 10, r: 12, b: 26, l: 58 };
  const vals = series.flatMap((s) => [s.value, s.ma7]).filter((v) => v != null);
  let min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  min -= span * 0.05; max += span * 0.05;
  const x = (i) => pad.l + (i / Math.max(series.length - 1, 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - min) / (max - min)) * (H - pad.t - pad.b);

  const path = (key) => series.reduce((acc, s, i) => {
    if (s[key] == null) return acc;
    return acc + (acc ? "L" : "M") + x(i).toFixed(1) + "," + y(s[key]).toFixed(1);
  }, "");

  const ticks = 4;
  let grid = "";
  for (let k = 0; k <= ticks; k++) {
    const v = min + ((max - min) * k) / ticks;
    grid += `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/>`;
    grid += `<text class="axis-text" x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v / 1000)}k</text>`;
  }
  const step = Math.ceil(series.length / 6);
  for (let i = 0; i < series.length; i += step) {
    grid += `<text class="axis-text" x="${x(i)}" y="${H - 6}" text-anchor="middle">${series[i].date.slice(5)}</text>`;
  }

  box.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      ${grid}
      <path class="line-2" d="${path("ma7")}" fill="none" stroke-width="2" stroke-linejoin="round"/>
      <path class="line-1" d="${path("value")}" fill="none" stroke-width="2" stroke-linejoin="round"/>
      <g id="hover" style="display:none">
        <line class="crosshair" y1="${pad.t}" y2="${H - pad.b}"/>
        <circle class="dot" r="5" fill="var(--series-1)"/>
      </g>
      <rect x="${pad.l}" y="0" width="${W - pad.l - pad.r}" height="${H}" fill="transparent" id="hit"/>
    </svg>
    <div class="tooltip" id="tip" hidden></div>`;

  const hover = box.querySelector("#hover"), tip = box.querySelector("#tip");
  const hit = box.querySelector("#hit");
  hit.addEventListener("mousemove", (ev) => {
    const rect = box.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * W;
    const i = Math.max(0, Math.min(series.length - 1, Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (series.length - 1))));
    const s = series[i];
    hover.style.display = "";
    hover.querySelector("line").setAttribute("x1", x(i));
    hover.querySelector("line").setAttribute("x2", x(i));
    hover.querySelector("circle").setAttribute("cx", x(i));
    hover.querySelector("circle").setAttribute("cy", y(s.value));
    tip.hidden = false;
    tip.style.left = (x(i) / W) * rect.width + "px";
    tip.style.top = (y(s.value) / H) * rect.height + "px";
    const ret = s.return_pct == null ? "" : ` (${s.return_pct > 0 ? "+" : ""}${s.return_pct}%)`;
    tip.innerHTML = `${s.date}<br>종가 <b>${usd(s.value)}</b>${ret}<br>7일 평균 <b>${usd(s.ma7)}</b>`;
  });
  hit.addEventListener("mouseleave", () => { hover.style.display = "none"; tip.hidden = true; });
}

// ---------- 탭 · 테마 ----------
function switchTab(name) {
  history.replaceState(null, "", name === "data" ? "#data" : "#");
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.tab === name;
    t.classList.toggle("active", on);
    t.setAttribute("aria-selected", on);
  });
  $("#tab-chat").hidden = name !== "chat";
  $("#tab-data").hidden = name !== "data";
  if (name === "data" && state.data.length) loadStatistics();
}

function currentTheme() {
  return document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch (e) {}
  $("#themeToggle").textContent = next === "dark" ? "☀️" : "🌙";
}

// ---------- 이벤트 연결 ----------
$("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); sendMessage($("#chatInput").value); });
$("#chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage($("#chatInput").value); }
});
$("#chatInput").addEventListener("input", autoGrow);
$("#messages").addEventListener("click", (e) => { if (e.target.classList.contains("chip")) sendMessage(e.target.textContent); });
$("#newChatBtn").addEventListener("click", () => { resetChat(); switchTab("chat"); scrollToChatOnMobile(); $("#chatInput").focus({ preventScroll: true }); });
$("#convList").addEventListener("click", (e) => {
  const del = e.target.closest("[data-del]");
  if (del) return deleteConversation(del.dataset.del);
  const item = e.target.closest(".conv-item");
  if (item) openConversation(item.dataset.id);
});
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
$("#dataForm").addEventListener("submit", submitData);
$("#fCancel").addEventListener("click", cancelEdit);
$("#dataBody").addEventListener("click", (e) => {
  if (e.target.dataset.edit) startEdit(e.target.dataset.edit);
  if (e.target.dataset.remove) removeData(e.target.dataset.remove);
});
$("#exportCsv").addEventListener("click", exportCsv);
$("#exportJson").addEventListener("click", exportJson);
$("#themeToggle").addEventListener("click", toggleTheme);
$("#themeToggle").textContent = currentTheme() === "dark" ? "☀️" : "🌙";
window.addEventListener("resize", () => { if (!$("#tab-data").hidden) loadStatistics(); });

// ---------- 시작 ----------
(async function init() {
  if (location.hash === "#data") switchTab("data");
  if (!(await wakeServer())) return;
  try {
    await Promise.all([loadSummary(), loadConversations(), loadData()]);
  } catch (e) {
    toast("데이터를 불러오지 못했어요: " + e.message);
  }
})();
