const state = {
  token: "",
  user: null,
  templates: [],
  resources: [],
  tasks: [],
  pollingTimer: null,
};

const elements = {};
const TERMINAL_STATUSES = new Set(["SUCCESS", "FAILED", "CANCELED"]);

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  bindEvents();
  restoreSession();
  refreshSessionUI();
  if (state.token) {
    loadDashboard();
  }
});

function cacheElements() {
  const ids = [
    "session-status",
    "refresh-dashboard",
    "logout-button",
    "login-form",
    "login-username",
    "login-password",
    "login-captcha",
    "login-submit",
    "metrics-strip",
    "workspace-grid",
    "template-filter-form",
    "template-filter-type",
    "template-filter-keyword",
    "template-list",
    "load-templates",
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
    "resource-form",
    "resource-type",
    "resource-tags",
    "resource-file",
    "resource-submit",
    "resource-list",
    "load-resources",
    "task-list",
    "load-tasks",
    "preview-title",
    "preview-frame",
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
  elements["logout-button"].addEventListener("click", handleLogout);
  elements["refresh-dashboard"].addEventListener("click", () => guardedAction(loadDashboard));
  elements["load-templates"].addEventListener("click", () => guardedAction(loadTemplates));
  elements["load-resources"].addEventListener("click", () => guardedAction(loadResources));
  elements["load-tasks"].addEventListener("click", () => guardedAction(loadTasks));
  elements["template-filter-form"].addEventListener("submit", (event) => {
    event.preventDefault();
    guardedAction(loadTemplates);
  });
  elements["plan-form"].addEventListener("submit", handlePlanSubmit);
  elements["courseware-form"].addEventListener("submit", handleCoursewareSubmit);
  elements["resource-form"].addEventListener("submit", handleResourceUpload);
  elements["template-list"].addEventListener("click", handleTemplateActions);
  elements["task-list"].addEventListener("click", handleTaskActions);

  document.querySelectorAll(".seed-pill").forEach((button) => {
    button.addEventListener("click", () => {
      elements["login-username"].value = button.dataset.username || "";
      elements["login-password"].value = button.dataset.password || "";
      elements["login-captcha"].value = button.dataset.captcha || "";
    });
  });
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
  sessionStorage.removeItem("water-token");
  sessionStorage.removeItem("water-user");
}

function refreshSessionUI() {
  const isLoggedIn = Boolean(state.token && state.user);
  elements["session-status"].textContent = isLoggedIn
    ? `${state.user.realName} · ${state.user.roleCode}`
    : "未登录";
  elements["metrics-strip"].classList.toggle("is-locked", !isLoggedIn);
  elements["workspace-grid"].classList.toggle("is-locked", !isLoggedIn);
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
    clearSession();
    refreshSessionUI();
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
    handleError(error);
  } finally {
    setButtonBusy(submit, false, "进入工作台");
  }
}

function handleLogout() {
  clearSession();
  state.templates = [];
  state.resources = [];
  state.tasks = [];
  stopPolling();
  renderTemplates();
  renderResources();
  renderTasks();
  fillTemplateOptions();
  fillCoursewarePlanOptions();
  elements["preview-frame"].srcdoc = "";
  elements["preview-title"].textContent = "选择一个成功任务后查看预览";
  refreshSessionUI();
  toast("已退出登录。", "info");
}

async function loadDashboard() {
  await Promise.all([loadTemplates(), loadResources(), loadTasks()]);
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
  renderTasks();
  fillCoursewarePlanOptions();
  updateMetrics();
  schedulePolling();
}

function updateMetrics() {
  elements["metric-templates"].textContent = `${state.templates.length}`;
  elements["metric-resources"].textContent = `${state.resources.length}`;
  elements["metric-tasks"].textContent = `${state.tasks.length}`;
  const successCount = state.tasks.filter((task) => task.status === "SUCCESS").length;
  elements["metric-success"].textContent = `${successCount}`;
}

