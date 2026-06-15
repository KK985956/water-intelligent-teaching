const state = {
  token: "",
  user: null,
  permissions: [],
  runtime: null,
  templates: [],
  resources: [],
  tasks: [],
  roles: [],
  users: [],
  audits: [],
  activeContent: null,
  activeTemplateDetail: null,
  activeStep: "templates",
  availableSteps: [],
  pollingTimer: null,
  socket: null,
  socketMode: "idle",
};

const elements = {};
const TERMINAL_STATUSES = new Set(["SUCCESS", "FAILED", "CANCELED"]);
const STEP_DEFS = [
  {
    id: "templates",
    title: "模板选择",
    short: "选模板",
    subtitle: "先选择理论课、实训课或培训课模板，作为后续生成的结构基础。",
    permission: "templates:read",
  },
  {
    id: "template-admin",
    title: "模板维护",
    short: "维护模板",
    subtitle: "教师和管理员可以上传模板新版本、查看版本历史并执行版本回滚。",
    permission: "templates:write",
  },
  {
    id: "plan",
    title: "教学方案",
    short: "生成方案",
    subtitle: "填写课程名称、课时、授课对象、教学目标和重难点，生成教学方案。",
    permission: "generation:run",
  },
  {
    id: "courseware",
    title: "教学课件",
    short: "生成课件",
    subtitle: "基于已完成的教学方案继续生成课件页面结构和教学要点。",
    permission: "generation:run",
  },
  {
    id: "resources",
    title: "教学资源",
    short: "资源库",
    subtitle: "查看或维护案例、图片、视频、公式和习题资源。",
    permission: "resources:read",
  },
  {
    id: "tasks",
    title: "任务与预览",
    short: "看结果",
    subtitle: "查看生成进度、预览结果、执行校验、导出下载或分享文件。",
    permission: "generation:run",
  },
  {
    id: "editor",
    title: "人工编辑",
    short: "再编辑",
    subtitle: "教师和管理员可以修改生成结果 JSON，并重新生成预览与导出源文件。",
    permission: "content:edit",
  },
  {
    id: "admin",
    title: "系统管理",
    short: "管理",
    subtitle: "仅管理员可见，用于用户管理和关键操作审计追踪。",
    permission: "users:manage",
  },
];

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  bindEvents();
  restoreSession();
  initTheme();
  initSidebarNav();
  fillLoginFromSeed(document.querySelector(".seed-pill.is-active"));
  refreshSessionUI();
  renderTemplates();
  renderResources();
  renderTasks();
  renderTemplateVersionList();
  renderUsers();
  renderAudits();
  if (state.token) {
    guardedAction(loadDashboard);
  }
});

function initTheme() {
  const saved = localStorage.getItem("water-theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeUI(saved);

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("water-theme", next);
    updateThemeUI(next);
  });
}

function updateThemeUI(theme) {
  const icon = document.getElementById("theme-icon");
  const label = document.getElementById("theme-label");
  if (theme === "dark") {
    icon.innerHTML = "&#9788;";
    label.textContent = "浅色模式";
  } else {
    icon.innerHTML = "&#9790;";
    label.textContent = "深色模式";
  }
}

function initSidebarNav() {
  document.getElementById("sidebar-nav").addEventListener("click", (e) => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    const navId = item.dataset.nav;
    setActiveSidebarItem(item);
    showPanelByStep(navId);
    closeSidebarMobile();
  });

  document.getElementById("sidebar-toggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("is-open");
  });

  document.querySelectorAll(".seed-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      const defaultStep = state.availableSteps.length ? state.availableSteps[0].id : "templates";
      setActiveSidebarItem(document.querySelector(`.sidebar-item[data-nav="${defaultStep}"]`));
      closeSidebarMobile();
    });
  });
}

function closeSidebarMobile() {
  if (window.innerWidth <= 820) {
    document.getElementById("sidebar").classList.remove("is-open");
  }
}

function setActiveSidebarItem(item) {
  document.querySelectorAll(".sidebar-item").forEach((el) => el.classList.remove("is-active"));
  if (item) item.classList.add("is-active");
}

function showPanelByStep(stepId) {
  const step = STEP_DEFS.find((s) => s.id === stepId);
  if (step && stepAllowed(step)) {
    state.activeStep = stepId;
    renderStepNav();
    renderVisibleStep();
  }
}

function cacheElements() {
  const ids = [
    "session-status",
    "realtime-status",
    "refresh-dashboard",
    "logout-button",
    "login-form",
    "login-username",
    "login-password",
    "login-captcha",
    "login-submit",
    "toggle-password",
    "login-helper",
    "metrics-strip",
    "role-flow",
    "step-title",
    "step-subtitle",
    "step-nav",
    "step-prev",
    "step-next",
    "workspace-grid",
    "template-filter-form",
    "template-filter-type",
    "template-filter-keyword",
    "template-list",
    "load-templates",
    "template-upload-form",
    "template-upload-name",
    "template-upload-type",
    "template-upload-rules",
    "template-upload-file",
    "template-upload-submit",
    "template-version-form",
    "template-version-target",
    "template-version-name",
    "template-version-log",
    "template-version-rules",
    "template-version-file",
    "template-version-submit",
    "template-version-list",
    "template-version-note",
    "plan-form",
    "plan-template",
    "plan-course-name",
    "plan-hours",
    "plan-audience",
    "plan-goals",
    "plan-focus-points",
    "plan-submit",
    "courseware-form",
    "courseware-plan-id",
    "courseware-template",
    "resource-picks",
    "courseware-submit",
    "exam-form",
    "exam-plan-id",
    "exam-submit",
    "resource-form",
    "resource-type",
    "resource-tags",
    "resource-file",
    "resource-submit",
    "resource-list",
    "load-resources",
    "user-panel-note",
    "user-form",
    "user-username",
    "user-password",
    "user-real-name",
    "user-dept",
    "user-role",
    "user-status",
    "user-submit",
    "user-list",
    "load-users",
    "task-list",
    "load-tasks",
    "export-share-scope",
    "export-expiry-days",
    "export-max-downloads",
    "editor-form",
    "editor-target-type",
    "editor-target-id",
    "editor-content",
    "editor-load",
    "editor-format",
    "editor-save",
    "editor-note",
    "preview-title",
    "preview-frame",
    "audit-list",
    "load-audits",
    "metric-templates",
    "metric-resources",
    "metric-tasks",
    "metric-success",
    "toast-stack",
  ];
  ids.forEach((id) => {
    elements[id] = document.getElementById(id);
  });
}

