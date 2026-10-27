/* Avatition chat window.
 * Add to any page with:  <script src="/widget.js" defer></script>
 * It shows a round icon in the bottom-right corner. Clicking it opens a small chat window.
 * Every answer about flights or companies comes from the server (POST /api/chat).
 * Only the fixed conversation steps (Hello / How can I help you? / Are you satisfied or not? /
 * Please leave us a review!) are written here, because they never depend on the data.
 * Text from the server is always shown as plain text, never as HTML.
 */
(function () {
  "use strict";

  var API = "/api";
  var STORE_KEY = "avatition.chat.v1";
  var MAX_LEN = 500;
  var MAX_KEPT = 60;
  var TIMEOUT_MS = 60000;
  var SUGGESTIONS = [
    "I'm in Mumbai and need to reach Delhi by the morning of 22 October",
    "Who can handle a medical emergency?",
    "Which company has helicopters for a corporate visit?",
    "Cheapest private flight between Delhi and Mumbai"
  ];
  var INTRO = "Welcome to Avatition. Say hi to get started. I can help with private flights between 20 Indian cities and with trusted private aviation companies.";

  // ---------- conversation steps ----------
  // 1. first message      -> "Hello"
  // 2. next message       -> "How can I help you?" (then the answer, if it was a question)
  // 3. thanks / bye       -> "Are you satisfied or not?"
  // 4. yes / satisfied    -> "Please leave us a review!"
  var SAY = {
    hello: "Hello! Welcome to Avatition. It's a pleasure to have you here. I can help you with private flights between 20 Indian cities and with trusted private aviation companies.",
    help: "Thank you for reaching out. How can I help you?",
    askSat: "You're most welcome! It was a pleasure assisting you. Before you go, are you satisfied or not?",
    askSatOk: "Glad I could help! Are you satisfied or not?",
    askSatBye:"Thank you for chatting with Avatition. Before you go, are you satisfied or not?",
    review: "Wonderful, I'm so glad I could help! Please leave us a review! Thank you for choosing Avatition, and have a safe and pleasant journey.",
    sorry: "I'm truly sorry I couldn't help as well as you hoped. Please tell me what went wrong, and I'll do my best to get it right.",
    farewell: "It was a pleasure helping you. Goodbye, and have a wonderful day!",
    helloAgain: "Hello again! It's lovely to hear from you. What can I do for you?",
    howAreYou: "I'm doing very well, thank you for asking! I hope you're having a lovely day too. What can I help you with?",
    whoAreYou: "I'm the Avatition assistant. I can find private flights between 20 Indian cities and suggest trusted private aviation companies, always with sources. Just ask me a question.",
    welcome: "Glad to hear that! Is there anything else I can help you with?",
    sorryUser: "No problem at all, there's nothing to apologise for. How can I help you?"
  };

  function isHowAreYou(text) {
    return /\bhow (are|r) (you|u)\b|\bhow is it going\b|\bhow's it going\b|\bhow do you do\b/.test(words(text).join(" "));
  }

  function isWhoAreYou(text) {
    return /\bwho are you\b|\bwhat can you do\b|\bwhat do you do\b|\bwhat is avatition\b|\bhow can you help\b/.test(words(text).join(" "));
  }

  function isAcknowledgement(text) {
    return /^(ok|okay|okk|k|great|nice|cool|good|awesome|perfect|got it|alright|fine|wow)( (thanks|then|great|nice))?$/.test(words(text).join(" "));
  }

  function isApology(text) {
    return /^(sorry|my bad|oops|apologies)\b/.test(words(text).join(" "));
  }

  function isBye(text) {
    return /\b(bye|goodbye|byee|tata|cya|see you)\b/.test(words(text).join(" "));
  }

  function words(text) {
    return text.toLowerCase().replace(/[^a-z' ]+/g, " ").trim().split(/\s+/).filter(Boolean);
  }

  function isGreeting(text) {
    return /^(hi+|hello+|hey+|helo|hlo|namaste|namaskar|hola|yo|good (morning|afternoon|evening)|greetings)( (there|bot|team|avatition|assistant|sir|madam))?$/
      .test(words(text).join(" "));
  }

  function isThanksOrBye(text) {
    var w = words(text);
    if (!w.length || w.length > 8) return false;
    return /\b(thanks|thank|thankyou|thx|ty|bye|goodbye|byee|tata|cya)\b|that's all|thats all|that is all|no more questions/
      .test(w.join(" "));
  }

  function isYes(text) {
    var s = words(text).join(" ");
    if (/\bnot\b|\bno\b/.test(s)) return false;
    return /^(yes|yeah|yea|yep|yup|ya|haan|ha|sure|ok|okay)\b|\bsatisfied\b|\bhappy\b/.test(s);
  }

  function isNo(text) {
    return /^(no|nope|nah|not)\b|\bnot satisfied\b|\bunsatisfied\b|\bdissatisfied\b/.test(words(text).join(" "));
  }

  // Which step are we on? Worked out from the saved chat, so it survives a page refresh.
  function stage() {
    var said = {};
    var last = null;
    history.forEach(function (m) {
      if (m.role === "bot") { last = m.flow || "answer"; if (m.flow) said[m.flow] = true; }
    });
    if (!said.hello) return "start";
    if (last === "hello") return "greeted";
    if (last === "askSat" || last === "askSatBye" || last === "askSatOk") return "asked";
    return "chatting";
  }

  // ---------- small helpers ----------
  var SVG_NS = "http://www.w3.org/2000/svg";
  var ICONS = {
    plane: { fill: true, d: "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" },
    down: { d: "M6 9l6 6 6-6" },
    reset: { d: "M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" },
    send: { d: "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" },
    company: { d: "M4 21V7l8-4 8 4v14M9 21v-6h6v6M8 10h.01M12 10h.01M16 10h.01" }
  };

  function icon(name) {
    var spec = ICONS[name];
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", spec.d);
    if (spec.fill) {
      p.setAttribute("fill", "currentColor");
    } else {
      p.setAttribute("fill", "none");
      p.setAttribute("stroke", "currentColor");
      p.setAttribute("stroke-width", "2");
      p.setAttribute("stroke-linecap", "round");
      p.setAttribute("stroke-linejoin", "round");
    }
    svg.appendChild(p);
    return svg;
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function safeUrl(url) {
    return typeof url === "string" && /^https?:\/\//i.test(url);
  }

  // ---------- saved history (only in this browser) ----------
  function loadHistory() {
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      var list = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(list)) return [];
      return list.filter(function (m) {
        return m && (m.role === "user" || m.role === "bot") && typeof m.text === "string";
      }).slice(-MAX_KEPT);
    } catch (e) {
      return [];
    }
  }

  function saveHistory(list) {
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify(list.slice(-MAX_KEPT)));
    } catch (e) { /* storage can be blocked; the chat still works */ }
  }

  // ---------- build the window ----------
  var history = loadHistory();
  var pending = false;
  var ui = {};

  function build() {
    var root = el("div", "avt");

    ui.launcher = el("button", "avt-launcher");
    ui.launcher.type = "button";
    ui.launcher.setAttribute("aria-label", "Open the Avatition assistant");
    ui.launcher.setAttribute("aria-expanded", "false");
    ui.launcher.setAttribute("aria-controls", "avt-panel");
    ui.launcher.appendChild(icon("plane"));

    ui.panel = el("section", "avt-panel");
    ui.panel.id = "avt-panel";
    ui.panel.setAttribute("role", "dialog");
    ui.panel.setAttribute("aria-label", "Avatition assistant");
    ui.panel.hidden = true;

    var head = el("header", "avt-head");
    var avatar = el("div", "avt-avatar");
    avatar.appendChild(icon("plane"));
    var titles = el("div", "avt-titles");
    titles.appendChild(el("h2", "avt-title", "Avatition assistant"));
    var status = el("p", "avt-status");
    ui.dot = el("span", "avt-dot");
    ui.statusText = el("span", null, "Checking connection");
    status.appendChild(ui.dot);
    status.appendChild(ui.statusText);
    titles.appendChild(status);

    ui.reset = el("button", "avt-iconbtn");
    ui.reset.type = "button";
    ui.reset.setAttribute("aria-label", "Start a new chat");
    ui.reset.title = "Start a new chat";
    ui.reset.appendChild(icon("reset"));

    ui.close = el("button", "avt-iconbtn");
    ui.close.type = "button";
    ui.close.setAttribute("aria-label", "Close the chat");
    ui.close.title = "Close";
    ui.close.appendChild(icon("down"));

    var wave = document.createElementNS(SVG_NS, "svg");
    wave.setAttribute("class", "avt-wave");
    wave.setAttribute("viewBox", "0 0 400 22");
    wave.setAttribute("preserveAspectRatio", "none");
    wave.setAttribute("aria-hidden", "true");
    var wp = document.createElementNS(SVG_NS, "path");
    wp.setAttribute("d", "M0 12 C 70 24, 140 0, 220 10 S 350 22, 400 6 L400 22 L0 22 Z");
    wave.appendChild(wp);

    head.appendChild(avatar);
    head.appendChild(titles);
    head.appendChild(ui.reset);
    head.appendChild(ui.close);
    head.appendChild(wave);

    ui.log = el("div", "avt-log");
    ui.log.setAttribute("role", "log");
    ui.log.setAttribute("aria-live", "polite");
    ui.log.setAttribute("aria-label", "Conversation");

    ui.form = el("form", "avt-form");
    ui.form.autocomplete = "off";
    ui.input = el("textarea", "avt-input");
    ui.input.rows = 1;
    ui.input.maxLength = MAX_LEN;
    ui.input.placeholder = "Ask about a flight or a company";
    ui.input.setAttribute("aria-label", "Your question");
    ui.send = el("button", "avt-send");
    ui.send.type = "submit";
    ui.send.disabled = true;
    ui.send.setAttribute("aria-label", "Send question");
    ui.send.appendChild(icon("send"));
    ui.count = el("div", "avt-count");
    ui.count.hidden = true;
    ui.form.appendChild(ui.input);
    ui.form.appendChild(ui.send);
    ui.form.appendChild(ui.count);

    ui.panel.appendChild(head);
    ui.panel.appendChild(ui.log);
    ui.panel.appendChild(ui.form);
    root.appendChild(ui.panel);
    root.appendChild(ui.launcher);
    document.body.appendChild(root);

    ui.launcher.addEventListener("click", function () { setOpen(ui.panel.hidden); });
    ui.close.addEventListener("click", function () { setOpen(false); });
    ui.reset.addEventListener("click", newChat);
    ui.panel.addEventListener("keydown", function (e) { if (e.key === "Escape") setOpen(false); });
    ui.form.addEventListener("submit", function (e) { e.preventDefault(); submitFromBox(); });
    ui.input.addEventListener("input", onInput);
    ui.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submitFromBox(); }
    });

    renderAll();
  }

  // ---------- open / close ----------
  function setOpen(open) {
    ui.panel.hidden = !open;
    ui.launcher.setAttribute("aria-expanded", open ? "true" : "false");
    ui.launcher.setAttribute("aria-label", open ? "Close the Avatition assistant" : "Open the Avatition assistant");
    if (open) {
      checkHealth();
      scrollToEnd();
      ui.input.focus();
    } else {
      ui.launcher.focus();
    }
  }

  function checkHealth() {
    fetch(API + "/health", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (h) {
        if (h && h.ok && h.mode === "live") setStatus("good", typeof h.detail === "string" && h.detail ? h.detail.slice(0, 60) : "Online");
        else if (h && h.ok) setStatus("warn", "Search not connected yet");
        else setStatus("bad", "Server problem");
      })
      .catch(function () { setStatus("bad", "Server not reachable"); });
  }

  function setStatus(tone, text) {
    ui.dot.setAttribute("data-tone", tone);
    ui.statusText.textContent = text;
  }

  // ---------- drawing ----------
  function scrollToEnd() { ui.log.scrollTop = ui.log.scrollHeight; }

  // After an answer arrives, show its first line (not the end of its cards).
  function scrollToStartOf(node) {
    var top = node.getBoundingClientRect().top - ui.log.getBoundingClientRect().top + ui.log.scrollTop;
    ui.log.scrollTop = Math.max(0, top - 8);
  }

  function renderAll() {
    ui.log.textContent = "";
    if (!history.length) {                         // the bot greets first, automatically
      history.push({ role: "bot", text: SAY.hello, flow: "hello" });
      saveHistory(history);
    }
    history.forEach(function (m) {
      if (m.role === "user") ui.log.appendChild(userBubble(m.text));
      else ui.log.appendChild(botMessage(m));
    });
    if (stage() === "greeted") ui.log.appendChild(chips());
    scrollToEnd();
  }

  function bubble(text, status) {
    var b = el("div", "avt-bubble", text);
    if (status) b.setAttribute("data-status", status);
    return b;
  }

  function userBubble(text) {
    var wrap = el("div", "avt-msg avt-user");
    wrap.appendChild(bubble(text));
    return wrap;
  }

  function botBubble(text, status) {
    var wrap = el("div", "avt-msg avt-bot");
    wrap.appendChild(bubble(text, status));
    return wrap;
  }

  function botMessage(m) {
    var wrap = botBubble(m.text, m.status);
    (Array.isArray(m.notes) ? m.notes : []).forEach(function (n) { wrap.appendChild(el("p", "avt-note", n)); });
    (Array.isArray(m.results) ? m.results : []).forEach(function (r) { wrap.appendChild(card(r)); });
    return wrap;
  }

  function chips() {
    var box = el("div", "avt-chips");
    SUGGESTIONS.forEach(function (s) {
      var b = el("button", "avt-chip", s);
      b.type = "button";
      b.addEventListener("click", function () { ask(s); });
      box.appendChild(b);
    });
    return box;
  }

  function card(r) {
    var c = el("article", "avt-card");
    var head = el("div", "avt-card-head");
    var kind = el("div", "avt-kind");
    kind.appendChild(icon(r.kind === "flight" ? "plane" : "company"));
    var names = el("div");
    names.appendChild(el("h3", "avt-card-title", r.title || ""));
    if (r.subtitle) names.appendChild(el("p", "avt-card-sub", r.subtitle));
    head.appendChild(kind);
    head.appendChild(names);
    c.appendChild(head);

    if (Array.isArray(r.badges) && r.badges.length) {
      var badges = el("div", "avt-badges");
      r.badges.forEach(function (b) {
        var span = el("span", "avt-badge", b && b.text);
        span.setAttribute("data-tone", b && b.tone ? b.tone : "muted");
        badges.appendChild(span);
      });
      c.appendChild(badges);
    }

    if (Array.isArray(r.facts) && r.facts.length) {
      var dl = el("dl", "avt-facts");
      r.facts.forEach(function (pair) {
        if (!Array.isArray(pair) || pair.length !== 2) return;
        var row = el("div", String(pair[1]).length > 20 ? "avt-wide" : "");
        row.appendChild(el("dt", null, pair[0]));
        row.appendChild(el("dd", null, pair[1]));
        dl.appendChild(row);
      });
      c.appendChild(dl);
    }

    if (r.note) c.appendChild(el("p", "avt-card-note", r.note));

    var links = (Array.isArray(r.sources) ? r.sources : []).filter(function (s) { return s && safeUrl(s.url); });
    if (links.length) {
      var p = el("p", "avt-sources");
      p.appendChild(document.createTextNode("Sources: "));
      links.forEach(function (s, i) {
        if (i) p.appendChild(document.createTextNode(", "));
        var a = el("a", null, s.label || s.url);
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        p.appendChild(a);
      });
      c.appendChild(p);
    }
    return c;
  }

  // ---------- sending ----------
  function onInput() {
    ui.input.style.height = "auto";
    ui.input.style.height = Math.min(ui.input.scrollHeight, 96) + "px";
    var n = ui.input.value.length;
    ui.send.disabled = pending || ui.input.value.trim() === "";
    ui.count.hidden = n <= MAX_LEN - 100;
    ui.count.textContent = n + " / " + MAX_LEN;
  }

  function submitFromBox() {
    var text = ui.input.value.trim();
    if (!text || pending) return;
    ui.input.value = "";
    onInput();
    ask(text);
  }

  function removeChips() {
    var c = ui.log.querySelector(".avt-chips");
    if (c) c.remove();
  }

  // A fixed reply written here (no server call).
  function lastBotFlow() {
    for (var i = history.length - 1; i >= 0; i--) {
      if (history[i].role === "bot") return history[i].flow || "answer";
    }
    return null;
  }

  function say(flow, text) {
    var m = { role: "bot", text: text || SAY[flow], flow: flow };
    history.push(m);
    saveHistory(history);
    ui.log.appendChild(botMessage(m));
    scrollToEnd();
  }

  function ask(text, isRetry) {
    if (pending) return;
    removeChips();
    if (!isRetry) {
      var step = stage();
      history.push({ role: "user", text: text });
      saveHistory(history);
      ui.log.appendChild(userBubble(text));

      var smallTalk = isGreeting(text) || isHowAreYou(text) || isWhoAreYou(text) ||
                      isAcknowledgement(text) || isThanksOrBye(text) || isApology(text);
      if (step === "start") {                      // step 1: "Hello"
        say("hello");
        if (smallTalk) {                           // just a greeting: wait for their question
          ui.log.appendChild(chips());
          scrollToEnd();
          return;
        }
        // a real question in the first message: greet, then answer it below
      } else if (step === "greeted" && smallTalk) { // step 2: "How can I help you?"
        if (isHowAreYou(text)) say("help", "I'm doing very well, thank you for asking! How can I help you?");
        else if (isWhoAreYou(text)) say("help", SAY.whoAreYou.replace("Just ask me a question.", "How can I help you?"));
        else say("help");
        ui.log.appendChild(chips());
        scrollToEnd();
        return;
      } else if (step === "asked") {               // step 4: satisfied?
        if (isYes(text)) { say("review"); return; }
        if (isNo(text)) { say("sorry"); return; }
      }
      if (step === "chatting" || step === "asked") {
        var last = lastBotFlow();
        if (isThanksOrBye(text) || isAcknowledgement(text)) {   // step 3: closing question
          if (last === "review" || last === "farewell") say("farewell");
          else if (isAcknowledgement(text) && !isThanksOrBye(text)) say("askSatOk");
          else say(isBye(text) ? "askSatBye" : "askSat");
          return;
        }
        if (isGreeting(text)) { say("helloAgain"); return; }
        if (isHowAreYou(text)) { say("howAreYou"); return; }
        if (isWhoAreYou(text)) { say("whoAreYou"); return; }
        if (isApology(text) && words(text).length <= 4) { say("sorryUser"); return; }
        if (isAcknowledgement(text)) { say("welcome"); return; }
      }
    }
    pending = true;
    ui.send.disabled = true;
    var typing = el("div", "avt-msg avt-bot");
    var tb = el("div", "avt-bubble");
    tb.setAttribute("role", "status");
    tb.setAttribute("aria-label", "The assistant is typing");
    var dots = el("span", "avt-typing");
    dots.appendChild(el("i")); dots.appendChild(el("i")); dots.appendChild(el("i"));
    tb.appendChild(dots);
    typing.appendChild(tb);
    ui.log.appendChild(typing);
    scrollToEnd();

    var answeredNode = null;
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);

    fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
      signal: ctrl.signal
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) {
          var err = new Error((body && body.error) || "The assistant could not answer.");
          err.retryable = r.status >= 500;
          throw err;
        }
        return body;
      });
    }).then(function (body) {
      typing.remove();
      var m = {
        role: "bot",
        text: typeof body.answer === "string" ? body.answer : "",
        status: body.status,
        results: Array.isArray(body.results) ? body.results : [],
        notes: Array.isArray(body.notes) ? body.notes : []
      };
      history.push(m);
      saveHistory(history);
      var shown = botMessage(m);
      ui.log.appendChild(shown);
      scrollToStartOf(shown);
      answeredNode = shown;
    }).catch(function (err) {
      typing.remove();
      var message = err && err.message && err.name !== "AbortError" && err.name !== "TypeError"
        ? err.message
        : "I'm sorry, I couldn't reach the server just now. Please try again in a moment.";
      var retryable = !err || err.retryable === undefined ? true : err.retryable;
      var wrap = el("div", "avt-msg avt-bot");
      var b = bubble(message);
      b.className += " avt-error";
      wrap.appendChild(b);
      if (retryable) {
        var retry = el("button", "avt-retry", "Try again");
        retry.type = "button";
        retry.addEventListener("click", function () { wrap.remove(); ask(text, true); });
        wrap.appendChild(retry);
      }
      ui.log.appendChild(wrap);
    }).then(function () {
      clearTimeout(timer);
      pending = false;
      onInput();
      if (answeredNode) scrollToStartOf(answeredNode); else scrollToEnd();
      if (!ui.panel.hidden) ui.input.focus();
    });
  }

  function newChat() {
    if (pending) return;
    history = [];
    saveHistory(history);
    renderAll();
    ui.input.focus();
  }

  // ---------- start ----------
  function start() {
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/widget.css";
    var built = false;
    function go() { if (!built) { built = true; build(); } }
    link.addEventListener("load", go);
    link.addEventListener("error", go);
    document.head.appendChild(link);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