function renderTemplates() {
  if (!state.templates.length) {
    elements["template-list"].innerHTML = `<div class="empty-state">当前没有匹配的模板。</div>`;
    return;
  }
  elements["template-list"].innerHTML = state.templates
    .map((template) => {
      const previewText = escapeHtml((template.previewText || "").slice(0, 160));
      return `
        <article class="template-card">
          <h4>${escapeHtml(template.templateName)}</h4>
          <div class="template-meta">
            <span class="chip">${escapeHtml(template.templateType)}</span>
            <span class="chip">v${template.versionNo}</span>
            <span class="chip">${template.placeholders.length} 个占位符</span>
          </div>
          <div class="task-body">${previewText || "该模板暂无预览文本。"}${template.previewText && template.previewText.length > 160 ? "..." : ""}</div>
          <div class="template-actions">
            <button class="text-button" data-template-action="use-plan" data-template-id="${template.templateId}" type="button">用于方案</button>
            <button class="text-button" data-template-action="use-courseware" data-template-id="${template.templateId}" type="button">用于课件</button>
            <button class="text-button" data-template-action="preview" data-template-id="${template.templateId}" type="button">查看详情</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function fillTemplateOptions() {
  const templateOptions = state.templates
    .map(
      (template) =>
        `<option value="${template.templateId}">${escapeHtml(template.templateName)} · ${escapeHtml(
          template.templateType
        )}</option>`
    )
    .join("");

  elements["plan-template"].innerHTML = templateOptions || `<option value="">暂无模板</option>`;
  elements["courseware-template"].innerHTML = templateOptions || `<option value="">暂无模板</option>`;

  if (!elements["plan-template"].value && state.templates[0]) {
    elements["plan-template"].value = state.templates[0].templateId;
  }

  const coursewareDefault =
    state.templates.find((template) => /课件/.test(template.templateName)) || state.templates[0];
  if (!elements["courseware-template"].value && coursewareDefault) {
    elements["courseware-template"].value = coursewareDefault.templateId;
  }
}

function renderResources() {
  if (!state.resources.length) {
    elements["resource-list"].innerHTML = `<div class="empty-state">当前还没有上传的教学资源。</div>`;
    return;
  }
  elements["resource-list"].innerHTML = state.resources
    .map(
      (resource) => `
        <article class="resource-card">
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
    elements["resource-picks"].innerHTML = `<div class="empty-state">暂无资源可引用，先在左侧上传。</div>`;
    return;
  }
  elements["resource-picks"].innerHTML = state.resources
    .map(
      (resource) => `
        <label class="pick-card">
          <input type="checkbox" value="${resource.resourceId}" />
          <div>
            <strong>${escapeHtml(resource.resourceName)}</strong>
            <div class="resource-body">${escapeHtml(resource.resourceType)} · ${(resource.tags || [])
              .map(escapeHtml)
              .join(" / ")}</div>
          </div>
        </label>
      `
    )
    .join("");
}

function renderTasks() {
  if (!state.tasks.length) {
    elements["task-list"].innerHTML = `<div class="empty-state">还没有生成任务，先创建一个教学方案试试。</div>`;
    return;
  }
  elements["task-list"].innerHTML = state.tasks.map(renderTaskCard).join("");
}

function renderTaskCard(task) {
  const result = task.result || {};
  const statusClass = statusTone(task.status);
  const progress = Number(task.progress || 0);
  const previewButton =
    task.status === "SUCCESS" && result.previewUrl
      ? `<button class="text-button" data-task-action="preview" data-task-id="${task.taskId}" type="button">预览</button>`
      : "";
  const validateButton =
    task.status === "SUCCESS" && result.targetId
      ? `<button class="text-button" data-task-action="validate" data-task-id="${task.taskId}" type="button">校验</button>`
      : "";
  const exportButtons =
    task.status === "SUCCESS" && result.targetId
      ? availableExports(task)
          .map(
            (format) =>
              `<button class="text-button" data-task-action="export" data-task-id="${task.taskId}" data-format="${format}" type="button">导出 ${format.toUpperCase()}</button>`
          )
          .join("")
      : "";

  return `
    <article class="task-card">
      <h4>${escapeHtml(task.taskType === "PLAN" ? "教学方案任务" : "教学课件任务")}</h4>
      <div class="task-meta">
        <span class="chip ${statusClass}">${escapeHtml(task.status)}</span>
        <span class="chip">进度 ${progress}%</span>
        <span class="chip">任务号 ${escapeHtml(task.taskId)}</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" style="width:${progress}%"></div>
      </div>
      <div class="task-body">
        <div>创建时间：${escapeHtml(task.createdAt)}</div>
        <div>模板标识：${escapeHtml(task.templateId)}</div>
        ${
          result.targetId
            ? `<div>结果对象：${escapeHtml(result.targetType || "")} · ${escapeHtml(result.targetId)}</div>`
            : ""
        }
        ${task.errorMessage ? `<div>失败原因：${escapeHtml(task.errorMessage)}</div>` : ""}
      </div>
      <div class="task-actions">
        ${previewButton}
        ${validateButton}
        ${exportButtons}
      </div>
    </article>
  `;
}

function availableExports(task) {
  if (task.taskType === "PLAN") {
    return ["docx", "html", "md", "json", "pdf"];
  }
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
            `<option value="${task.result.targetId}">${escapeHtml(
              task.result.targetId
            )} · ${escapeHtml(task.params?.courseName || "")}</option>`
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
    toast(`已创建方案任务：${task.taskId}`, "success");
    await loadTasks();
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
    const selectedResources = Array.from(
      elements["resource-picks"].querySelectorAll("input[type='checkbox']:checked")
    ).map((input) => input.value);
    const task = await api("/api/v1/generation/coursewares", {
      method: "POST",
      json: {
        planId: elements["courseware-plan-id"].value,
        coursewareTemplateId: elements["courseware-template"].value,
        resources: selectedResources,
      },
    });
    toast(`已创建课件任务：${task.taskId}`, "success");
    await loadTasks();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "生成教学课件");
  }
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
    await api("/api/v1/resources/upload", {
      method: "POST",
      formData,
    });
    elements["resource-form"].reset();
    toast("资源上传成功。", "success");
    await loadResources();
  } catch (error) {
    handleError(error);
  } finally {
    setButtonBusy(button, false, "上传资源");
  }
}