function bindEvents() {
  elements["login-form"].addEventListener("submit", handleLogin);
  elements["logout-button"].addEventListener("click", () => handleLogout());
  elements["refresh-dashboard"].addEventListener("click", () => guardedAction(loadDashboard));
  elements["step-prev"].addEventListener("click", () => moveStep(-1));
  elements["step-next"].addEventListener("click", () => moveStep(1));
  elements["step-nav"].addEventListener("click", handleStepNavClick);
  elements["load-templates"].addEventListener("click", () => guardedAction(loadTemplates));
  elements["load-resources"].addEventListener("click", () => guardedAction(loadResources));
  elements["load-users"].addEventListener("click", () => guardedAction(loadAdminData));
  elements["load-tasks"].addEventListener("click", () => guardedAction(loadTasks));
  elements["load-audits"].addEventListener("click", () => guardedAction(loadAudits));
  elements["editor-load"].addEventListener("click", () => guardedAction(loadEditorContent));
  elements["editor-format"].addEventListener("click", formatEditorJson);
  elements["editor-form"].addEventListener("submit", handleEditorSave);
  elements["template-filter-form"].addEventListener("submit", (event) => {
    event.preventDefault();
    guardedAction(loadTemplates);
  });
  elements["template-upload-form"].addEventListener("submit", handleTemplateUploadSubmit);
  elements["template-version-target"].addEventListener("change", () => guardedAction(ensureTemplateVersionDetail));
  elements["template-version-form"].addEventListener("submit", handleTemplateVersionSubmit);
  elements["template-version-list"].addEventListener("click", handleTemplateVersionActions);
  elements["plan-form"].addEventListener("submit", handlePlanSubmit);
  elements["courseware-form"].addEventListener("submit", handleCoursewareSubmit);
  elements["exam-form"].addEventListener("submit", handleExamSubmit);
  elements["resource-form"].addEventListener("submit", handleResourceUpload);
  elements["user-form"].addEventListener("submit", handleUserCreate);
  elements["template-list"].addEventListener("click", handleTemplateActions);
  elements["task-list"].addEventListener("click", handleTaskActions);
  elements["user-list"].addEventListener("click", handleUserActions);

  document.querySelectorAll(".seed-pill").forEach((button) => {
    button.addEventListener("click", () => {
      fillLoginFromSeed(button);
    });
  });

  elements["toggle-password"].addEventListener("click", togglePasswordVisibility);
}

function fillLoginFromSeed(button) {
  if (!button) return;
  document.querySelectorAll(".seed-pill").forEach((item) => item.classList.remove("is-active"));
  button.classList.add("is-active");
  elements["login-username"].value = button.dataset.username || "";
  elements["login-password"].value = button.dataset.password || "";
  elements["login-captcha"].value = button.dataset.captcha || "";
  elements["login-helper"].textContent = `已填入${button.querySelector("strong")?.textContent || "演示"}账号，可直接进入工作台。`;
  elements["login-helper"].classList.remove("is-error");
}

function togglePasswordVisibility() {
  const input = elements["login-password"];
  const button = elements["toggle-password"];
  const shouldShow = input.type === "password";
  input.type = shouldShow ? "text" : "password";
  button.textContent = shouldShow ? "隐藏" : "显示";
  button.setAttribute("aria-label", shouldShow ? "隐藏密码" : "显示密码");
  input.focus();
}

function restoreSession() {
  state.token = sessionStorage.getItem("water-token") || "";
  try {
    state.user = JSON.parse(sessionStorage.getItem("water-user") || "null");
  } catch (_error) {
    state.user = null;
  }
}

function persistSession() {
  sessionStorage.setItem("water-token", state.token);
  sessionStorage.setItem("water-user", JSON.stringify(state.user));
}

function clearSession() {
  state.token = "";
  state.user = null;
  state.permissions = [];
  state.runtime = null;
  sessionStorage.removeItem("water-token");
  sessionStorage.removeItem("water-user");
}

function hasPermission(permission) {
  return state.permissions.includes(permission);
}

function hasPanelAccess(node) {
  const permission = node.dataset.permission;
  return !permission || hasPermission(permission);
}

function stepAllowed(step) {
  return !step.permission || hasPermission(step.permission);
}

function refreshWorkflow() {
  const isLoggedIn = Boolean(state.token && state.user);
  elements["role-flow"].classList.toggle("is-locked", !isLoggedIn);
  elements["workspace-grid"].classList.add("step-mode");

  document.querySelectorAll("[data-permission]").forEach((node) => {
    const canAccess = isLoggedIn && hasPanelAccess(node);
    node.classList.toggle("role-hidden", !canAccess);
  });

  state.availableSteps = STEP_DEFS.filter((step) => {
    if (!isLoggedIn || !stepAllowed(step)) return false;
    return Boolean(document.querySelector(`[data-step="${step.id}"]:not(.role-hidden)`));
  });

  if (!state.availableSteps.length) {
    state.activeStep = "";
  } else if (!state.availableSteps.some((step) => step.id === state.activeStep)) {
    state.activeStep = state.availableSteps[0].id;
  }

  document.querySelectorAll(".sidebar-item").forEach((item) => {
    const navId = item.dataset.nav;
    const isAllowed = isLoggedIn && STEP_DEFS.some((s) => s.id === navId && stepAllowed(s));
    const hasPanel = Boolean(document.querySelector(`[data-step="${navId}"]:not(.role-hidden)`));
    item.style.display = isAllowed && hasPanel ? "" : "none";
    if (navId === state.activeStep) {
      item.classList.add("is-active");
    } else {
      item.classList.remove("is-active");
    }
  });

  renderStepNav();
  renderVisibleStep();
}

function renderStepNav() {
  if (!state.availableSteps.length) {
    elements["step-nav"].innerHTML = `<div class="empty-state">登录后会显示当前角色可用的操作步骤。</div>`;
    elements["step-title"].textContent = "按步骤完成教学资料生成";
    elements["step-subtitle"].textContent = "管理员、教师、学生会看到不同的流程入口。";
    elements["step-prev"].disabled = true;
    elements["step-next"].disabled = true;
    return;
  }

  elements["step-nav"].innerHTML = state.availableSteps
    .map(
      (step, index) => `
        <button class="step-tab${step.id === state.activeStep ? " is-active" : ""}" data-step-target="${step.id}" type="button">
          <strong>${String(index + 1).padStart(2, "0")} · ${escapeHtml(step.short)}</strong>
          <span>${escapeHtml(step.title)}</span>
        </button>
      `
    )
    .join("");

  const active = currentStep();
  const index = active ? state.availableSteps.findIndex((step) => step.id === active.id) : -1;
  elements["step-title"].textContent = active ? active.title : "按步骤完成教学资料生成";
  elements["step-subtitle"].textContent = active ? active.subtitle : "请选择一个可用步骤。";
  elements["step-prev"].disabled = index <= 0;
  elements["step-next"].disabled = index < 0 || index >= state.availableSteps.length - 1;
}

function renderVisibleStep() {
  document.querySelectorAll("[data-step]").forEach((panel) => {
    const visible = panel.dataset.step === state.activeStep && !panel.classList.contains("role-hidden");
    panel.classList.toggle("step-hidden", !visible);
  });
}

function currentStep() {
  return state.availableSteps.find((step) => step.id === state.activeStep);
}

function setActiveStep(stepId) {
  if (!state.availableSteps.some((step) => step.id === stepId)) return;
  state.activeStep = stepId;
  renderStepNav();
  renderVisibleStep();
  syncSidebarToStep(stepId);
  elements["role-flow"].scrollIntoView({ behavior: "smooth", block: "start" });
}

function syncSidebarToStep(stepId) {
  const sidebarItem = document.querySelector(`.sidebar-item[data-nav="${stepId}"]`);
  if (sidebarItem) {
    document.querySelectorAll(".sidebar-item").forEach((el) => el.classList.remove("is-active"));
    sidebarItem.classList.add("is-active");
  }
}

