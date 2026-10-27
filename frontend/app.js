// Avatition frontend. Plain JavaScript, no build step.
// Every value from the server is written with textContent, never innerHTML,
// so company names or descriptions cannot inject markup into the page.

(() => {
  "use strict";

  const TOKEN_KEY = "avatition.token";
  const SESSION_KEY = "avatition.session";

  const CATEGORY_LABEL = {
    charter: "Private jet charter",
    corporate_flight: "Corporate flight department",
    aircraft_management: "Aircraft management",
    operator: "Private aircraft operator",
    broker: "Air charter broker",
    leasing: "Aircraft leasing",
    support: "Aviation support",
    fbo: "FBO / ground handling",
  };

  const AIRCRAFT_LABEL = {
    light_jet: "light jet",
    midsize_jet: "midsize jet",
    large_jet: "large jet",
    helicopter: "helicopter",
    turboprop: "turboprop",
  };

  const $ = (id) => document.getElementById(id);

  const els = {
    authView: $("auth-view"),
    chatView: $("chat-view"),
    authForm: $("auth-form"),
    authSubmit: $("auth-submit"),
    authError: $("auth-error"),
    authTitle: $("auth-title"),
    email: $("email"),
    password: $("password"),
    passwordHint: $("password-hint"),
    tabLogin: $("tab-login"),
    tabRegister: $("tab-register"),
    account: $("account"),
    accountEmail: $("account-email"),
    signOut: $("sign-out"),
    chatForm: $("chat-form"),
    message: $("message"),
    send: $("send"),
    log: $("log"),
    filters: $("filters"),
    modeBadge: $("mode-badge"),
    newChat: $("new-chat"),
    examples: $("examples"),
  };

  let authMode = "login";

  // ── Storage (per-browser convenience only; wrapped in try/catch) ──────────
  function store(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (_) { /* private mode or blocked storage: keep going in memory */ }
  }
  function read(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }
  function readSession(key) {
    try { return sessionStorage.getItem(key); } catch (_) { return null; }
  }
  function writeSession(key, value) {
    try {
      if (value === null) sessionStorage.removeItem(key);
      else sessionStorage.setItem(key, value);
    } catch (_) { /* ignore */ }
  }

  // ── API helper ────────────────────────────────────────────────────────────
  async function api(path, { method = "GET", body } = {}) {
    const headers = { "Accept": "application/json" };
    const token = read(TOKEN_KEY);
    if (token) headers["Authorization"] = "Bearer " + token;
    if (body !== undefined) headers["Content-Type"] = "application/json";

    let response;
    try {
      response = await fetch(path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (_) {
      throw new Error("Cannot reach the server. Check that it is running.");
    }

    let data = {};
    try { data = await response.json(); } catch (_) { /* empty body */ }

    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.";
      const err = new Error(detail);
      err.status = response.status;
      throw err;
    }
    return data;
  }

  // ── Views ─────────────────────────────────────────────────────────────────
  function showAuth() {
    els.chatView.hidden = true;
    els.authView.hidden = false;
    els.account.hidden = true;
    els.authError.hidden = true;
    els.email.focus();
  }

  function showChat(email) {
    els.authView.hidden = true;
    els.chatView.hidden = false;
    els.account.hidden = false;
    els.accountEmail.textContent = email;
    els.message.focus();
  }

  function setAuthMode(next) {
    authMode = next;
    const isLogin = next === "login";
    els.tabLogin.setAttribute("aria-selected", String(isLogin));
    els.tabRegister.setAttribute("aria-selected", String(!isLogin));
    els.tabLogin.classList.toggle("active", isLogin);
    els.tabRegister.classList.toggle("active", !isLogin);
    els.authTitle.textContent = isLogin ? "Sign in" : "Create account";
    els.authSubmit.textContent = isLogin ? "Sign in" : "Create account";
    els.password.autocomplete = isLogin ? "current-password" : "new-password";
    els.passwordHint.hidden = isLogin;
    els.authError.hidden = true;
  }

  // ── Auth ──────────────────────────────────────────────────────────────────
  els.tabLogin.addEventListener("click", () => setAuthMode("login"));
  els.tabRegister.addEventListener("click", () => setAuthMode("register"));

  els.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    els.authError.hidden = true;
    const email = els.email.value.trim();
    const password = els.password.value;
    if (!email || !password) {
      showAuthError("Please enter your email and password.");
      return;
    }

    els.authSubmit.disabled = true;
    try {
      const path = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
      const data = await api(path, { method: "POST", body: { email, password } });
      store(TOKEN_KEY, data.token);
      els.password.value = "";
      showChat(data.email);
      await startChat();
    } catch (err) {
      showAuthError(err.message);
    } finally {
      els.authSubmit.disabled = false;
    }
  });

  function showAuthError(message) {
    els.authError.textContent = message;
    els.authError.hidden = false;
  }

  els.signOut.addEventListener("click", () => {
    store(TOKEN_KEY, null);
    writeSession(SESSION_KEY, null);
    els.log.replaceChildren();
    els.filters.replaceChildren();
    showAuth();
    setAuthMode("login");
  });

  // ── Chat rendering ───────────────────────────────────────────────────────
  function addMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const p = document.createElement("p");
    p.textContent = text;
    wrap.appendChild(p);
    els.log.appendChild(wrap);
    els.log.scrollTop = els.log.scrollHeight;
    return wrap;
  }

  function safeUrl(url) {
    if (typeof url !== "string") return null;
    try {
      const parsed = new URL(url);
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
    } catch (_) {
      return null;
    }
  }

  function renderFilters(criteria) {
    els.filters.replaceChildren();
    if (!criteria) return;
    const tags = [];
    (criteria.categories || []).forEach((c) => tags.push(CATEGORY_LABEL[c] || c));
    if (criteria.city) tags.push("City: " + criteria.city);
    if (criteria.aircraft_class) tags.push("Verified fleet: " + (AIRCRAFT_LABEL[criteria.aircraft_class] || criteria.aircraft_class));
    (criteria.keywords || []).forEach((k) => tags.push("Keyword: " + k));
    tags.forEach((text) => {
      const tag = document.createElement("span");
      tag.className = "filter-tag";
      tag.textContent = text;
      els.filters.appendChild(tag);
    });
  }

  function renderCard(result) {
    const card = document.createElement("article");
    card.className = "card";

    const title = document.createElement("h3");
    title.textContent = result.name;
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "meta";
    const parts = [];
    if (result.hq_city) parts.push(result.hq_city);
    if (result.categories && result.categories.length) parts.push(result.categories.join(", "));
    meta.textContent = parts.join(" · ");
    card.appendChild(meta);

    const verify = document.createElement("div");
    const level = result.verification_status || "unverified";
    verify.className = "verify " + level;
    verify.textContent = "Verification: " + level;
    card.appendChild(verify);

    if (result.summary) {
      const p = document.createElement("p");
      p.textContent = result.summary;
      card.appendChild(p);
    }

    const ul = document.createElement("ul");
    (result.explanation && result.explanation.lines || []).forEach((line) => {
      const li = document.createElement("li");
      li.textContent = line;
      ul.appendChild(li);
    });
    card.appendChild(ul);

    const sources = (result.explanation && result.explanation.sources) || [];
    if (sources.length) {
      const box = document.createElement("div");
      box.className = "sources";
      const label = document.createElement("div");
      label.className = "score";
      label.textContent = "Sources";
      box.appendChild(label);
      sources.forEach((src) => {
        const href = safeUrl(src.url);
        const line = document.createElement("div");
        if (href) {
          const a = document.createElement("a");
          a.href = href;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = src.label || href;
          line.appendChild(a);
        } else {
          line.textContent = src.label || "Source link unavailable";
        }
        box.appendChild(line);
      });
      card.appendChild(box);
    }

    const scores = result.scores || {};
    const score = document.createElement("div");
    score.className = "score";
    score.textContent =
      `Score ${Number(scores.total || 0).toFixed(2)} ` +
      `(keyword ${Number(scores.keyword || 0).toFixed(2)}, ` +
      `similarity ${Number(scores.vector || 0).toFixed(2)}, ` +
      `preference ${Number(scores.preference || 0).toFixed(2)})`;
    card.appendChild(score);

    return card;
  }

  function renderExcluded(count, list) {
    if (!count) return null;
    const details = document.createElement("details");
    details.className = "excluded";
    const summary = document.createElement("summary");
    summary.textContent = `${count} companies did not meet every requirement`;
    details.appendChild(summary);
    const ul = document.createElement("ul");
    (list || []).forEach((item) => {
      const li = document.createElement("li");
      li.textContent = `${item.name}: ${(item.reasons || []).join("; ")}`;
      ul.appendChild(li);
    });
    details.appendChild(ul);
    return details;
  }

  function renderTurn(data) {
    const wrap = addMessage("assistant", data.reply);
    renderFilters(data.criteria);
    (data.results || []).forEach((r) => wrap.appendChild(renderCard(r)));
    const excluded = renderExcluded(data.excluded_count, data.excluded);
    if (excluded) wrap.appendChild(excluded);
    els.log.scrollTop = els.log.scrollHeight;
  }

  function setMode(geminiOn) {
    els.modeBadge.textContent = geminiOn ? "AI mode (Gemini)" : "Direct mode";
  }

  // ── Chat actions ─────────────────────────────────────────────────────────
  async function ask(text) {
    const clean = (text || "").trim();
    if (!clean) return;
    addMessage("user", clean);
    els.message.value = "";
    els.send.disabled = true;

    const working = addMessage("assistant", "Searching verified records…");
    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: { message: clean, session_id: readSession(SESSION_KEY) },
      });
      working.remove();
      writeSession(SESSION_KEY, data.session_id);
      setMode(data.mode === "gemini");
      renderTurn(data);
    } catch (err) {
      working.remove();
      if (err.status === 401) {
        store(TOKEN_KEY, null);
        showAuth();
        showAuthError(err.message);
      } else {
        addMessage("assistant", err.message);
      }
    } finally {
      els.send.disabled = false;
      els.message.focus();
    }
  }

  els.chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    ask(els.message.value);
  });

  els.examples.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.classList && target.classList.contains("chip")) {
      ask(target.textContent);
    }
  });

  els.newChat.addEventListener("click", () => {
    writeSession(SESSION_KEY, null);
    els.log.replaceChildren();
    els.filters.replaceChildren();
    els.message.focus();
  });

  async function loadHistory(sessionId) {
    const data = await api(`/api/chat/${encodeURIComponent(sessionId)}/history`);
    (data.messages || []).forEach((m) => addMessage(m.role === "user" ? "user" : "assistant", m.content));
    if (data.messages && data.messages.length) {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = "Earlier results are not shown again. Ask the question to see them.";
      els.log.appendChild(note);
    }
  }

  async function startChat() {
    try {
      const health = await api("/api/health");
      setMode(Boolean(health.gemini_enabled));
    } catch (_) { /* header badge stays as default */ }

    const sessionId = readSession(SESSION_KEY);
    if (sessionId) {
      try { await loadHistory(sessionId); } catch (_) { writeSession(SESSION_KEY, null); }
    }
  }

  // ── Start up ──────────────────────────────────────────────────────────────
  async function boot() {
    setAuthMode("login");
    if (!read(TOKEN_KEY)) {
      showAuth();
      return;
    }
    try {
      const me = await api("/api/auth/me");
      showChat(me.email);
      await startChat();
    } catch (_) {
      store(TOKEN_KEY, null);
      showAuth();
    }
  }

  boot();
})();
