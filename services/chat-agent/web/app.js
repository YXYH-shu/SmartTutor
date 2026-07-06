const state = {
  sessionId: null,
  busy: false,
  panelState: {
    leftCollapsed: false,
    rightCollapsed: false,
  },
};

const PANEL_STORAGE_KEY = "chatagent.panelState";

const scenarios = [
  {
    title: "学生视角：普通问候",
    messages: ["你好，我是学生 ID 40 的学生。你可以帮我学习科学和数学吗？"],
  },
  {
    title: "学生视角：科学问答后学情分析",
    messages: [
      "你好，我是学生 ID 40 的学生。",
      "我最近在学电路，闭合回路为什么才能让小灯泡亮起来？",
      "如果导线断开了，电流为什么就不能继续流动？",
      "请帮我做一个学情分析，看看我现在的学习情况。",
    ],
  },
  {
    title: "教师视角：基于历史提问做学情分析",
    messages: [
      [
        "学生 ID 是 42。该学生最近提出过这些问题：",
        "1. 最近在学电路，想知道为什么闭合回路才能让小灯泡亮起来。",
        "2. 如果导线断开，为什么电流就不能继续流动？",
        "3. 摩擦力什么时候会帮助运动，什么时候会阻碍运动？",
        "4. 植物生长为什么需要阳光？",
        "",
        "请基于这些历史提问，为该学生做一次学情分析。",
      ].join("\n"),
    ],
  },
  {
    title: "学生视角：物理疑问后分析",
    messages: [
      "我是学生 ID 5 的学生。",
      "我不太理解力和运动的关系，为什么物体有时候受力了速度还不一定变快？",
      "摩擦力到底什么时候是帮助运动，什么时候是阻碍运动？",
      "能不能根据我刚才问的问题，分析一下我的学情？",
    ],
  },
  {
    title: "学生视角：先问知识再补 ID",
    messages: [
      "月相为什么会变化？我总是分不清上弦月和下弦月。",
      "我想做一次学情分析。",
      "我的学生 ID 是 5。",
      "请根据刚才的问题帮我分析一下。",
    ],
  },
  {
    title: "学生视角：只问知识不分析",
    messages: [
      "我是学生 ID 40 的学生。",
      "植物生长为什么需要阳光？",
      "如果没有阳光，植物是不是一定会马上死亡？",
    ],
  },
  {
    title: "学生视角：取消分析",
    messages: [
      "我是学生 ID 40 的学生。",
      "我想做一次学情分析。",
      "先取消，我还想再问一个知识点。",
    ],
  },
];

const els = {
  appShell: document.querySelector("#appShell"),
  leftPanel: document.querySelector("#leftPanel"),
  rightPanel: document.querySelector("#rightPanel"),
  leftPanelToggle: document.querySelector("#leftPanelToggle"),
  rightPanelToggle: document.querySelector("#rightPanelToggle"),
  sessionId: document.querySelector("#sessionId"),
  skillsList: document.querySelector("#skillsList"),
  slotsList: document.querySelector("#slotsList"),
  scenarioList: document.querySelector("#scenarioList"),
  messages: document.querySelector("#messages"),
  eventsList: document.querySelector("#eventsList"),
  statusBadge: document.querySelector("#statusBadge"),
  form: document.querySelector("#chatForm"),
  input: document.querySelector("#messageInput"),
  sendBtn: document.querySelector("#sendBtn"),
  sampleBtn: document.querySelector("#sampleBtn"),
  newSessionBtn: document.querySelector("#newSessionBtn"),
};

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return response.json();
}

async function loadSkills() {
  const skills = await requestJson("/api/skills");
  els.skillsList.innerHTML = "";
  for (const skill of skills) {
    const item = document.createElement("div");
    item.className = "skill-item";
    item.innerHTML = `<strong>${escapeHtml(skill.name)}</strong><span>${escapeHtml(skill.description || "")}</span>`;
    els.skillsList.appendChild(item);
  }
}