function moveStep(direction) {
  const index = state.availableSteps.findIndex((step) => step.id === state.activeStep);
  const next = state.availableSteps[index + direction];
  if (next) setActiveStep(next.id);
}

function handleStepNavClick(event) {
  const button = event.target.closest("[data-step-target]");
  if (!button) return;
  setActiveStep(button.dataset.stepTarget);
}

function refreshSessionUI() {
  const isLoggedIn = Boolean(state.token && state.user);
  document.body.classList.toggle("is-auth-view", !isLoggedIn);
  document.body.classList.toggle("is-workspace-view", isLoggedIn);
  elements["session-status"].textContent = isLoggedIn
    ? `${state.user.realName} · ${state.user.roleCode}`
    : "未登录";
  if (!isLoggedIn) {
    updateRealtimeStatus("idle");
  }
  elements["metrics-strip"].classList.toggle("is-locked", !isLoggedIn);
  elements["workspace-grid"].classList.toggle("is-locked", !isLoggedIn);
  refreshWorkflow();
  setFormDisabled(elements["template-upload-form"], !isLoggedIn || !hasPermission("templates:write"));
  setFormDisabled(elements["template-version-form"], !isLoggedIn || !hasPermission("templates:write"));
  setFormDisabled(elements["user-form"], !isLoggedIn || !hasPermission("users:manage"));
  setFormDisabled(elements["editor-form"], !isLoggedIn || !hasPermission("content:edit"));
  elements["load-users"].disabled = !isLoggedIn || !hasPermission("users:manage");
  elements["load-audits"].disabled = !isLoggedIn || !hasPermission("logs:read");
  elements["editor-load"].disabled = !isLoggedIn;
  elements["editor-format"].disabled = !isLoggedIn;
  elements["editor-save"].disabled = !isLoggedIn || !hasPermission("content:edit");
  elements["user-panel-note"].textContent = !isLoggedIn
    ? "登录后可查看当前角色是否具备管理员能力。"
    : hasPermission("users:manage")
      ? "当前账号具备管理员权限，可直接维护用户。"
      : "当前角色无用户管理权限，切换管理员账号后可操作。";
}

function updateRealtimeStatus(mode) {
  state.socketMode = mode;
  const node = elements["realtime-status"];
  node.classList.remove("status-pill--live", "status-pill--warn");
  if (mode === "connected") {
    node.textContent = "实时通道已连接";
    node.classList.add("status-pill--live");
    return;
  }
  if (mode === "connecting") {
    node.textContent = "实时通道连接中";
    return;
  }
  if (mode === "fallback") {
    node.textContent = "实时通道断开，已回退轮询";
    node.classList.add("status-pill--warn");
    return;
  }
  node.textContent = "实时通道未连接";
}

async function guardedAction(action) {
  if (!state.token) {
    toast("请先登录后再操作。", "warn");
    return;
  }
  try {
    await action();
  } catch (error) {
    handleError(error);
  }
}

async function api(path, options = {}) {
  const config = {
    method: options.method || "GET",
    headers: {},
  };

  if (options.auth !== false && state.token) {
    config.headers.Authorization = `Bearer ${state.token}`;
  }
  if (options.json) {
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(options.json);
  }
  if (options.formData) {
    config.body = options.formData;
  }

  const response = await fetch(path, config);
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = await response.json();
    if (!response.ok || payload.code !== 0) {
      const error = new Error(payload.message || "请求失败");
      error.payload = payload;
      throw error;
    }
    return payload.data;
  }
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response;
}

function handleError(error) {
  const message = error?.payload?.message || error?.message || "发生未知错误";
  if (message.includes("登录凭证") || message.includes("重新登录")) {
    handleLogout({ silent: true });
  }
  toast(message, "error");
}

function toast(message, type = "info") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  elements["toast-stack"].appendChild(node);
  window.setTimeout(() => {
    node.remove();
  }, 3200);
}

async function handleLogin(event) {
  event.preventDefault();
  const submit = elements["login-submit"];
  elements["login-helper"].textContent = "正在校验账号并加载权限...";
  elements["login-helper"].classList.remove("is-error");
  setButtonBusy(submit, true, "登录中...");
  try {
    const data = await api("/api/v1/auth/login", {
      method: "POST",
      auth: false,
      json: {
        username: elements["login-username"].value.trim(),
        password: elements["login-password"].value,
        captcha: elements["login-captcha"].value.trim(),
      },
    });
    state.token = data.token;
    state.user = data.userInfo;
    persistSession();
    refreshSessionUI();
    toast("登录成功，正在加载工作台。", "success");
    await loadDashboard();
  } catch (error) {
    elements["login-helper"].textContent = error?.payload?.message || error?.message || "登录失败，请检查账号、密码或验证码。";
    elements["login-helper"].classList.add("is-error");
    handleError(error);
  } finally {
    setButtonBusy(submit, false, "进入工作台");
  }
}

function handleLogout(options = {}) {
  closeProgressSocket();
  stopPolling();
  clearSession();
  state.templates = [];
  state.resources = [];
  state.tasks = [];
  state.roles = [];
  state.users = [];
  state.audits = [];
  state.activeContent = null;
  state.activeTemplateDetail = null;
  state.activeStep = "templates";
  state.availableSteps = [];
  renderTemplates();
  renderResources();
  renderTasks();
  renderTemplateVersionList();
  renderUsers();
  renderAudits();
  fillTemplateOptions();
  fillCoursewarePlanOptions();
  fillExamPlanOptions();
  fillTemplateVersionOptions();
  fillUserRoleOptions();
  elements["template-upload-form"].reset();
  elements["template-version-form"].reset();
  elements["preview-frame"].srcdoc = "";
  elements["preview-title"].textContent = "选择一个成功任务后查看预览";
  elements["editor-content"].value = "";
  elements["editor-target-id"].value = "";
  elements["editor-note"].textContent = "点击任务卡的“编辑”自动载入内容";
  refreshSessionUI();
  if (!options.silent) {
    toast("已退出登录。", "info");
  }
}

async function loadDashboard() {
  await loadRuntimeContext();
  const jobs = [loadTemplates(), loadResources(), loadTasks()];
  if (hasPermission("users:manage")) {
    jobs.push(loadAdminData());
  } else {
    state.roles = [];
    state.users = [];
    fillUserRoleOptions();
    renderUsers();
  }
  if (hasPermission("logs:read")) {
    jobs.push(loadAudits());
  } else {
    state.audits = [];
    renderAudits();
  }
  await Promise.all(jobs);
  await ensureTemplateVersionDetail();
  connectProgressSocket();
}

async function loadRuntimeContext() {
  const data = await api("/api/v1/runtime/context");
  state.runtime = data;
  state.user = data.currentUser;
  state.permissions = data.permissions || [];
  persistSession();
  refreshSessionUI();
}

async function loadAdminData() {
  if (!hasPermission("users:manage")) {
    state.roles = [];
    state.users = [];
    fillUserRoleOptions();
    renderUsers();
    return;
  }
  const [roles, users] = await Promise.all([api("/api/v1/roles"), api("/api/v1/users?size=50")]);
  state.roles = roles || [];
  state.users = users.list || [];
  fillUserRoleOptions();
  renderUsers();
}

