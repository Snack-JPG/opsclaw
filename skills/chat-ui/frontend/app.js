(function () {
  const DEFAULT_COMPANY_ID = "demo";
  const DEFAULT_HTTP_BASE = "http://localhost:8000";
  const DEFAULT_WS_BASE = "ws://localhost:8765/ws";
  const THEME_KEY = "opsclaw-chat-theme";

  const DEMO_CONFIG = {
    company_id: "demo",
    branding: {
      product_name: "AcmeOps Pulse",
      primary_color: "#14685c",
      secondary_color: "#e8f5f0",
    },
    roles: {
      finance: {
        display_name: "Finance Lead",
        avatar_emoji: "💸",
        description: "Budgets, approvals, reimbursement timing, and spend sanity checks.",
      },
      ops: {
        display_name: "Ops Desk",
        avatar_emoji: "⚙️",
        description: "Escalations, blockers, logistics, scheduling, and internal triage.",
      },
      hr: {
        display_name: "People Partner",
        avatar_emoji: "🫶",
        description: "Policy guidance, onboarding, leave, benefits, and manager comms.",
      },
      admin: {
        display_name: "Admin Coordinator",
        avatar_emoji: "🗂️",
        description: "Facilities, access, procurement, room planning, and office requests.",
      },
    },
    role_list: ["finance", "ops", "hr", "admin"],
  };

  const DEMO_RESPONSES = {
    finance: [
      "Finance read: the request is reasonable, but the cleanest path is bundling it into the next approval run so it clears faster.",
      "Short answer: yes, there is room for that. The thing to watch is timing, not total budget.",
      "I would frame this as an operational unblock with a capped spend range. That usually gets approval with less back-and-forth.",
    ],
    ops: [
      "Ops take: this looks more like a handoff problem than a capacity problem. Fix the queue split before adding people.",
      "I would move the owner closer to the bottleneck. The current delay is happening after intake, not before it.",
      "This is recoverable today. Tighten the checklist, assign a single escalation point, and stop parallel updates in two channels.",
    ],
    hr: [
      "From a people side, I would approve the direction but document the exception clearly so the precedent is controlled.",
      "That message should lead with employee impact, timing, and owner. It will cut most of the follow-up immediately.",
      "Policy-wise this is low risk. The important part is manager alignment before it reaches the wider team.",
    ],
    admin: [
      "Admin answer: yes, that can move quickly if room access and supplies are requested in the same note.",
      "The likely constraint is facilities timing. If you lock the calendar first, the rest becomes straightforward.",
      "I would package this as one coordinated request so front desk, facilities, and procurement are not chasing separate threads.",
    ],
  };

  const app = document.getElementById("app");
  const timeFormatter = new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" });

  const state = {
    companyId: getQueryParam("company_id") || DEFAULT_COMPANY_ID,
    apiBase: getQueryParam("api_base") || DEFAULT_HTTP_BASE,
    theme: localStorage.getItem(THEME_KEY) || "light",
    isDemo: false,
    config: null,
    roles: [],
    roleMap: {},
    employeeName: "",
    token: "",
    session: null,
    activeView: "landing",
    activeRole: "",
    messagesByRole: {},
    typingByRole: {},
    unreadByRole: {},
    socketStatusByRole: {},
    socket: null,
    socketRole: "",
    authPending: false,
    messageDraft: "",
    reconnectTimer: null,
    lastTypingRole: "",
    loadedHistoryByRole: {},
    historyPendingByRole: {},
    sendButtonAnimating: false,
    demoBannerDismissed: false,
  };

  function getQueryParam(key) {
    return new URLSearchParams(window.location.search).get(key);
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function uid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return String(Date.now() + Math.random());
  }

  function normalizeConfig(payload) {
    const config = payload && typeof payload === "object" ? payload : {};
    const rolesSource = config.roles || {};
    const list = Array.isArray(config.role_list) && config.role_list.length
      ? config.role_list
      : Object.keys(rolesSource);
    const roles = list.map(function (roleId) {
      const roleValue = typeof roleId === "string" ? roleId : roleId.role;
      const source = typeof roleId === "object" ? roleId : rolesSource[roleValue] || {};
      const displayName = source.display_name || source.name || roleValue;
      const avatarEmoji = source.avatar_emoji || source.emoji || "✨";
      return {
        id: roleValue,
        display_name: displayName,
        name: displayName,
        avatar_emoji: avatarEmoji,
        emoji: avatarEmoji,
        description: source.description || "Internal role agent.",
      };
    });
    const roleMap = {};
    roles.forEach(function (role) {
      roleMap[role.id] = role;
    });
    return {
      company_id: config.company_id || state.companyId || DEFAULT_COMPANY_ID,
      branding: {
        product_name: (config.branding && config.branding.product_name) || DEMO_CONFIG.branding.product_name,
        primary_color: (config.branding && config.branding.primary_color) || DEMO_CONFIG.branding.primary_color,
        secondary_color: (config.branding && config.branding.secondary_color) || DEMO_CONFIG.branding.secondary_color,
      },
      roles: roleMap,
      role_list: roles.map(function (role) {
        return role.id;
      }),
      ws_base: config.websocket_base_url || DEFAULT_WS_BASE,
    };
  }

  function applyThemeVariables() {
    const branding = (state.config && state.config.branding) || DEMO_CONFIG.branding;
    const root = document.documentElement.style;
    root.setProperty("--primary", branding.primary_color || DEMO_CONFIG.branding.primary_color);
    root.setProperty("--secondary", branding.secondary_color || DEMO_CONFIG.branding.secondary_color);
    root.setProperty("--bg", state.theme === "dark" ? "#09100e" : "#f5f1e8");
    root.setProperty("--text", state.theme === "dark" ? "#edf4f0" : "#13211d");
    document.body.dataset.theme = state.theme;
  }

  function setTheme(theme) {
    state.theme = theme === "dark" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, state.theme);
    applyThemeVariables();
    render();
  }

  function loadDemoConfig(reason) {
    state.isDemo = true;
    state.demoBannerDismissed = false;
    state.config = normalizeConfig(DEMO_CONFIG);
    hydrateRoles();
    seedDemoMessages();
    applyThemeVariables();
    if (reason) {
      console.warn(reason);
    }
  }

  function hydrateRoles() {
    state.roles = state.config.role_list.map(function (roleId) {
      return state.config.roles[roleId];
    });
    state.roleMap = state.config.roles;
    if (!state.activeRole && state.roles.length) {
      state.activeRole = state.roles[0].id;
    }
    state.roles.forEach(function (role) {
      if (!state.messagesByRole[role.id]) {
        state.messagesByRole[role.id] = [];
      }
      if (typeof state.unreadByRole[role.id] !== "number") {
        state.unreadByRole[role.id] = 0;
      }
      if (!state.socketStatusByRole[role.id]) {
        state.socketStatusByRole[role.id] = state.isDemo ? "demo" : "offline";
      }
    });
  }

  function seedDemoMessages() {
    state.roles.forEach(function (role) {
      if (!state.messagesByRole[role.id].length) {
        pushMessage(role.id, {
          author: "agent",
          text: "You’re in demo mode. Ask me anything about " + role.description.toLowerCase(),
          timestamp: nowIso(),
          agentName: role.name,
        });
      }
    });
  }

  async function fetchJson(url, options) {
    const controller = new AbortController();
    const timeout = window.setTimeout(function () {
      controller.abort();
    }, 2800);
    try {
      const response = await fetch(url, Object.assign({}, options, { signal: controller.signal }));
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function bootstrap() {
    applyThemeVariables();
    try {
      const config = await fetchJson(
        state.apiBase + "/api/config?company_id=" + encodeURIComponent(state.companyId)
      );
      state.isDemo = false;
      state.config = normalizeConfig(config);
      hydrateRoles();
      applyThemeVariables();
    } catch (error) {
      loadDemoConfig("Config unavailable, using demo mode.");
    }
    render();
  }

  function getRole(roleId) {
    return state.roleMap[roleId] || {
      id: roleId,
      display_name: roleId,
      name: roleId,
      avatar_emoji: "✨",
      emoji: "✨",
      description: "Internal role agent.",
    };
  }

  function pushMessage(roleId, payload) {
    const list = state.messagesByRole[roleId] || [];
    list.push({
      id: uid(),
      author: payload.author,
      text: payload.text,
      timestamp: payload.timestamp || nowIso(),
      agentName: payload.agentName || getRole(roleId).name,
    });
    state.messagesByRole[roleId] = list;
    if (state.activeRole !== roleId && payload.author === "agent") {
      state.unreadByRole[roleId] = (state.unreadByRole[roleId] || 0) + 1;
    }
  }

  function replaceMessages(roleId, messages) {
    state.messagesByRole[roleId] = messages.map(function (message) {
      return {
        id: message.id || uid(),
        author: message.sender === "user" ? "user" : "agent",
        text: message.text || "",
        timestamp: message.timestamp || nowIso(),
        agentName: message.agent_name || getRole(roleId).name,
      };
    });
  }

  function roleStatusText(roleId) {
    const status = state.socketStatusByRole[roleId];
    if (state.isDemo) {
      return "Demo mode";
    }
    if (status === "connecting") {
      return "Connecting";
    }
    if (status === "online") {
      return "Live";
    }
    return "Offline";
  }

  async function authenticate() {
    if (!state.employeeName.trim() || state.authPending) {
      return;
    }
    state.authPending = true;
    render();
    try {
      if (state.isDemo) {
        state.token = "demo-token";
        state.session = {
          company_id: state.config.company_id,
          employee_name: state.employeeName.trim(),
          session: "demo-session",
        };
      } else {
        const auth = await fetchJson(state.apiBase + "/api/auth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            company_id: state.config.company_id,
            employee_name: state.employeeName.trim(),
          }),
        });
        state.token = auth.token;
        state.session = auth.session;
        if (auth.websocket_base_url) {
          state.config.ws_base = auth.websocket_base_url;
        }
      }
      state.activeView = "chat";
      state.socketStatusByRole[state.activeRole] = state.isDemo ? "demo" : "connecting";
      render();
      if (state.isDemo) {
        scrollMessagesToBottom();
      } else {
        await activateRole(state.activeRole);
      }
    } catch (error) {
      loadDemoConfig("Auth unavailable, switching to demo mode.");
      state.token = "demo-token";
      state.session = {
        company_id: state.config.company_id,
        employee_name: state.employeeName.trim(),
        session: "demo-session",
      };
      state.activeView = "chat";
      render();
      scrollMessagesToBottom();
    } finally {
      state.authPending = false;
      render();
    }
  }

  function closeSocket(manual) {
    window.clearTimeout(state.reconnectTimer);
    if (state.socket) {
      var previousRole = state.socketRole;
      state.socket.__manualClose = !!manual;
      state.socket.close();
      state.socket = null;
      state.socketRole = "";
      if (previousRole && !state.isDemo) {
        state.socketStatusByRole[previousRole] = "offline";
      }
    }
  }

  async function loadHistory(roleId) {
    if (state.isDemo || !state.token || !roleId) {
      return;
    }
    state.historyPendingByRole[roleId] = true;
    render();
    try {
      const history = await fetchJson(
        state.apiBase + "/api/history?role=" + encodeURIComponent(roleId) + "&limit=20",
        {
          headers: {
            Authorization: "Bearer " + state.token,
          },
        }
      );
      replaceMessages(roleId, Array.isArray(history.messages) ? history.messages : []);
      state.loadedHistoryByRole[roleId] = true;
      state.unreadByRole[roleId] = 0;
    } catch (error) {
      console.warn("History unavailable for role", roleId, error);
    } finally {
      state.historyPendingByRole[roleId] = false;
      render();
      scrollMessagesToBottom();
    }
  }

  function wsUrl(roleId) {
    const base = (state.config && state.config.ws_base) || DEFAULT_WS_BASE;
    return base.replace(/\/$/, "") + "/" + encodeURIComponent(roleId) + "?token=" + encodeURIComponent(state.token);
  }

  function connectSocket(roleId) {
    if (state.isDemo || !state.token) {
      return;
    }
    if (state.socketRole === roleId && state.socket && state.socket.readyState < 2) {
      return;
    }
    closeSocket(true);
    state.socketStatusByRole[roleId] = "connecting";
    render();
    const socket = new WebSocket(wsUrl(roleId));
    state.socket = socket;
    state.socketRole = roleId;

    socket.addEventListener("open", function () {
      state.socketStatusByRole[roleId] = "online";
      render();
    });

    socket.addEventListener("message", function (event) {
      try {
        const data = JSON.parse(event.data);
        handleIncoming(roleId, data);
      } catch (error) {
        console.warn("Invalid WebSocket payload", error);
      }
    });

    socket.addEventListener("close", function () {
      const manual = socket.__manualClose;
      if (state.socket === socket) {
        state.socket = null;
        state.socketRole = "";
      }
      state.typingByRole[roleId] = false;
      if (!manual && state.activeView === "chat" && !state.isDemo) {
        state.socketStatusByRole[roleId] = "offline";
        state.reconnectTimer = window.setTimeout(function () {
          connectSocket(roleId);
        }, 1400);
      }
      render();
    });

    socket.addEventListener("error", function () {
      state.socketStatusByRole[roleId] = "offline";
      render();
    });
  }

  function handleIncoming(roleId, payload) {
    if (payload.type === "connected") {
      state.socketStatusByRole[roleId] = "online";
      const welcomeText = payload.text || payload.greeting;
      if (welcomeText && !state.messagesByRole[roleId].length) {
        pushMessage(roleId, {
          author: "agent",
          text: welcomeText,
          timestamp: payload.timestamp || nowIso(),
          agentName: payload.agent_name || getRole(roleId).name,
        });
      }
    }
    if (payload.type === "typing") {
      state.typingByRole[roleId] = true;
      state.lastTypingRole = roleId;
    }
    if (payload.type === "response") {
      state.typingByRole[roleId] = false;
      pushMessage(roleId, {
        author: "agent",
        text: payload.text,
        timestamp: payload.timestamp || nowIso(),
        agentName: payload.agent_name || getRole(roleId).name,
      });
    }
    render();
    scrollMessagesToBottom();
  }

  function simulateDemoReply(roleId) {
    state.typingByRole[roleId] = true;
    render();
    scrollMessagesToBottom();
    const options = DEMO_RESPONSES[roleId] || DEMO_RESPONSES.ops;
    const text = options[Math.floor(Math.random() * options.length)];
    window.setTimeout(function () {
      state.typingByRole[roleId] = false;
      pushMessage(roleId, {
        author: "agent",
        text: text,
        timestamp: nowIso(),
        agentName: getRole(roleId).name,
      });
      render();
      scrollMessagesToBottom();
    }, 1100 + Math.round(Math.random() * 700));
  }

  function sendMessage() {
    const text = state.messageDraft.trim();
    const roleId = state.activeRole;
    if (!text || !roleId) {
      return;
    }
    state.sendButtonAnimating = true;
    window.setTimeout(function () {
      state.sendButtonAnimating = false;
      render();
    }, 150);
    pushMessage(roleId, {
      author: "user",
      text: text,
      timestamp: nowIso(),
    });
    state.messageDraft = "";
    render();
    scrollMessagesToBottom();

    if (state.isDemo || !state.socket || state.socket.readyState !== WebSocket.OPEN || state.socketRole !== roleId) {
      simulateDemoReply(roleId);
      return;
    }

    state.socket.send(
      JSON.stringify({
        type: "message",
        text: text,
        role: roleId,
      })
    );
  }

  async function activateRole(roleId) {
    await loadHistory(roleId);
    connectSocket(roleId);
  }

  function setActiveRole(roleId) {
    state.activeRole = roleId;
    state.unreadByRole[roleId] = 0;
    if (state.activeView === "chat" && !state.isDemo) {
      activateRole(roleId);
    }
    render();
    scrollMessagesToBottom();
  }

  function dismissDemoBanner() {
    state.demoBannerDismissed = true;
    render();
  }

  function connectionIndicatorMarkup(roleId) {
    var isConnected = state.socketStatusByRole[roleId] === "online";
    return '<span class="connection-indicator ' + (isConnected ? "is-connected" : "is-disconnected") + '" aria-hidden="true"></span>';
  }

  function demoBannerMarkup() {
    if (!state.isDemo || state.demoBannerDismissed) {
      return "";
    }
    return (
      '<div class="demo-banner">' +
      '<span>Running in demo mode — start the backend for live chat</span>' +
      '<button class="demo-banner-dismiss" type="button" data-action="dismiss-demo">Dismiss</button>' +
      "</div>"
    );
  }

  function formatTime(timestamp) {
    try {
      return timeFormatter.format(new Date(timestamp));
    } catch (error) {
      return "";
    }
  }

  function initials() {
    return ((state.session && state.session.employee_name) || state.employeeName || "OC")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map(function (part) {
        return part.charAt(0).toUpperCase();
      })
      .join("");
  }

  function landingMarkup() {
    const branding = state.config.branding;
    const activeLandingRole = getRole(state.activeRole);
    return (
      '<main class="screen landing view-transition">' +
      demoBannerMarkup() +
      '<section class="landing">' +
      '<aside class="landing-panel glass">' +
      '<div class="topbar">' +
      brandMarkup(branding.product_name) +
      themeToggleMarkup() +
      "</div>" +
      '<div class="landing-hero">' +
      '<p class="eyebrow">Internal AI Operations Desk</p>' +
      '<h1 class="hero-title">' + escapeHtml(branding.product_name) + " for every team that needs answers fast.</h1>" +
      '<p class="landing-body">A premium white-label chat layer for employees to route questions to role-based AI agents across finance, ops, people, and admin workflows.</p>' +
      '<div class="hero-metrics">' +
      '<div class="metric"><strong>' + state.roles.length + '</strong><span>Role agents live</span></div>' +
      '<div class="metric"><strong>' + (state.isDemo ? "Demo" : "Live") + '</strong><span>Connection mode</span></div>' +
      '<div class="metric"><strong>24/7</strong><span>Internal coverage</span></div>' +
      "</div>" +
      "</div>" +
      '<div class="landing-footer">' +
      '<div><p class="helper">Selected role</p><strong>' + escapeHtml(activeLandingRole.name) + "</strong></div>" +
      '<div class="status-pill"><span class="status-dot"></span><span class="status-copy">' +
      escapeHtml(state.isDemo ? "Backend unreachable. Using AcmeCorp demo." : "Connected to live company config.") +
      "</span></div>" +
      "</div>" +
      "</aside>" +
      '<section class="landing-stage glass">' +
      '<div class="landing-stage-head">' +
      '<div><p class="eyebrow">Choose a role agent</p><h2 class="section-title">Start from the right desk</h2></div>' +
      '<button class="ghost-button" data-action="toggle-theme">' + escapeHtml(state.theme === "dark" ? "Light mode" : "Dark mode") + "</button>" +
      "</div>" +
      '<div class="role-grid">' +
      state.roles.map(function (role) {
        return (
          '<button class="role-card' + (role.id === state.activeRole ? " is-active" : "") + '" data-action="pick-role" data-role="' + escapeHtml(role.id) + '">' +
          '<div class="role-avatar">' + escapeHtml(role.emoji) + "</div>" +
          '<div><h3 class="role-name">' + escapeHtml(role.name) + '</h3><p class="role-copy">' + escapeHtml(role.description) + "</p></div>" +
          '<p class="role-greeting">' + escapeHtml(roleStatusText(role.id)) + " agent</p>" +
          "</button>"
        );
      }).join("") +
      "</div>" +
      '<div class="auth-panel">' +
      '<div><p class="eyebrow">Employee access</p><h3 class="role-name">Enter your name and open chat</h3></div>' +
      '<div class="input-grid">' +
      '<div class="field"><label for="employee-name">Employee name</label><input id="employee-name" name="employee-name" autocomplete="name" placeholder="Jordan Lee" value="' + escapeHtml(state.employeeName) + '" /></div>' +
      '<button class="primary-button" data-action="auth">' + escapeHtml(state.authPending ? "Connecting..." : "Enter workspace") + "</button>" +
      "</div>" +
      '<p class="helper">Company: <strong>' + escapeHtml(state.config.company_id) + "</strong> • WebSocket: <strong>" + escapeHtml(DEFAULT_WS_BASE) + "</strong></p>" +
      "</div>" +
      "</section>" +
      "</section>" +
      "</main>"
    );
  }

  function brandMarkup(name) {
    return (
      '<div class="brand">' +
      '<div class="brand-mark">' + escapeHtml(name.slice(0, 2).toUpperCase()) + "</div>" +
      '<div class="brand-label"><strong>' + escapeHtml(name) + '</strong><div class="helper">White-label employee AI chat</div></div>' +
      "</div>"
    );
  }

  function themeToggleMarkup() {
    return '<button class="theme-toggle" data-action="toggle-theme">' + escapeHtml(state.theme === "dark" ? "Dark" : "Light") + "</button>";
  }

  function chatMarkup() {
    const role = getRole(state.activeRole);
    const messages = state.messagesByRole[state.activeRole] || [];
    return (
      '<main class="screen view-transition">' +
      demoBannerMarkup() +
      '<section class="app-shell">' +
      '<aside class="sidebar glass">' +
      '<div class="topbar">' +
      brandMarkup(state.config.branding.product_name) +
      themeToggleMarkup() +
      "</div>" +
      '<div><p class="eyebrow">Role agents</p><h2 class="section-title">Switch desks</h2></div>' +
      '<div class="sidebar-list">' +
      state.roles.map(function (entry) {
        const unread = state.unreadByRole[entry.id] || 0;
        return (
          '<button class="sidebar-role' + (entry.id === state.activeRole ? " is-active" : "") + '" data-action="pick-role" data-role="' + escapeHtml(entry.id) + '">' +
          '<div class="sidebar-avatar">' + escapeHtml(entry.emoji) + "</div>" +
          '<div class="sidebar-role-meta"><div class="role-name">' + escapeHtml(entry.name) + '</div><p class="role-copy">' + escapeHtml(entry.description) + "</p></div>" +
          (unread ? '<span class="unread-dot" aria-label="Unread messages"></span>' : "") +
          "</button>"
        );
      }).join("") +
      "</div>" +
      '<div class="side-footer">' +
      '<button class="ghost-button" data-action="back">Change employee</button>' +
      '<div class="status-pill"><span class="status-dot"></span><span class="status-copy">' + escapeHtml(state.isDemo ? "Demo conversation engine" : "Live WebSocket transport") + "</span></div>" +
      "</div>" +
      "</aside>" +
      '<section class="chat-shell glass">' +
      '<header class="chat-header">' +
      '<div class="chat-header-main">' +
      '<div class="message-avatar">' + escapeHtml(role.emoji) + "</div>" +
      '<div class="chat-heading"><h1 class="chat-title">' + connectionIndicatorMarkup(role.id) + escapeHtml(role.name) + '</h1><p class="presence">' + escapeHtml(role.description) + " • " + escapeHtml(roleStatusText(role.id)) + "</p></div>" +
      "</div>" +
      '<div class="chat-actions"><button class="ghost-button" data-action="back">Back</button>' + themeToggleMarkup() + "</div>" +
      "</header>" +
      '<section class="messages" id="messages">' +
      (state.historyPendingByRole[state.activeRole] ? '<div class="history-loading">Loading recent history...</div>' : "") +
      (messages.length ? messages.map(function (message) {
        const authorName = message.author === "user"
          ? (state.session && state.session.employee_name) || state.employeeName || "You"
          : message.agentName || role.name;
        return (
          '<article class="message-row ' + message.author + ' is-new">' +
          '<div class="message-avatar">' + escapeHtml(message.author === "user" ? initials() : role.emoji) + "</div>" +
          '<div class="message-body">' +
          '<div class="message-name">' + escapeHtml(authorName) + "</div>" +
          '<div class="message-bubble">' + escapeHtml(message.text) + "</div>" +
          '<div class="message-meta"><span>' + escapeHtml(formatTime(message.timestamp)) + "</span></div>" +
          "</div>" +
          "</article>"
        );
      }).join("") : '<div class="empty-state"><h3>Open the conversation</h3><p class="empty-copy">Send your first message to ' + escapeHtml(role.name) + " and the thread will appear here.</p></div>") +
      (state.typingByRole[state.activeRole]
        ? '<div class="typing-row"><span>' + escapeHtml(role.name) + '</span><div class="typing-dots"><span></span><span></span><span></span></div></div>'
        : "") +
      "</section>" +
      '<form class="composer" id="composer">' +
      '<div class="composer-grid">' +
      '<textarea id="composer-input" placeholder="Ask ' + escapeHtml(role.name) + ' about budgets, blockers, policies, or operations..." rows="1">' + escapeHtml(state.messageDraft) + "</textarea>" +
      '<button class="primary-button send-button' + (state.sendButtonAnimating ? " is-animating" : "") + '" type="submit">Send</button>' +
      "</div>" +
      '<div class="composer-note">Messages send as <code>{type:&quot;message&quot;, text:&quot;...&quot;, role:&quot;' + escapeHtml(role.id) + '&quot;}</code></div>' +
      "</form>" +
      "</section>" +
      "</section>" +
      mobileNavMarkup() +
      "</main>"
    );
  }

  function mobileNavMarkup() {
    return (
      '<nav class="mobile-nav">' +
      state.roles.map(function (role) {
        var unread = state.unreadByRole[role.id] || 0;
        return (
          '<button class="mobile-role-button' + (role.id === state.activeRole ? " is-active" : "") + '" data-action="pick-role" data-role="' + escapeHtml(role.id) + '">' +
          '<span class="emoji-wrap"><span class="emoji">' + escapeHtml(role.emoji) + '</span>' + (unread ? '<span class="unread-dot" aria-hidden="true"></span>' : "") + '</span><span>' + escapeHtml(role.name.split(" ")[0]) + "</span>" +
          "</button>"
        );
      }).join("") +
      "</nav>"
    );
  }

  function render() {
    if (!state.config) {
      app.innerHTML = "";
      return;
    }
    app.innerHTML = state.activeView === "chat" ? chatMarkup() : landingMarkup();
    bindEvents();
  }

  function bindEvents() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-action='toggle-theme']"), function (button) {
      button.onclick = function () {
        setTheme(state.theme === "dark" ? "light" : "dark");
      };
    });

    Array.prototype.forEach.call(document.querySelectorAll("[data-action='pick-role']"), function (button) {
      button.onclick = function () {
        setActiveRole(button.getAttribute("data-role"));
      };
    });

    Array.prototype.forEach.call(document.querySelectorAll("[data-action='auth']"), function (button) {
      button.onclick = function () {
        const input = document.getElementById("employee-name");
        state.employeeName = input ? input.value : state.employeeName;
        authenticate();
      };
    });

    Array.prototype.forEach.call(document.querySelectorAll("[data-action='back']"), function (button) {
      button.onclick = function () {
        closeSocket(true);
        state.activeView = "landing";
        state.typingByRole = {};
        render();
      };
    });

    Array.prototype.forEach.call(document.querySelectorAll("[data-action='dismiss-demo']"), function (button) {
      button.onclick = function () {
        dismissDemoBanner();
      };
    });

    var nameInput = document.getElementById("employee-name");
    if (nameInput) {
      nameInput.oninput = function () {
        state.employeeName = nameInput.value;
      };
      nameInput.onkeydown = function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          state.employeeName = nameInput.value;
          authenticate();
        }
      };
      nameInput.focus();
    }

    var composer = document.getElementById("composer");
    var composerInput = document.getElementById("composer-input");
    if (composer && composerInput) {
      composerInput.oninput = function () {
        state.messageDraft = composerInput.value;
      };
      composer.addEventListener("submit", function (event) {
        event.preventDefault();
        state.messageDraft = composerInput.value;
        sendMessage();
      });
      composerInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          state.messageDraft = composerInput.value;
          sendMessage();
        }
      });
      composerInput.focus();
    }
  }

  function scrollMessagesToBottom() {
    window.requestAnimationFrame(function () {
      var container = document.getElementById("messages");
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    });
  }

  window.addEventListener("beforeunload", function () {
    closeSocket(true);
  });

  bootstrap();
})();