async function handleTemplateActions(event) {
  const button = event.target.closest("[data-template-action]");
  if (!button) return;
  if (!state.token) {
    toast("请先登录后再操作。", "warn");
    return;
  }
  const templateId = button.dataset.templateId;
  const action = button.dataset.templateAction;
  if (action === "use-plan") {
    elements["plan-template"].value = templateId;
    toast("已把模板带入方案生成表单。", "info");
    return;
  }
  if (action === "use-courseware") {
    elements["courseware-template"].value = templateId;
    toast("已把模板带入课件生成表单。", "info");
    return;
  }
  if (action === "preview") {
    try {
      const detail = await api(`/api/v1/templates/${templateId}`);
      const html = buildTemplatePreview(detail);
      elements["preview-frame"].srcdoc = html;
      elements["preview-title"].textContent = `${detail.templateName} · 模板详情`;
    } catch (error) {
      handleError(error);
    }
  }
}

async function handleTaskActions(event) {
  const button = event.target.closest("[data-task-action]");
  if (!button) return;
  const task = state.tasks.find((item) => item.taskId === button.dataset.taskId);
  if (!task) return;
  const action = button.dataset.taskAction;
  if (action === "preview") {
    await openTaskPreview(task);
    return;
  }
  if (action === "validate") {
    await runValidation(task);
    return;
  }
  if (action === "export") {
    await runExport(task, button.dataset.format);
  }
}

async function openTaskPreview(task) {
  try {
    const response = await api(task.result.previewUrl, { method: "GET" });
    const html = await response.text();
    elements["preview-frame"].srcdoc = html;
    elements["preview-title"].textContent = `${task.result.targetType} · ${task.result.targetId}`;
    toast("预览内容已加载。", "info");
  } catch (error) {
    handleError(error);
  }
}

async function runValidation(task) {
  try {
    const result = await api("/api/v1/validation/format", {
      method: "POST",
      json: {
        targetId: task.result.targetId,
        targetType: task.result.targetType,
      },
    });
    const issueText = result.issueCount ? `发现 ${result.issueCount} 项提示` : "未发现格式问题";
    toast(`校验完成：${issueText}，得分 ${result.score}`, result.issueCount ? "warn" : "success");
  } catch (error) {
    handleError(error);
  }
}

async function runExport(task, format) {
  try {
    const result = await api("/api/v1/exports", {
      method: "POST",
      json: {
        targetId: task.result.targetId,
        format,
        expiryDays: 7,
        shareScope: "private",
      },
    });
    await downloadWithAuth(result.downloadUrl, formatFileName(task, result.actualFormat));
    let copied = false;
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(`${window.location.origin}${result.shareUrl}`);
        copied = true;
      } catch (_error) {
        // Ignore clipboard errors and keep the export successful.
      }
    }
    toast(
      copied
        ? `导出成功，已下载 ${result.actualFormat.toUpperCase()} 文件，分享链接也已复制。`
        : `导出成功，已下载 ${result.actualFormat.toUpperCase()} 文件。`,
      "success"
    );
  } catch (error) {
    handleError(error);
  }
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

function formatFileName(task, extension) {
  const courseName = (task.params?.courseName || task.result?.targetId || "export").replace(/[\\/:*?"<>|]/g, "-");
  return `${courseName}.${extension}`;
}

function schedulePolling() {
  stopPolling();
  const hasRunningTask = state.tasks.some((task) => !TERMINAL_STATUSES.has(task.status));
  if (!hasRunningTask) return;
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
  const placeholderHtml = (detail.placeholders || [])
    .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
    .join("");
  return `<!DOCTYPE html>
  <html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <style>
      body { font-family: "Microsoft YaHei", sans-serif; padding: 28px; color: #163142; background: #f8fbfc; }
      .box { max-width: 920px; margin: 0 auto; background: white; border-radius: 24px; padding: 28px; box-shadow: 0 18px 36px rgba(22, 49, 66, 0.12); }
      .meta { display: flex; gap: 10px; flex-wrap: wrap; margin: 16px 0; }
      .chip { display: inline-flex; padding: 6px 10px; border-radius: 999px; background: #e8f1f5; color: #0f4f66; font-size: 12px; }
      pre { white-space: pre-wrap; line-height: 1.7; padding: 18px; border-radius: 18px; background: #f3f7f9; border: 1px solid rgba(22,49,66,.08); }
    </style>
  </head>
  <body>
    <main class="box">
      <h1>${escapeHtml(detail.templateName)}</h1>
      <div class="meta">
        <span class="chip">${escapeHtml(detail.templateType)}</span>
        <span class="chip">v${escapeHtml(String(detail.versionNo))}</span>
        ${placeholderHtml}
      </div>
      <pre>${escapeHtml(detail.previewText || "暂无模板预览内容。")}</pre>
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