async function loadAudits() {
  if (!hasPermission("logs:read")) {
    state.audits = [];
    renderAudits();
    return;
  }
  const data = await api("/api/v1/audit-logs?size=30");
  state.audits = data.list || [];
  renderAudits();
}

async function loadTemplates() {
  const query = new URLSearchParams();
  const templateType = elements["template-filter-type"].value;
  const keyword = elements["template-filter-keyword"].value.trim();
  if (templateType) query.set("type", templateType);
  if (keyword) query.set("keyword", keyword);
  const data = await api(`/api/v1/templates?${query.toString()}`);
  state.templates = data.list || [];
  renderTemplates();
  fillTemplateOptions();
  fillTemplateVersionOptions();
  updateMetrics();
}

async function loadResources() {
  const data = await api("/api/v1/resources?size=50");
  state.resources = data.list || [];
  renderResources();
  renderResourcePicks();
  updateMetrics();
}

async function loadTasks() {
  state.tasks = await api("/api/v1/tasks?limit=20");
  sortTasks();
  renderTasks();
  fillCoursewarePlanOptions();
  fillExamPlanOptions();
  updateMetrics();
  schedulePolling();
}

function updateMetrics() {
  elements["metric-templates"].textContent = `${state.templates.length}`;
  elements["metric-resources"].textContent = `${state.resources.length}`;
  elements["metric-tasks"].textContent = `${state.tasks.length}`;
  elements["metric-success"].textContent = `${state.tasks.filter((task) => task.status === "SUCCESS").length}`;
}

function renderTemplates() {
  if (!state.templates.length) {
    elements["template-list"].innerHTML = `<div class="empty-state">当前没有匹配的模板。</div>`;
    return;
  }
  elements["template-list"].innerHTML = state.templates
    .map((template) => {
      const manageButton = hasPermission("templates:write")
        ? `<button class="text-button" data-template-action="manage" data-template-id="${template.templateId}" type="button">版本管理</button>`
        : "";
      return `
        <article class="template-card" data-template-type="${escapeHtml(template.templateType)}">
          <h4>${escapeHtml(template.templateName)}</h4>
          <div class="template-meta">
            <span class="chip">${escapeHtml(template.templateType)}</span>
            <span class="chip">v${template.versionNo}</span>
            <span class="chip">${template.placeholders.length} 个占位符</span>
          </div>
          <div class="task-body">${escapeHtml((template.previewText || "").slice(0, 150))}${template.previewText && template.previewText.length > 150 ? "..." : ""}</div>
          <div class="template-actions">
            <button class="text-button" data-template-action="use-plan" data-template-id="${template.templateId}" type="button">用于方案</button>
            <button class="text-button" data-template-action="use-courseware" data-template-id="${template.templateId}" type="button">用于课件</button>
            <button class="text-button" data-template-action="preview" data-template-id="${template.templateId}" type="button">查看详情</button>
            ${manageButton}
          </div>
        </article>
      `;
    })
    .join("");
}

function fillTemplateOptions() {
  const renderOptions = (templates) =>
    templates
      .map(
        (template) =>
          `<option value="${template.templateId}">${escapeHtml(template.templateName)} · ${escapeHtml(template.templateType)}</option>`
      )
      .join("");
  const planTemplates = state.templates.filter(
    (template) => ["THEORY", "PRACTICE", "REVIEW"].includes(template.templateType) && !template.templateId.startsWith("TPL-PPT-")
  );
  const coursewareTemplates = state.templates.filter(
    (template) => template.templateType === "TRAINING" || template.templateId.startsWith("TPL-PPT-")
  );
  const planOptions = renderOptions(planTemplates);
  const coursewareOptions = renderOptions(coursewareTemplates);
  const allOptions = state.templates
    .map(
      (template) =>
        `<option value="${template.templateId}">${escapeHtml(template.templateName)} · ${escapeHtml(template.templateType)}</option>`
    )
    .join("");
  elements["plan-template"].innerHTML = planOptions || allOptions || `<option value="">暂无模板</option>`;
  elements["courseware-template"].innerHTML = coursewareOptions || allOptions || `<option value="">暂无模板</option>`;

  const defaultPlan = planTemplates.find((template) => template.templateType === "THEORY") || planTemplates[0] || state.templates[0];
  if (defaultPlan && !planTemplates.some((item) => item.templateId === elements["plan-template"].value)) {
    elements["plan-template"].value = defaultPlan.templateId;
  }
  const defaultCourseware =
    coursewareTemplates.find((template) => /课件/.test(template.templateName) || template.templateId.startsWith("TPL-PPT-")) ||
    coursewareTemplates[0] ||
    state.templates[0];
  if (defaultCourseware && !coursewareTemplates.some((item) => item.templateId === elements["courseware-template"].value)) {
    elements["courseware-template"].value = defaultCourseware.templateId;
  }
}

function fillTemplateVersionOptions() {
  const select = elements["template-version-target"];
  const currentValue = select.value;
  select.innerHTML = state.templates.length
    ? state.templates
        .map(
          (template) =>
            `<option value="${template.templateId}">${escapeHtml(template.templateName)} · 当前 v${template.versionNo}</option>`
        )
        .join("")
    : `<option value="">暂无模板</option>`;
  if (!state.templates.length) {
    state.activeTemplateDetail = null;
    renderTemplateVersionList();
    return;
  }
  select.value = state.templates.some((template) => template.templateId === currentValue)
    ? currentValue
    : state.templates[0].templateId;
}

async function ensureTemplateVersionDetail() {
  const templateId = elements["template-version-target"].value;
  if (!templateId) {
    state.activeTemplateDetail = null;
    renderTemplateVersionList();
    return;
  }
  state.activeTemplateDetail = await api(`/api/v1/templates/${templateId}`);
  renderTemplateVersionList();
}

function renderTemplateVersionList() {
  const detail = state.activeTemplateDetail;
  if (!detail) {
    elements["template-version-note"].textContent = "选择一个模板后查看版本";
    elements["template-version-list"].innerHTML = `<div class="empty-state">当前没有可展示的模板版本。</div>`;
    return;
  }
  elements["template-version-note"].textContent = `${detail.templateName} · 当前 v${detail.versionNo}`;
  const versions = detail.versionHistory || [];
  if (!versions.length) {
    elements["template-version-list"].innerHTML = `<div class="empty-state">当前模板还没有历史版本。</div>`;
    return;
  }
  elements["template-version-list"].innerHTML = versions
    .map((version) => {
      const rollbackButton = version.isCurrent
        ? ""
        : `<button class="text-button" data-version-action="rollback" data-version-no="${version.versionNo}" type="button">回滚到此版本</button>`;
      return `
        <article class="version-card">
          <div class="template-meta">
            <span class="chip">v${version.versionNo}</span>
            ${version.isCurrent ? `<span class="chip ok">当前版本</span>` : ""}
            <span class="chip">${(version.placeholders || []).length} 个占位符</span>
          </div>
          <div class="task-body">
            <div>名称：${escapeHtml(version.templateName || detail.templateName)}</div>
            <div>时间：${escapeHtml(version.createdAt || "")}</div>
            <div>说明：${escapeHtml(version.changeLog || "未填写")}</div>
          </div>
          <div class="template-actions">${rollbackButton}</div>
        </article>
      `;
    })
    .join("");
}