async function createSession() {
  const payload = await requestJson("/api/sessions", { method: "POST", body: "{}" });
  state.sessionId = payload.session_id;
  renderSession(payload.session);
}

async function sendMessage(message) {
  if (!message || state.busy) return;
  state.busy = true;
  setStatus("running");
  els.sendBtn.disabled = true;
  setScenarioButtonsDisabled(true);

  appendMessage("user", message);
  const assistantNode = appendMessage("assistant", "");
  let assistantText = "";
  let finalSession = null;

  try {
    const response = await fetch(`/api/sessions/${state.sessionId}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `HTTP ${response.status}`);
    }
    if (!response.body) {
      throw new Error("浏览器不支持流式响应。");
    }

    for await (const streamEvent of readSseEvents(response.body)) {
      if (streamEvent.name === "status") {
        setStatus(streamEvent.payload.status || "running");
      } else if (streamEvent.name === "event") {
        appendEvent(streamEvent.payload.event);
      } else if (streamEvent.name === "assistant_delta") {
        assistantText += streamEvent.payload.content || "";
        updateAssistantMessage(assistantNode, assistantText);
      } else if (streamEvent.name === "session") {
        finalSession = streamEvent.payload;
      } else if (streamEvent.name === "done") {
        setStatus(streamEvent.payload.status || "done");
      } else if (streamEvent.name === "error") {
        appendEvent({
          type: "error",
          message: streamEvent.payload.message || "请求失败",
          data: streamEvent.payload,
        });
        throw new Error(streamEvent.payload.message || "请求失败");
      }
    }

    if (finalSession) {
      renderSession(finalSession.session);
      setStatus(finalSession.result.status);
    }
  } catch (error) {
    setStatus("error");
    updateAssistantMessage(assistantNode, `请求失败：${error.message}`);
  } finally {
    state.busy = false;
    els.sendBtn.disabled = false;
    setScenarioButtonsDisabled(false);
    els.input.focus();
  }
}

async function sendScenario(messages) {
  for (const message of messages) {
    await sendMessage(message);
  }
}

function renderSession(session) {
  els.sessionId.textContent = session.session_id;
  renderMessages(session.messages || []);
  renderSlots(session.slots || {}, session.pending_inputs || []);
  renderEvents(session.events || []);
}

function renderMessages(messages) {
  els.messages.innerHTML = "";
  for (const message of messages) {
    appendMessage(message.role, message.content);
  }
  els.messages.scrollTop = els.messages.scrollHeight;
}

function appendMessage(role, content) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  if (role === "assistant") {
    updateAssistantMessage(node, content);
  } else {
    node.textContent = content;
  }
  els.messages.appendChild(node);
  els.messages.scrollTop = els.messages.scrollHeight;
  return node;
}

function updateAssistantMessage(node, content) {
  node.classList.toggle("streaming", !content);
  node.innerHTML = renderMarkdown(content);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderSlots(slots, pendingInputs) {
  els.slotsList.innerHTML = "";
  const entries = Object.entries(slots);
  for (const [key, value] of entries) {
    const row = document.createElement("div");
    row.innerHTML = `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value))}</dd>`;
    els.slotsList.appendChild(row);
  }
  for (const key of pendingInputs) {
    const row = document.createElement("div");
    row.innerHTML = `<dt>${escapeHtml(key)}</dt><dd>pending</dd>`;
    els.slotsList.appendChild(row);
  }
}

function renderEvents(events) {
  els.eventsList.innerHTML = "";
  for (const event of events) {
    appendEvent(event);
  }
}

function appendEvent(event) {
  if (!event) return;
  const item = document.createElement("li");
  item.className = "event-item";
  const detail = renderEventDetails(event);
  item.innerHTML = `<strong>${escapeHtml(event.type)}</strong><span>${escapeHtml(event.message)}</span>${detail}`;
  els.eventsList.appendChild(item);
  els.eventsList.scrollTop = els.eventsList.scrollHeight;
}

function renderScenarios() {
  els.scenarioList.innerHTML = "";
  for (const scenario of scenarios) {
    const card = document.createElement("article");
    card.className = "scenario-item";

    const title = document.createElement("h3");
    title.textContent = scenario.title;
    card.appendChild(title);

    const steps = document.createElement("div");
    steps.className = "scenario-steps";
    scenario.messages.forEach((message, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "scenario-step";
      button.textContent = `${index + 1}. ${message}`;
      button.title = message;
      button.addEventListener("click", async () => {
        await sendMessage(message);
      });
      steps.appendChild(button);
    });
    card.appendChild(steps);

    if (scenario.messages.length > 1) {
      const runButton = document.createElement("button");
      runButton.type = "button";
      runButton.className = "scenario-run";
      runButton.textContent = "连续发送";
      runButton.addEventListener("click", async () => {
        await sendScenario(scenario.messages);
      });
      card.appendChild(runButton);
    }

    els.scenarioList.appendChild(card);
  }
}

function setScenarioButtonsDisabled(disabled) {
  for (const button of els.scenarioList.querySelectorAll("button")) {
    button.disabled = disabled;
  }
}

function renderEventDetails(event) {
  const data = event.data || {};
  const fields = [];
  for (const key of [
    "command",
    "cwd",
    "exit_code",
    "stdout",
    "stderr",
    "status",
    "metrics",
    "raw_result",
    "report_markdown",
    "error",
    "message",
  ]) {
    if (data[key] !== null && data[key] !== undefined && data[key] !== "") {
      fields.push([key, data[key]]);
    }
  }

  if (!fields.length) {
    for (const [key, value] of Object.entries(data)) {
      if (value !== null && value !== undefined && value !== "") fields.push([key, value]);
    }
  }

  return fields
    .map(([key, value]) => {
      const rendered = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
      return `<pre><code>${escapeHtml(`${key}: ${rendered}`)}</code></pre>`;
    })
    .join("");
}

function setStatus(status) {
  els.statusBadge.textContent = status;
}

function isEmbedMode() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("embed") === "1") return true;

  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}

function loadPanelState() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(PANEL_STORAGE_KEY) || "null");
    if (
      saved &&
      typeof saved.leftCollapsed === "boolean" &&
      typeof saved.rightCollapsed === "boolean"
    ) {
      return saved;
    }
  } catch {
    // Ignore localStorage failures; the layout still has a deterministic default.
  }

  const defaultCollapsed = isEmbedMode();
  return {
    leftCollapsed: defaultCollapsed,
    rightCollapsed: defaultCollapsed,
  };
}

function savePanelState() {
  try {
    window.localStorage.setItem(PANEL_STORAGE_KEY, JSON.stringify(state.panelState));
  } catch {
    // Non-critical; private browsing or storage policies may block writes.
  }
}

function applyPanelState({ persist = false } = {}) {
  els.appShell.classList.toggle("left-collapsed", state.panelState.leftCollapsed);
  els.appShell.classList.toggle("right-collapsed", state.panelState.rightCollapsed);
  els.leftPanel.classList.toggle("is-collapsed", state.panelState.leftCollapsed);
  els.rightPanel.classList.toggle("is-collapsed", state.panelState.rightCollapsed);

  els.leftPanelToggle.textContent = state.panelState.leftCollapsed ? "展开测试场景" : "收起测试场景";
  els.rightPanelToggle.textContent = state.panelState.rightCollapsed ? "展开执行过程" : "收起执行过程";
  els.leftPanelToggle.setAttribute("aria-expanded", String(!state.panelState.leftCollapsed));
  els.rightPanelToggle.setAttribute("aria-expanded", String(!state.panelState.rightCollapsed));

  if (persist) savePanelState();
}

function togglePanel(side) {
  if (side === "left") {
    state.panelState.leftCollapsed = !state.panelState.leftCollapsed;
  } else {
    state.panelState.rightCollapsed = !state.panelState.rightCollapsed;
  }
  applyPanelState({ persist: true });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replaceAll("\r\n", "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let inCode = false;
  let codeLines = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listType) return;
    html.push(`<${listType}>${listItems.map((item) => `<li>${renderInline(item)}</li>`).join("")}</${listType}>`);
    listType = null;
    listItems = [];
  };

  const flushBlocks = () => {
    flushParagraph();
    flushList();
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        flushBlocks();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      flushBlocks();
      continue;
    }

    if (isTableStart(lines, index)) {
      flushBlocks();
      const table = collectTable(lines, index);
      html.push(renderTable(table.rows));
      index = table.nextIndex - 1;
      continue;
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushBlocks();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      flushParagraph();
      if (listType !== "ul") flushList();
      listType = "ul";
      listItems.push(unordered[1]);
      continue;
    }

    const ordered = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (ordered) {
      flushParagraph();
      if (listType !== "ol") flushList();
      listType = "ol";
      listItems.push(ordered[1]);
      continue;
    }

    const quote = /^>\s?(.+)$/.exec(trimmed);
    if (quote) {
      flushBlocks();
      html.push(`<blockquote>${renderInline(quote[1])}</blockquote>`);
      continue;
    }

    paragraph.push(trimmed);
  }

  if (inCode) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  flushBlocks();
  return html.join("");
}

function renderInline(value) {
  let html = escapeHtml(value);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  return html;
}

function isTableStart(lines, index) {
  return hasTablePipes(lines[index]) && index + 1 < lines.length && isTableSeparator(lines[index + 1]);
}

function hasTablePipes(line) {
  return line.includes("|");
}

function isTableSeparator(line) {
  const cells = splitTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function collectTable(lines, startIndex) {
  const rows = [splitTableRow(lines[startIndex])];
  let index = startIndex + 2;
  while (index < lines.length && hasTablePipes(lines[index]) && lines[index].trim()) {
    rows.push(splitTableRow(lines[index]));
    index += 1;
  }
  return { rows, nextIndex: index };
}

function renderTable(rows) {
  const [header, ...body] = rows;
  const head = header.map((cell) => `<th>${renderInline(cell)}</th>`).join("");
  const bodyRows = body
    .map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="markdown-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
}

async function* readSseEvents(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const event = parseSseEvent(part);
        if (event) yield event;
      }
    }

    buffer += decoder.decode();
    const event = parseSseEvent(buffer);
    if (event) yield event;
  } finally {
    reader.releaseLock();
  }
}

function parseSseEvent(block) {
  const lines = block.split("\n");
  let name = "message";
  const data = [];

  for (const line of lines) {
    if (line.startsWith("event: ")) {
      name = line.slice("event: ".length);
    } else if (line.startsWith("data: ")) {
      data.push(line.slice("data: ".length));
    }
  }

  if (!data.length) return null;
  return { name, payload: JSON.parse(data.join("\n")) };
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = els.input.value.trim();
  els.input.value = "";
  await sendMessage(message);
});

els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.form.requestSubmit();
  }
});

els.sampleBtn.addEventListener("click", () => {
  els.input.value = scenarios[1].messages[0];
  els.input.focus();
});

els.newSessionBtn.addEventListener("click", async () => {
  await createSession();
  setStatus("ready");
  els.input.focus();
});

els.leftPanelToggle.addEventListener("click", () => togglePanel("left"));
els.rightPanelToggle.addEventListener("click", () => togglePanel("right"));

state.panelState = loadPanelState();
applyPanelState();
renderScenarios();

Promise.all([loadSkills(), createSession()])
  .then(() => setStatus("ready"))
  .catch((error) => {
    setStatus("error");
    appendMessage("assistant", `初始化失败：${error.message}`);
  });