function renderResources() {
  if (!state.resources.length) {
    elements["resource-list"].innerHTML = `<div class="empty-state">当前还没有上传的教学资源。</div>`;
    return;
  }
  elements["resource-list"].innerHTML = state.resources
    .map(
      (resource) => `
        <article class="resource-card" data-resource-type="${escapeHtml(resource.resourceType)}">
          <h4>${escapeHtml(resource.resourceName)}</h4>
          <div class="resource-meta">
            <span class="chip">${escapeHtml(resource.resourceType)}</span>
            ${(resource.tags || []).map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join("")}
          </div>
          <div class="resource-body">
            <div>上传时间：${escapeHtml(resource.createdAt)}</div>
            <div>资源标识：${escapeHtml(resource.resourceId)}</div>
          </div>
        </article>
      `
    )
    .join("");
}

function renderResourcePicks() {
  if (!state.resources.length) {
    elements["resource-picks"].innerHTML = `<div class="empty-state">暂无资源可引用，先上传一些案例或素材。</div>`;
    return;
  }
  elements["resource-picks"].innerHTML = state.resources
    .map(
      (resource) => `
        <label class="pick-card">
          <input type="checkbox" value="${resource.resourceId}" />
          <div>
            <strong>${escapeHtml(resource.resourceName)}</strong>
            <div class="resource-body">${escapeHtml(resource.resourceType)} · ${(resource.tags || []).map(escapeHtml).join(" / ")}</div>
          </div>
        </label>
      `
    )
    .join("");
}

function renderUsers() {
  if (!hasPermission("users:manage")) {
    elements["user-list"].innerHTML = `<div class="empty-state">当前账号无用户管理权限。</div>`;
    return;
  }
  if (!state.users.length) {
    elements["user-list"].innerHTML = `<div class="empty-state">当前还没有可管理的用户。</div>`;
    return;
  }
  elements["user-list"].innerHTML = state.users
    .map(
      (user) => `
        <article class="user-card" data-user-id="${user.userId}">
          <div class="template-meta">
            <span class="chip">${escapeHtml(user.username)}</span>
            <span class="chip">${escapeHtml(user.roleCode)}</span>
            <span class="chip">${Number(user.status) === 1 ? "启用" : "停用"}</span>
          </div>
          <div class="user-grid">
            <label><span>姓名</span><input class="user-real-name" value="${escapeHtml(user.realName || "")}" /></label>
            <label><span>部门</span><input class="user-dept" value="${escapeHtml(user.dept || "")}" /></label>
            <label><span>角色</span><select class="user-role">${buildRoleOptions(user.roleCode)}</select></label>
            <label><span>状态</span><select class="user-status"><option value="1"${Number(user.status) === 1 ? " selected" : ""}>启用</option><option value="0"${Number(user.status) === 0 ? " selected" : ""}>停用</option></select></label>
            <label class="user-password-field"><span>重置密码</span><input class="user-password-reset" type="password" placeholder="留空则不修改" /></label>
          </div>
          <div class="template-actions"><button class="text-button" data-user-action="save" type="button">保存修改</button></div>
        </article>
      `
    )
    .join("");
}

function renderAudits() {
  if (!hasPermission("logs:read")) {
    elements["audit-list"].innerHTML = `<div class="empty-state">当前角色无审计日志查看权限。</div>`;
    return;
  }
  if (!state.audits.length) {
    elements["audit-list"].innerHTML = `<div class="empty-state">暂无审计日志，完成登录、上传、生成或导出后会出现在这里。</div>`;
    return;
  }
  elements["audit-list"].innerHTML = state.audits
    .map(
      (item) => `
        <article class="audit-card">
          <h4>${escapeHtml(item.action)}</h4>
          <div class="audit-meta">
            <span class="chip">${escapeHtml(item.resultStatus)}</span>
            <span class="chip">${escapeHtml(item.targetType)}</span>
            <span class="chip">${escapeHtml(item.username || `User ${item.userId || "-"}`)}</span>
          </div>
          <div class="audit-body">
            <div>对象：${escapeHtml(item.targetId || "-")}</div>
            <div>详情：${escapeHtml(item.detail || "无补充说明")}</div>
            <div>时间：${escapeHtml(item.createdAt || "")}</div>
          </div>
        </article>
      `
    )
    .join("");
}

function fillUserRoleOptions() {
  elements["user-role"].innerHTML = state.roles.length
    ? state.roles
        .map((role) => `<option value="${role.roleCode}">${escapeHtml(role.roleName)} · ${escapeHtml(role.roleCode)}</option>`)
        .join("")
    : `<option value="">暂无角色</option>`;
}

function buildRoleOptions(selectedRoleCode) {
  if (!state.roles.length) {
    return `<option value="">暂无角色</option>`;
  }
  return state.roles
    .map(
      (role) =>
        `<option value="${role.roleCode}"${role.roleCode === selectedRoleCode ? " selected" : ""}>${escapeHtml(role.roleName)} · ${escapeHtml(role.roleCode)}</option>`
    )
    .join("");
}

function renderTasks() {
  if (!state.tasks.length) {
    elements["task-list"].innerHTML = `<div class="empty-state">还没有生成任务，先创建一个教学方案试试看。</div>`;
    return;
  }
  elements["task-list"].innerHTML = state.tasks.map(renderTaskCard).join("");
}

function renderTaskCard(task) {
  const result = task.result || {};
  const progress = Number(task.progress || 0);
  const warnings = Array.isArray(result.warnings) && result.warnings.length
    ? `<div>模板提醒：${escapeHtml(result.warnings.join("；"))}</div>`
    : "";
  const previewButton =
    task.status === "SUCCESS" && result.previewUrl
      ? `<button class="text-button" data-task-action="preview" data-task-id="${task.taskId}" type="button">预览</button>`
      : "";
  const validateButton =
    hasPermission("validation:run") && task.status === "SUCCESS" && result.targetId
      ? `<button class="text-button" data-task-action="validate" data-task-id="${task.taskId}" type="button">校验</button>`
      : "";
  const editButton =
    hasPermission("content:edit") && task.status === "SUCCESS" && result.targetId
      ? `<button class="text-button" data-task-action="edit" data-task-id="${task.taskId}" type="button">编辑</button>`
      : "";
  const cancelButton =
    !TERMINAL_STATUSES.has(task.status)
      ? `<button class="text-button" data-task-action="cancel" data-task-id="${task.taskId}" type="button">取消</button>`
      : "";
  const retryButton =
    task.status === "FAILED" || task.status === "CANCELED"
      ? `<button class="text-button" data-task-action="retry" data-task-id="${task.taskId}" type="button">重试</button>`
      : "";
  const exportButtons =
    hasPermission("exports:write") && task.status === "SUCCESS" && result.targetId
      ? availableExports(task)
          .map(
            (format) =>
              `<button class="text-button" data-task-action="export" data-task-id="${task.taskId}" data-format="${format}" type="button">导出 ${format.toUpperCase()}</button>`
          )
          .join("")
      : "";
  const exportHint =
    task.taskType === "PLAN" && task.status === "SUCCESS"
      ? `<div class="task-hint">教学方案支持 DOCX、HTML、MD、JSON、PDF。要导出 PPT，请先在“教学课件生成”中选择该方案生成课件。</div>`
      : "";
  return `
    <article class="task-card" data-task-status="${escapeHtml(task.status)}">
      <h4>${escapeHtml(task.taskType === "PLAN" ? "教学方案任务" : task.taskType === "EXAM" ? "试卷生成任务" : "教学课件任务")}</h4>
      <div class="task-meta">
        <span class="chip ${statusTone(task.status)}">${escapeHtml(task.status)}</span>
        <span class="chip">进度 ${progress}%</span>
        <span class="chip">${escapeHtml(task.taskId)}</span>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div>
      <div class="task-body">
        <div>创建时间：${escapeHtml(task.createdAt)}</div>
        <div>模板标识：${escapeHtml(task.templateId)}</div>
        ${result.targetId ? `<div>结果对象：${escapeHtml(result.targetType || "")} · ${escapeHtml(result.targetId)}</div>` : ""}
        ${result.templateMode ? `<div>填充模式：${escapeHtml(result.templateMode)}</div>` : ""}
        ${warnings}
        ${task.errorMessage ? `<div>失败原因：${escapeHtml(task.errorMessage)}</div>` : ""}
        ${exportHint}
      </div>
      <div class="task-actions">${previewButton}${editButton}${validateButton}${cancelButton}${retryButton}${exportButtons}</div>
    </article>
  `;
}

function availableExports(task) {
  if (task.taskType === "PLAN") return ["docx", "html", "md", "json", "pdf"];
  if (task.taskType === "EXAM") return ["html", "md", "json", "txt", "docx", "student_md"];
  return ["pptx", "html", "json", "txt", "pdf"];
}

function fillCoursewarePlanOptions() {
  const planTasks = state.tasks.filter(
    (task) => task.taskType === "PLAN" && task.status === "SUCCESS" && task.result?.targetId
  );
  elements["courseware-plan-id"].innerHTML = planTasks.length
    ? planTasks
        .map(
          (task) =>
            `<option value="${task.result.targetId}">${escapeHtml(task.result.targetId)} · ${escapeHtml(task.params?.courseName || "")}</option>`
        )
        .join("")
    : `<option value="">暂无可用方案，请先生成教学方案</option>`;
}

async function handlePlanSubmit(event) {
  event.preventDefault();
  const button = elements["plan-submit"];
  setButtonBusy(button, true, "生成中...");
  try {
    const task = await api("/api/v1/generation/plans", {
      method: "POST",
      json: {
        templateId: elements["plan-template"].value,
        courseName: elements["plan-course-name"].value.trim(),
        hours: Number(elements["plan-hours"].value || 0),
        audience: elements["plan-audience"].value.trim(),
        goals: linesToList(elements["plan-goals"].value),
        focusPoints: linesToList(elements["plan-focus-points"].value),
      },
    });
    mergeTask(task);
    toast(`已创建方案任务：${task.taskId}`, "success");
    setActiveStep("tasks");
    schedulePolling();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "生成教学方案");
  }
}

async function handleCoursewareSubmit(event) {
  event.preventDefault();
  const button = elements["courseware-submit"];
  setButtonBusy(button, true, "生成中...");
  try {
    const selectedResources = Array.from(elements["resource-picks"].querySelectorAll("input[type='checkbox']:checked")).map(
      (input) => input.value
    );
    const task = await api("/api/v1/generation/coursewares", {
      method: "POST",
      json: {
        planId: elements["courseware-plan-id"].value,
        coursewareTemplateId: elements["courseware-template"].value,
        resources: selectedResources,
      },
    });
    mergeTask(task);
    toast(`已创建课件任务：${task.taskId}`, "success");
    setActiveStep("tasks");
    schedulePolling();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "生成教学课件");
  }
}

async function handleExamSubmit(event) {
  event.preventDefault();
  const button = elements["exam-submit"];
  setButtonBusy(button, true, "生成中...");
  try {
    const task = await api("/api/v1/generation/exams", {
      method: "POST",
      json: {
        planId: elements["exam-plan-id"].value,
      },
    });
    mergeTask(task);
    toast(`已创建试卷任务：${task.taskId}`, "success");
    setActiveStep("tasks");
    schedulePolling();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "生成试卷");
  }
}

function fillExamPlanOptions() {
  const planTasks = state.tasks.filter(
    (task) => task.taskType === "PLAN" && task.status === "SUCCESS" && task.result?.targetId
  );
  elements["exam-plan-id"].innerHTML = planTasks.length
    ? planTasks
        .map(
          (task) =>
            `<option value="${task.result.targetId}">${escapeHtml(task.result.targetId)} · ${escapeHtml(task.params?.courseName || "")}</option>`
        )
        .join("")
    : `<option value="">暂无可用方案，请先生成教学方案</option>`;
}

async function handleResourceUpload(event) {
  event.preventDefault();
  const button = elements["resource-submit"];
  setButtonBusy(button, true, "上传中...");
  try {
    const file = elements["resource-file"].files[0];
    if (!file) {
      throw new Error("请先选择资源文件。");
    }
    const formData = new FormData();
    formData.append("resourceType", elements["resource-type"].value);
    formData.append("tags", elements["resource-tags"].value.trim());
    formData.append("file", file);
    await api("/api/v1/resources/upload", { method: "POST", formData });
    elements["resource-form"].reset();
    toast("资源上传成功。", "success");
    await loadResources();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "上传资源");
  }
}

async function handleTemplateUploadSubmit(event) {
  event.preventDefault();
  const button = elements["template-upload-submit"];
  setButtonBusy(button, true, "上传中...");
  try {
    const file = elements["template-upload-file"].files[0];
    if (!file) {
      throw new Error("请先选择模板文件。");
    }
    const formData = new FormData();
    formData.append("name", elements["template-upload-name"].value.trim());
    formData.append("type", elements["template-upload-type"].value);
    formData.append("file", file);
    if (elements["template-upload-rules"].value.trim()) {
      formData.append("rulesJson", elements["template-upload-rules"].value.trim());
    }
    const detail = await api("/api/v1/templates/upload", { method: "POST", formData });
    elements["template-upload-form"].reset();
    toast("模板上传成功。", "success");
    await loadTemplates();
    elements["template-version-target"].value = detail.templateId;
    state.activeTemplateDetail = detail;
    renderTemplateVersionList();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "上传模板");
  }
}

async function handleTemplateVersionSubmit(event) {
  event.preventDefault();
  const button = elements["template-version-submit"];
  setButtonBusy(button, true, "上传中...");
  try {
    const file = elements["template-version-file"].files[0];
    if (!file) {
      throw new Error("请先选择模板版本文件。");
    }
    const templateId = elements["template-version-target"].value;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("changeLog", elements["template-version-log"].value.trim());
    if (elements["template-version-name"].value.trim()) {
      formData.append("name", elements["template-version-name"].value.trim());
    }
    if (elements["template-version-rules"].value.trim()) {
      formData.append("rulesJson", elements["template-version-rules"].value.trim());
    }
    await api(`/api/v1/templates/${templateId}/versions`, { method: "POST", formData });
    elements["template-version-form"].reset();
    toast("模板新版本上传成功。", "success");
    await loadTemplates();
    elements["template-version-target"].value = templateId;
    await ensureTemplateVersionDetail();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "上传新版本");
  }
}

async function handleTemplateVersionActions(event) {
  const button = event.target.closest("[data-version-action]");
  if (!button || button.dataset.versionAction !== "rollback" || !state.activeTemplateDetail) return;
  try {
    await api(`/api/v1/templates/${state.activeTemplateDetail.templateId}/rollback`, {
      method: "POST",
      json: { versionNo: Number(button.dataset.versionNo) },
    });
    toast(`已回滚到模板 v${button.dataset.versionNo}。`, "success");
    await loadTemplates();
    elements["template-version-target"].value = state.activeTemplateDetail.templateId;
    await ensureTemplateVersionDetail();
  } catch (error) {
    handleError(error);
  }
}

async function handleUserCreate(event) {
  event.preventDefault();
  if (!hasPermission("users:manage")) {
    toast("当前账号无用户管理权限。", "warn");
    return;
  }
  const button = elements["user-submit"];
  setButtonBusy(button, true, "创建中...");
  try {
    await api("/api/v1/users", {
      method: "POST",
      json: {
        username: elements["user-username"].value.trim(),
        password: elements["user-password"].value,
        realName: elements["user-real-name"].value.trim(),
        dept: elements["user-dept"].value.trim(),
        roleCode: elements["user-role"].value,
        status: Number(elements["user-status"].value),
      },
    });
    elements["user-form"].reset();
    fillUserRoleOptions();
    toast("用户创建成功。", "success");
    await loadAdminData();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "创建用户");
  }
}

async function handleUserActions(event) {
  const button = event.target.closest("[data-user-action]");
  if (!button || button.dataset.userAction !== "save") return;
  const card = button.closest("[data-user-id]");
  if (!card) return;
  try {
    await api(`/api/v1/users/${card.dataset.userId}`, {
      method: "PATCH",
      json: {
        realName: card.querySelector(".user-real-name").value.trim(),
        dept: card.querySelector(".user-dept").value.trim(),
        roleCode: card.querySelector(".user-role").value,
        status: Number(card.querySelector(".user-status").value),
        password: card.querySelector(".user-password-reset").value,
      },
    });
    toast("用户信息已更新。", "success");
    await loadAdminData();
  } catch (error) {
    handleError(error);
  }
}

async function handleTemplateActions(event) {
  const button = event.target.closest("[data-template-action]");
  if (!button) return;
  const templateId = button.dataset.templateId;
  if (button.dataset.templateAction === "use-plan") {
    elements["plan-template"].value = templateId;
    setActiveStep("plan");
    toast("已将模板带入教学方案表单。", "info");
    return;
  }
  if (button.dataset.templateAction === "use-courseware") {
    elements["courseware-template"].value = templateId;
    setActiveStep("courseware");
    toast("已将模板带入教学课件表单。", "info");
    return;
  }
  if (button.dataset.templateAction === "manage") {
    elements["template-version-target"].value = templateId;
    await ensureTemplateVersionDetail();
    setActiveStep("template-admin");
    toast("已切换到模板版本管理区。", "info");
    return;
  }
  if (button.dataset.templateAction === "preview") {
    const detail = await api(`/api/v1/templates/${templateId}`);
    state.activeTemplateDetail = detail;
    elements["template-version-target"].value = templateId;
    renderTemplateVersionList();
    elements["preview-frame"].srcdoc = buildTemplatePreview(detail);
    elements["preview-title"].textContent = `${detail.templateName} · 模板详情`;
    setActiveStep("tasks");
  }
}

async function handleTaskActions(event) {
  const button = event.target.closest("[data-task-action]");
  if (!button) return;
  const task = state.tasks.find((item) => item.taskId === button.dataset.taskId);
  if (!task) return;
  if (button.dataset.taskAction === "preview") {
    await openTaskPreview(task);
    return;
  }
  if (button.dataset.taskAction === "validate") {
    await runValidation(task);
    return;
  }
  if (button.dataset.taskAction === "edit") {
    await loadTaskIntoEditor(task);
    return;
  }
  if (button.dataset.taskAction === "cancel") {
    await cancelTask(task);
    return;
  }
  if (button.dataset.taskAction === "retry") {
    await retryTask(task);
    return;
  }
  if (button.dataset.taskAction === "export") {
    await runExport(task, button.dataset.format);
  }
}

async function openTaskPreview(task) {
  const response = await api(task.result.previewUrl, { method: "GET" });
  const html = await response.text();
  elements["preview-frame"].srcdoc = html;
  elements["preview-title"].textContent = `${task.result.targetType} · ${task.result.targetId}`;
  setActiveStep("tasks");
  toast("预览内容已加载。", "info");
}

async function loadTaskIntoEditor(task) {
  if (!task.result?.targetId || !task.result?.targetType) {
    toast("该任务还没有可编辑的结果对象。", "warn");
    return;
  }
  elements["editor-target-type"].value = task.result.targetType;
  elements["editor-target-id"].value = task.result.targetId;
  setActiveStep("editor");
  await loadEditorContent();
}

async function loadEditorContent() {
  const targetType = elements["editor-target-type"].value;
  const targetId = elements["editor-target-id"].value.trim();
  if (!targetId) {
    toast("请先填写结果对象 ID，或点击任务卡的“编辑”。", "warn");
    return;
  }
  const data = await api(`/api/v1/content/${targetType}/${encodeURIComponent(targetId)}`);
  state.activeContent = data;
  elements["editor-content"].value = JSON.stringify(data.content, null, 2);
  elements["editor-note"].textContent = `${data.targetType} · ${data.targetId} 已载入，可编辑后保存`;
}

function formatEditorJson() {
  try {
    const parsed = JSON.parse(elements["editor-content"].value || "{}");
    elements["editor-content"].value = JSON.stringify(parsed, null, 2);
    toast("JSON 已格式化。", "info");
  } catch (error) {
    toast(`JSON 格式不正确：${error.message}`, "error");
  }
}

async function handleEditorSave(event) {
  event.preventDefault();
  const targetType = elements["editor-target-type"].value;
  const targetId = elements["editor-target-id"].value.trim();
  if (!targetId) {
    toast("请先填写结果对象 ID。", "warn");
    return;
  }
  let content;
  try {
    content = JSON.parse(elements["editor-content"].value || "{}");
  } catch (error) {
    toast(`JSON 格式不正确：${error.message}`, "error");
    return;
  }
  const button = elements["editor-save"];
  setButtonBusy(button, true, "保存中...");
  try {
    const data = await api(`/api/v1/content/${targetType}/${encodeURIComponent(targetId)}`, {
      method: "PATCH",
      json: { content },
    });
    state.activeContent = data;
    elements["editor-content"].value = JSON.stringify(data.content, null, 2);
    elements["editor-note"].textContent = `${data.targetType} · ${data.targetId} 已保存并重新生成`;
    toast("内容已保存，预览与导出文件已重新生成。", "success");
    await loadTasks();
    const task = state.tasks.find((item) => item.result?.targetId === data.targetId);
    if (task) await openTaskPreview(task);
    if (hasPermission("logs:read")) {
      await loadAudits();
    }
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "保存并重新生成");
  }
}

async function cancelTask(task) {
  const updated = await api(`/api/v1/tasks/${task.taskId}/cancel`, { method: "POST" });
  mergeTask(updated);
  toast(`任务 ${task.taskId} 已取消。`, "warn");
}

async function retryTask(task) {
  const updated = await api(`/api/v1/tasks/${task.taskId}/retry`, { method: "POST" });
  mergeTask(updated);
  toast(`任务 ${task.taskId} 已重新入队。`, "success");
  schedulePolling();
}

async function runValidation(task) {
  const result = await api("/api/v1/validation/format", {
    method: "POST",
    json: {
      targetId: task.result.targetId,
      targetType: task.result.targetType,
    },
  });
  const issueText = result.issueCount ? `发现 ${result.issueCount} 项提示` : "未发现格式问题";
  toast(`校验完成：${issueText}，得分 ${result.score}`, result.issueCount ? "warn" : "success");
}

async function runExport(task, format) {
  const result = await api("/api/v1/exports", {
    method: "POST",
    json: {
      targetId: task.result.targetId,
      format,
      expiryDays: Number(elements["export-expiry-days"].value || 7),
      shareScope: elements["export-share-scope"].value,
      maxDownloads: Number(elements["export-max-downloads"].value || 0),
    },
  });
  await downloadWithAuth(result.downloadUrl, formatFileName(task, result.actualFormat));
  let copied = false;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${result.shareUrl}`);
      copied = true;
    } catch (_error) {
      copied = false;
    }
  }
  toast(
    copied
      ? `导出成功，已下载 ${result.actualFormat.toUpperCase()} 文件，分享链接也已复制。`
      : `导出成功，已下载 ${result.actualFormat.toUpperCase()} 文件。`,
    "success"
  );
}

async function downloadWithAuth(url, fileName) {
  const response = await api(url, { method: "GET" });
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

function connectProgressSocket() {
  closeProgressSocket();
  const socketConfig = state.runtime?.progressSocket;
  if (!socketConfig?.enabled || !state.token) {
    updateRealtimeStatus("fallback");
    schedulePolling();
    return;
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.hostname || "127.0.0.1";
  const socket = new WebSocket(`${protocol}://${host}:${socketConfig.port}`);
  state.socket = socket;
  updateRealtimeStatus("connecting");
  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({ type: "auth", token: state.token }));
  });
  socket.addEventListener("message", handleSocketMessage);
  socket.addEventListener("close", () => {
    if (state.socket === socket) {
      state.socket = null;
      updateRealtimeStatus("fallback");
      schedulePolling();
    }
  });
  socket.addEventListener("error", () => {
    updateRealtimeStatus("fallback");
  });
}

function closeProgressSocket() {
  if (state.socket) {
    try {
      state.socket.close();
    } catch (_error) {
      // ignore close race
    }
  }
  state.socket = null;
}

function handleSocketMessage(event) {
  try {
    const payload = JSON.parse(event.data);
    if (payload.type === "ready") {
      updateRealtimeStatus("connected");
      stopPolling();
      return;
    }
    if (payload.type === "task.updated" && payload.task) {
      mergeTask(payload.task, true);
      return;
    }
    if (payload.type === "error") {
      updateRealtimeStatus("fallback");
    }
  } catch (_error) {
    updateRealtimeStatus("fallback");
  }
}

function mergeTask(task, notifyTerminal = false) {
  const index = state.tasks.findIndex((item) => item.taskId === task.taskId);
  const previousStatus = index >= 0 ? state.tasks[index].status : "";
  if (index >= 0) {
    state.tasks[index] = task;
  } else {
    state.tasks.unshift(task);
  }
  sortTasks();
  renderTasks();
  fillCoursewarePlanOptions();
  fillExamPlanOptions();
  updateMetrics();
  if (notifyTerminal && previousStatus !== task.status && TERMINAL_STATUSES.has(task.status)) {
    toast(task.status === "SUCCESS" ? `任务 ${task.taskId} 已完成。` : `任务 ${task.taskId} 执行失败。`, task.status === "SUCCESS" ? "success" : "error");
  }
}

function sortTasks() {
  state.tasks.sort((left, right) => String(right.createdAt || "").localeCompare(String(left.createdAt || "")));
}

function formatFileName(task, extension) {
  const courseName = (task.params?.courseName || task.result?.targetId || "export").replace(/[\\/:*?"<>|]/g, "-");
  return `${courseName}.${extension}`;
}

function schedulePolling() {
  stopPolling();
  if (state.socketMode === "connected") return;
  if (!state.tasks.some((task) => !TERMINAL_STATUSES.has(task.status))) return;
  state.pollingTimer = window.setTimeout(async () => {
    try {
      await loadTasks();
    } catch (error) {
      handleError(error);
    }
  }, 2500);
}

function stopPolling() {
  if (state.pollingTimer) {
    window.clearTimeout(state.pollingTimer);
    state.pollingTimer = null;
  }
}

function buildTemplatePreview(detail) {
  const placeholderHtml = (detail.placeholders || []).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("");
  const versionHtml = (detail.versionHistory || [])
    .map(
      (version) =>
        `<li>v${escapeHtml(String(version.versionNo))} · ${escapeHtml(version.changeLog || "未填写说明")} · ${escapeHtml(version.createdAt || "")}${version.isCurrent ? " · 当前版本" : ""}</li>`
    )
    .join("");
  return `<!DOCTYPE html>
  <html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <style>
      body { font-family: "Microsoft YaHei", sans-serif; padding: 28px; color: #163245; background: linear-gradient(145deg, #f4f9fb 0%, #fffdf8 100%); }
      .box { max-width: 920px; margin: 0 auto; background: rgba(255,255,255,.95); border-radius: 28px; padding: 28px; box-shadow: 0 18px 36px rgba(22,49,66,.12); }
      .meta { display: flex; gap: 10px; flex-wrap: wrap; margin: 16px 0; }
      .chip { display: inline-flex; padding: 6px 10px; border-radius: 999px; background: #e7f1f5; color: #0f4f66; font-size: 12px; }
      pre { white-space: pre-wrap; line-height: 1.8; padding: 18px; border-radius: 18px; background: #f3f7f9; border: 1px solid rgba(22,49,66,.08); }
      ul { line-height: 1.8; }
    </style>
  </head>
  <body>
    <main class="box">
      <h1>${escapeHtml(detail.templateName)}</h1>
      <div class="meta"><span class="chip">${escapeHtml(detail.templateType)}</span><span class="chip">v${escapeHtml(String(detail.versionNo))}</span>${placeholderHtml}</div>
      <pre>${escapeHtml(detail.previewText || "暂无模板预览内容。")}</pre>
      <h2>版本历史</h2>
      <ul>${versionHtml || "<li>暂无历史版本</li>"}</ul>
    </main>
  </body>
  </html>`;
}

function linesToList(text) {
  return text
    .split(/\n|；|;/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function setButtonBusy(button, busy, busyText) {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = busyText;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

function setFormDisabled(form, disabled) {
  if (!form) return;
  Array.from(form.querySelectorAll("input, select, textarea, button")).forEach((field) => {
    field.disabled = disabled;
  });
}

function statusTone(status) {
  if (status === "SUCCESS") return "ok";
  if (status === "FAILED" || status === "CANCELED") return "fail";
  if (status === "VALIDATING" || status === "OPTIMIZING") return "warn";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
