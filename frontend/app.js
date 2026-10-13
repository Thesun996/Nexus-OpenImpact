const MOCK_INSPECT = {
  project_name: "signature_change",
  project_fingerprint: "5f2bb40697ffc7b1eccd7bc7879b9b2faf7b25defdc86b87cb622cf4afe70917",
  coverage: {
    status: "complete",
    python_files: 4,
    indexed_functions: 4,
    files_with_parse_errors: 0,
  },
  symbols: [
    { symbol_id: "utils.format_date", file: "utils.py", line: 1, parameters: [{ name: "date" }] },
    { symbol_id: "report.report", file: "report.py", line: 4, parameters: [{ name: "date" }] },
    { symbol_id: "dashboard.dashboard", file: "dashboard.py", line: 4, parameters: [] },
    { symbol_id: "page.page", file: "page.py", line: 4, parameters: [] },
  ],
};

const MOCK_VALIDATE = {
  validation: { valid: true, diagnostics: [] },
  change_spec: {
    target_symbol_id: "utils.format_date",
    before: { name: "format_date", parameters: [{ name: "date" }] },
    after: { name: "format_date", parameters: [{ name: "date" }, { name: "timezone" }] },
  },
};

const MOCK_REPORT = {
  coverage: {
    status: "complete",
    indexed_modules: 4,
    indexed_functions: 4,
    files_with_parse_errors: 0,
  },
  summary: {
    direct_impact_count: 1,
    indirect_1hop_count: 1,
    indirect_2hop_count: 1,
    manual_review_count: 0,
    unresolved_call_count: 0,
  },
  direct_impacts: [
    {
      caller_symbol_id: "report.report",
      target_symbol_id: "utils.format_date",
      file: "report.py",
      line: 5,
      reason: "新增必填参数 timezone，但这里仍然只传了 date。",
    },
  ],
  indirect_impacts: [
    {
      impacted_symbol_id: "dashboard.dashboard",
      impact_type: "indirect_1hop",
      path: "dashboard.dashboard → report.report → utils.format_date",
    },
    {
      impacted_symbol_id: "page.page",
      impact_type: "indirect_2hop",
      path: "page.page → dashboard.dashboard → report.report → utils.format_date",
    },
  ],
  evidence: {
    file: "report.py",
    line: 5,
    snippet: "return format_date(date)",
    explanation:
      "这里调用 format_date 时只传入了 date。修改后 format_date 还需要 timezone，所以这个调用需要修改或检查。",
  },
  diagnostics: {
    parse_errors: [],
    unresolved_calls: [],
    unresolved_imports: [],
  },
};

const STORAGE_KEY = "openimpact.frontend.state";
const LANGUAGE_KEY = "openimpact.frontend.language";
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const API_BASE = (window.OPENIMPACT_API_BASE || "/api/v1").replace(/\/+$/, "");
const SAMPLE_ZIP_PATH = "./samples/signature_change.zip";
const ZIP_DB_NAME = "openimpact.frontend.workflow";
const ZIP_STORE_NAME = "files";
const ZIP_RECORD_ID = "current";

const I18N_EN = {
  "Nexus OpenImpact - 变更影响分析": "Nexus OpenImpact - Change Impact Analysis",
  "Nexus OpenImpact - 上传项目": "Nexus OpenImpact - Upload Project",
  "Nexus OpenImpact - 选择函数": "Nexus OpenImpact - Select Function",
  "Nexus OpenImpact - 配置变更": "Nexus OpenImpact - Configure Change",
  "Nexus OpenImpact - 分析报告": "Nexus OpenImpact - Analysis Report",
  "Nexus OpenImpact - 功能规划中": "Nexus OpenImpact - Feature Planned",
  主导航: "Main navigation",
  分析步骤: "Analysis steps",
  分析摘要: "Analysis summary",
  项目摘要: "Project summary",
  函数列表: "Function List",
  影响文件: "Impacted Files",
  影响统计: "Impact metrics",
  调用关系简图: "Call graph preview",
  首页: "Home",
  变更分析: "Change Analysis",
  影响范围: "Impact Scope",
  调用关系: "Call Graph",
  依赖分析: "Dependency Analysis",
  历史记录: "History",
  配置管理: "Settings",
  未命名用户: "Unnamed User",
  "▤ 文档": "▤ Docs",
  "⚙ 设置": "⚙ Settings",
  分析引擎: "Analysis Engine",
  运行正常: "Healthy",
  "AST 解析": "AST Parsing",
  符号索引: "Symbol Index",
  依赖图构建: "Dependency Graph",
  影响分析: "Impact Analysis",
  "搜索文件、函数、类或提交信息...": "Search files, functions, classes, or commits...",
  "搜索文件或路径...": "Search files or paths...",
  "搜索函数或文件...": "Search functions or files...",
  变更影响分析: "Change Impact Analysis",
  "基于代码语义分析、调用关系与依赖图，精准识别本次变更的影响范围":
    "Identify the impact scope of this change from code semantics, call relationships, and dependency graphs.",
  分析时间: "Analysis time",
  "Mock 数据": "Mock Data",
  "后端 inspect": "Backend inspect",
  真实接口: "Real API",
  "⟳ 重新分析": "⟳ Re-run",
  "上传 Python ZIP": "Upload Python ZIP",
  "请上传小型 Python 项目 ZIP。系统不会运行你的代码，只读取源码做静态分析。":
    "Upload a small Python project ZIP. The system will not run your code; it only reads source files for static analysis.",
  大小限制: "Size limit",
  等待上传: "Waiting for Upload",
  "上传 ZIP": "Upload ZIP",
  "选择 ZIP 文件": "Choose ZIP File",
  "拖放 ZIP 到这里，或点击选择文件": "Drop a ZIP here, or click to choose a file",
  当前文件: "Current File",
  未选择文件: "No file selected",
  已选择文件: "Selected File",
  读取方式: "Read Mode",
  "只接受 ZIP。上传后会读取函数列表，不会运行项目代码。":
    "ZIP only. After upload, the function list will be read without running project code.",
  开始读取项目: "Read Project",
  读取中: "Reading",
  读取完成: "Read Complete",
  读取失败: "Read Failed",
  第一版边界: "V1 Boundary",
  语言: "Language",
  范围: "Scope",
  变更: "Change",
  判断: "Decision",
  后端静态分析: "Backend static analysis",
  说明: "Note",
  "上传会请求后端 inspect。浏览器会在本地保存本次 ZIP，用于后续 validate 和 analyze；V1 后端不保存用户项目或历史报告。":
    "Upload calls backend inspect. The browser stores this ZIP locally for validate and analyze; the V1 backend does not persist user projects or historical reports.",
  "无法读取内置样例 ZIP。": "Cannot read the bundled sample ZIP.",
  "无法连接后端接口。请确认 FastAPI 已启动，并通过同源代理访问 /api/v1。":
    "Cannot reach the backend API. Make sure FastAPI is running and /api/v1 is available through the same-origin proxy.",
  "当前浏览器无法读取上次上传的 ZIP。请重新上传同一个 ZIP，或使用内置样例 ZIP。":
    "The browser cannot read the previously uploaded ZIP. Re-upload the same ZIP or use the bundled sample ZIP.",
  "请先选择 ZIP 文件。": "Choose a ZIP file first.",
  "只支持 .zip 文件。": "Only .zip files are supported.",
  "ZIP 文件不能超过 5MB。": "ZIP files must be 5MB or smaller.",
  "已读取项目，即将进入函数选择。": "Project read. Entering function selection.",
  变更文件数: "Changed Files",
  受影响文件数: "Impacted Files",
  直接影响函数: "Directly Impacted Functions",
  风险等级: "Risk Level",
  新增: "Added",
  修改: "Modified",
  删除: "Deleted",
  中等: "Medium",
  高: "High",
  中: "Medium",
  低: "Low",
  全部类型: "All Types",
  影响程度: "Impact Level",
  "↕ 按影响度排序": "↕ Sort by Impact",
  文件路径: "File Path",
  类型: "Type",
  变更类型: "Change Type",
  相关函数: "Related Functions",
  操作: "Action",
  查看: "View",
  "⌄ 受影响的相关文件（4）": "⌄ Related impacted files (4)",
  "共 12 个文件": "12 files total",
  "已选择 1 个": "1 selected",
  "10 / 页": "10 / page",
  概览: "Overview",
  相关文件: "Related Files",
  基本信息: "Basic Info",
  行数变更: "Line Changes",
  "... 共6个": "... 6 total",
  "调用关系（简图）": "Call Graph (Preview)",
  相关提交: "Related Commits",
  修复影响分析边界问题: "Fix impact analysis boundary issue",
  调整依赖解析逻辑: "Adjust dependency resolution logic",
  分析日志: "Analysis Logs",
  选择分析函数: "Select Analysis Function",
  "项目已完成读取，从可解析的模块级函数中选择本次计划修改的目标。":
    "The project has been inspected. Choose the module-level function you plan to change.",
  "ZIP 指纹": "ZIP fingerprint",
  重置样例: "Reset Sample",
  下一步: "Next",
  上传项目: "Upload Project",
  已完成: "Complete",
  选择函数: "Select Function",
  当前步骤: "Current Step",
  配置变更: "Configure Change",
  查看报告: "View Report",
  未开始: "Not Started",
  项目名: "Project Name",
  "上传 ZIP 已完成解析": "Uploaded ZIP has been parsed",
  "Python 文件": "Python Files",
  函数数量: "Function Count",
  模块级函数: "Module-level functions",
  覆盖状态: "Coverage Status",
  没有解析错误: "No parse errors",
  模块: "Modules",
  诊断: "Diagnostics",
  全部函数: "All Functions",
  按文件排序: "Sort by File",
  函数名: "Function Name",
  文件: "File",
  行号: "Line",
  参数: "Parameters",
  "共 4 个函数": "4 functions total",
  已选择: "Selected",
  配置签名变更: "Configure Signature Change",
  "目标函数已选择，填写新增必填参数后先校验 ChangeSpec。":
    "A target function is selected. Add the new required parameter and validate the ChangeSpec first.",
  目标: "Target",
  返回选择: "Back to Selection",
  目标函数: "Target Function",
  当前签名: "Current Signature",
  文件位置: "File Location",
  新增参数: "New Parameter",
  新增参数名: "New Parameter Name",
  参数类型: "Parameter Type",
  校验变更: "Validate Change",
  校验结果: "Validation Result",
  校验通过: "Validation Passed",
  校验中: "Validating",
  校验失败: "Validation Failed",
  待校验: "Pending Validation",
  "填写参数后点击校验。": "Enter the parameter, then validate the change.",
  "新增参数名不能为空。": "New parameter name cannot be empty.",
  "新增参数名必须是合法的 Python 标识符。": "New parameter name must be a valid Python identifier.",
  "新增参数不能和已有参数重名。": "New parameter cannot duplicate an existing parameter.",
  "请先通过校验。": "Pass validation first.",
  待输入: "Pending Input",
  修改前: "Before",
  修改后: "After",
  "新增必填参数会用于后续影响分析。": "The new required parameter will be used in the impact analysis.",
  开始分析: "Start Analysis",
  分析中: "Analyzing",
  分析失败: "Analysis Failed",
  "分析已完成，即将打开报告。": "Analysis complete. Opening the report.",
  分析报告: "Analysis Report",
  "分析已完成，以下结果来自静态调用关系、签名规则和源码证据。":
    "Analysis is complete. Results come from static call relationships, signature rules, and source evidence.",
  调整变更: "Adjust Change",
  分析完成: "Analysis Complete",
  变更目标: "Change Target",
  变更类型: "Change Type",
  新增必填参数: "New Required Parameter",
  直接影响: "Direct Impact",
  确定不兼容调用: "Confirmed incompatible call",
  "1-hop 间接": "1-hop Indirect",
  上游建议检查: "Upstream review recommended",
  "2-hop 间接": "2-hop Indirect",
  更上游调用路径: "Higher upstream call path",
  人工检查: "Manual Review",
  无展开参数不确定项: "No uncertain expanded-argument cases",
  未解析调用: "Unresolved Calls",
  覆盖完整: "Complete coverage",
  影响列表: "Impact List",
  调用路径: "Call Paths",
  位置: "Location",
  原因: "Reason",
  路径: "Path",
  "位置：report.py:5": "Location: report.py:5",
  "原因：新增必填参数 timezone，但这里仍然只传了 date。":
    "Reason: the new required parameter timezone was added, but this call still only passes date.",
  "路径：dashboard.dashboard → report.report → utils.format_date":
    "Path: dashboard.dashboard → report.report → utils.format_date",
  "路径：page.page → dashboard.dashboard → report.report → utils.format_date":
    "Path: page.page → dashboard.dashboard → report.report → utils.format_date",
  中文解释: "Explanation",
  "这里调用 format_date 时只传入了 date。修改后 format_date 还需要 timezone，所以这个调用需要修改或检查。":
    "This call only passes date to format_date. After the change, format_date also requires timezone, so this call needs to be updated or reviewed.",
  证据依据: "Evidence Basis",
  "诊断 / 分析限制": "Diagnostics / Analysis Limits",
  未发现诊断项: "No diagnostics found",
  "分析范围不完整，未报告影响不代表整个项目一定没有影响。":
    "Analysis coverage is incomplete. Missing findings do not prove the whole project is unaffected.",
  解析错误: "Parse Errors",
  "未解析 import": "Unresolved Imports",
  未解析调用: "Unresolved Calls",
  规则: "Rule",
  调用者: "Caller",
  解析依据: "Resolution Basis",
  功能规划中: "Feature Planned",
  "当前第一版优先完成上传 ZIP、选择函数、配置变更和查看影响报告。":
    "The first version focuses on uploading a ZIP, selecting a function, configuring a change, and viewing the impact report.",
  返回核心流程: "Back to Core Flow",
  这个模块暂未接入: "This module is not connected yet",
  "调用关系、依赖分析、历史记录和配置管理属于后续扩展。第一版不会展示空页面或虚假数据，核心能力集中在函数签名变更影响分析。":
    "Call graph, dependency analysis, history, and settings are planned extensions. V1 avoids empty pages or fake data and focuses on function-signature change impact analysis.",
  调用关系规划中: "Call Graph Planned",
  调用关系视图暂未接入: "Call graph view is not connected yet",
  "后续会把后端已解析的调用边做成可浏览视图。第一版先通过报告页展示 Direct、1-hop 和 2-hop 调用路径。":
    "Later versions will turn parsed backend call edges into a browsable view. V1 shows Direct, 1-hop, and 2-hop call paths in the report page.",
  依赖分析规划中: "Dependency Analysis Planned",
  依赖分析页暂未接入: "Dependency analysis is not connected yet",
  "依赖分析属于后续扩展。当前第一版只展示函数签名变化、调用位置、传播路径和源码证据。":
    "Dependency analysis is a later extension. V1 only shows function signature changes, call locations, propagation paths, and source evidence.",
  历史记录规划中: "History Planned",
  历史报告暂未接入: "Historical reports are not connected yet",
  "V1 暂不保存上传项目和历史报告。刷新或更换 ZIP 后，需要重新上传并重新分析。":
    "V1 does not persist uploaded projects or historical reports. After refreshing or changing the ZIP, upload and analyze again.",
  配置管理规划中: "Settings Planned",
  配置管理暂未接入: "Settings are not connected yet",
  "配置管理会在接入真实后端、模型 Provider 和项目持久化后再实现。当前页面只使用本地 mock 数据。":
    "Settings will be implemented after the real backend, model provider, and project persistence are connected. This page only uses local mock data.",
  文档入口规划中: "Docs Entry Planned",
  前端文档入口暂未接入: "Frontend docs entry is not connected yet",
  "项目文档目前仍在仓库 docs 目录中维护。后续可以把 API 契约、前端交接说明和使用说明挂到这里。":
    "Project docs are currently maintained in the repository docs directory. Later, API contracts, frontend handoff notes, and usage docs can be linked here.",
  分析日志规划中: "Analysis Logs Planned",
  分析日志页暂未接入: "Analysis logs are not connected yet",
  "真实分析任务接入后，这里可以展示 inspect、validate、analyze 三步的请求状态和诊断信息。":
    "After real analysis tasks are connected, this page can show request status and diagnostics for inspect, validate, and analyze.",
  模块列表规划中: "Module List Planned",
  模块视图暂未接入: "Module view is not connected yet",
  "模块列表将基于 inspect 返回的 modules[] 展示。当前第一版优先展示可选择的函数列表。":
    "The module list will be based on modules[] returned by inspect. V1 prioritizes the selectable function list.",
  诊断信息规划中: "Diagnostics Planned",
  诊断详情页暂未接入: "Diagnostics details are not connected yet",
  "后续会单独展示解析错误、未解析 import、未解析调用和 partial coverage 提示。":
    "Later versions will separately show parse errors, unresolved imports, unresolved calls, and partial coverage warnings.",
  调用路径规划中: "Call Paths Planned",
  调用路径页暂未接入: "Call paths page is not connected yet",
  "报告页已展示核心路径。后续可以把每条 propagation_path 做成独立可展开视图。":
    "The report page already shows core paths. Later, each propagation_path can become an expandable view.",
  "查看报告样例": "View Report Sample",
  "项目切换会在接入上传历史后启用。": "Project switching will be enabled after upload history is connected.",
  "分支选择会在接入项目历史后启用。": "Branch selection will be enabled after project history is connected.",
  "当前项目来自上传 ZIP，暂不支持分支切换。": "This project comes from an uploaded ZIP, so branch switching is not supported yet.",
  "当前正在查看影响文件。": "You are viewing impacted files.",
  "筛选器会在接入真实报告列表后启用。": "Filters will be enabled after real report lists are connected.",
  "影响程度筛选会在接入真实报告列表后启用。": "Impact-level filtering will be enabled after real report lists are connected.",
  "排序会在接入真实报告列表后启用。": "Sorting will be enabled after real report lists are connected.",
  "当前样例只有一页结果。": "The current sample only has one page of results.",
  "当前已经是第 1 页。": "You are already on page 1.",
  "第二页会在真实报告列表中显示。": "Page 2 will appear in real report lists.",
  "分页大小会在真实列表中启用。": "Page size will be enabled in real lists.",
  "详情面板关闭会在真实列表交互中启用。": "Closing the detail panel will be enabled in the real list interaction.",
  "当前正在查看文件概览。": "You are viewing the file overview.",
  "调用关系大图属于后续图谱视图。": "The full call graph belongs to the later graph view.",
  "当前正在查看函数列表。": "You are viewing the function list.",
  "函数筛选会在真实上传项目后启用。": "Function filtering will be enabled after a real uploaded project is connected.",
  "排序会在真实函数列表中启用。": "Sorting will be enabled in the real function list.",
  "参数高级选项暂未开放。": "Advanced parameter options are not available yet.",
  "当前正在查看影响列表。": "You are viewing the impact list.",
  "这个控件将在接入真实数据后启用。": "This control will be enabled after real data is connected.",
};

const PARTIAL_I18N_KEYS = Object.keys(I18N_EN)
  .filter((key) => key.length > 1 && /[\u4e00-\u9fff]/.test(key))
  .sort((a, b) => b.length - a.length);

function getLanguage() {
  return localStorage.getItem(LANGUAGE_KEY) === "en" ? "en" : "zh";
}

function t(text) {
  if (getLanguage() !== "en") return text;
  return I18N_EN[text] || text;
}

function localized(value) {
  if (value && typeof value === "object") return value[getLanguage()] || value.zh || "";
  return t(value);
}

function skipTranslationNode(element) {
  return Boolean(element?.closest("script, style, code, pre, svg, input, textarea, select, option, [data-no-i18n]"));
}

function translateTextNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      if (skipTranslationNode(node.parentElement)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => {
    const trimmed = node.nodeValue.trim();
    const translated = I18N_EN[trimmed];
    if (translated) {
      node.nodeValue = node.nodeValue.replace(trimmed, translated);
      return;
    }
    let partial = node.nodeValue;
    PARTIAL_I18N_KEYS.forEach((key) => {
      if (partial.includes(key)) partial = partial.replaceAll(key, I18N_EN[key]);
    });
    node.nodeValue = partial;
  });
}

function applyLanguage() {
  const language = getLanguage();
  document.documentElement.lang = language === "en" ? "en" : "zh-CN";
  document.body.dataset.language = language;
  document.querySelectorAll("[data-language-toggle]").forEach((button) => {
    button.textContent = language === "en" ? "中文" : "EN";
  });
  if (language !== "en") return;

  document.title = t(document.title);
  document.querySelectorAll("[placeholder]").forEach((control) => {
    control.setAttribute("placeholder", t(control.getAttribute("placeholder")));
  });
  document.querySelectorAll("[aria-label]").forEach((item) => {
    item.setAttribute("aria-label", t(item.getAttribute("aria-label")));
  });
  translateTextNodes(document.body);
}

function initLanguageToggle() {
  document.querySelectorAll("[data-language-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      localStorage.setItem(LANGUAGE_KEY, getLanguage() === "en" ? "zh" : "en");
      window.location.reload();
    });
  });
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function apiUrl(path) {
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${suffix}`;
}

function apiErrorMessage(payload, fallback) {
  const error = payload?.error;
  if (error?.message) return error.message;
  if (payload?.validation?.diagnostics?.length) return diagnosticsToText(payload.validation.diagnostics, fallback);
  if (Array.isArray(payload?.detail)) return payload.detail.map((item) => item.msg || String(item)).join(" ");
  if (typeof payload?.detail === "string") return payload.detail;
  return fallback;
}

async function parseJsonResponse(response) {
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }
  if (!response.ok) {
    throw new Error(apiErrorMessage(payload, `${response.status} ${response.statusText}`));
  }
  return payload;
}

async function requestJson(path, options) {
  try {
    return await parseJsonResponse(await fetch(apiUrl(path), options));
  } catch (error) {
    if (error instanceof TypeError) throw new Error("无法连接后端接口。请确认 FastAPI 已启动，并通过同源代理访问 /api/v1。");
    throw error;
  }
}

function buildForm(file, change, fingerprint) {
  const form = new FormData();
  form.append("file", file, file.name || "project.zip");
  if (change) form.append("change", JSON.stringify(change));
  if (fingerprint) form.append("expected_fingerprint", fingerprint);
  return form;
}

function fileFromBlob(blob, name) {
  return new File([blob], name, { type: blob.type || "application/zip" });
}

async function loadSampleZipFile() {
  const response = await fetch(SAMPLE_ZIP_PATH);
  if (!response.ok) throw new Error("无法读取内置样例 ZIP。");
  return fileFromBlob(await response.blob(), "signature_change.zip");
}

function openZipDatabase() {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const request = window.indexedDB.open(ZIP_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ZIP_STORE_NAME)) db.createObjectStore(ZIP_STORE_NAME, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveWorkflowFile(file) {
  try {
    const db = await openZipDatabase();
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(ZIP_STORE_NAME, "readwrite");
      transaction.objectStore(ZIP_STORE_NAME).put({
        id: ZIP_RECORD_ID,
        name: file.name,
        type: file.type || "application/zip",
        lastModified: file.lastModified || Date.now(),
        blob: file,
      });
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    db.close();
  } catch (error) {
    console.warn("Failed to persist workflow ZIP", error);
  }
}

async function loadWorkflowFile() {
  try {
    const db = await openZipDatabase();
    const record = await new Promise((resolve, reject) => {
      const request = db.transaction(ZIP_STORE_NAME, "readonly").objectStore(ZIP_STORE_NAME).get(ZIP_RECORD_ID);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    db.close();
    if (record?.blob) return fileFromBlob(record.blob, record.name || "project.zip");
  } catch (error) {
    console.warn("Failed to load workflow ZIP", error);
  }
  return null;
}

async function fileForFollowupRequest(state) {
  const storedFile = await loadWorkflowFile();
  if (storedFile) return storedFile;
  if (state.zipSource === "browser_file" || state.zipSource === "uploaded_once") throw new Error("当前浏览器无法读取上次上传的 ZIP。请重新上传同一个 ZIP，或使用内置样例 ZIP。");
  return loadSampleZipFile();
}

function defaultState() {
  return {
    fileName: null,
    zipSource: "sample",
    uploadStatus: "idle",
    inspect: clone(MOCK_INSPECT),
    selectedSymbolId: "utils.format_date",
    parameterName: "timezone",
    parameterKind: "positional_or_keyword",
    validation: null,
    report: null,
    validationLoading: false,
    validationError: null,
    analyzeLoading: false,
    analyzeError: null,
  };
}

function loadState() {
  try {
    return { ...defaultState(), ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return defaultState();
  }
}

function saveState(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function findSymbol(state) {
  return state.inspect.symbols.find((symbol) => symbol.symbol_id === state.selectedSymbolId) || state.inspect.symbols[0];
}

function shortFunctionName(symbolId) {
  return symbolId.split(".").at(-1) || symbolId;
}

function signatureFor(symbol, extraParameter) {
  const params = symbol.parameters.map((parameter) => parameter.name);
  if (extraParameter) params.push(extraParameter);
  return `${shortFunctionName(symbol.symbol_id)}(${params.join(", ")})`;
}

function diagnosticsToText(diagnostics, fallback) {
  if (!Array.isArray(diagnostics) || diagnostics.length === 0) return fallback;
  return diagnostics.map((item) => item.message || item.reason || item.code || String(item)).join(" ");
}

function collectDiagnostics(report) {
  const diagnostics = report?.diagnostics || {};
  const groups = [
    ["解析错误", diagnostics.parse_errors],
    ["未解析 import", diagnostics.unresolved_imports],
    ["未解析调用", diagnostics.unresolved_calls],
  ];
  return groups.flatMap(([label, items]) =>
    (Array.isArray(items) ? items : []).map((item) => ({
      label,
      message: item.message || item.reason || item.symbol_id || item.module || item.file || JSON.stringify(item),
    })),
  );
}

function pathFromEdges(edges) {
  if (!Array.isArray(edges) || edges.length === 0) return "";
  return [edges[0].caller_symbol_id, ...edges.map((edge) => edge.callee_symbol_id)].filter(Boolean).join(" → ");
}

function indirectPath(item) {
  if (item.path) return item.path;
  const source = item.sources?.[0];
  const edges = source?.propagation_path;
  return pathFromEdges(edges) || item.impacted_symbol_id || "-";
}

function impactLabel(type) {
  if (type === "indirect_1hop") return "1-hop Indirect";
  if (type === "indirect_2hop") return "2-hop Indirect";
  return "Direct Impact";
}

function renderImpactList(report) {
  const list = document.querySelector(".impact-list");
  if (!list) return;

  const directItems = (report.direct_impacts || []).map(
    (item) => `
      <section class="impact-item direct">
        <header><mark>${impactLabel("direct")}</mark><b>${escapeHtml(item.caller_symbol_id || "-")} → ${escapeHtml(item.target_symbol_id || "-")}</b></header>
        <p>${escapeHtml(t("位置"))}：${escapeHtml(item.file || "-")}:${escapeHtml(item.line ?? "-")}</p>
        <p>${escapeHtml(t("原因"))}：${escapeHtml(item.reason || item.after_reason || "-")}</p>
      </section>`,
  );

  const indirectItems = (report.indirect_impacts || []).map((item) => {
    const isTwoHop = item.impact_type === "indirect_2hop";
    return `
      <section class="impact-item indirect${isTwoHop ? " two-hop" : ""}">
        <header><mark>${impactLabel(item.impact_type)}</mark><b>${escapeHtml(item.impacted_symbol_id || "-")}</b></header>
        <p>${escapeHtml(t("路径"))}：${escapeHtml(indirectPath(item))}</p>
      </section>`;
  });

  list.innerHTML = [...directItems, ...indirectItems].join("") || `<p class="empty-state">${escapeHtml(t("未发现诊断项"))}</p>`;
}

function primaryEvidence(report) {
  if (report.evidence) {
    return {
      impactType: "direct",
      file: report.evidence.file,
      line: report.evidence.line,
      snippet: report.evidence.snippet,
      reason: report.evidence.explanation,
      rule: "required_parameter_added_breaks_call",
      target: report.change?.target_symbol_id || "utils.format_date",
      caller: report.direct_impacts?.[0]?.caller_symbol_id || "report.report",
      resolutionBasis: report.direct_impacts?.[0]?.resolution_basis || "from_import",
    };
  }

  const evidence = (report.evidences || []).find((item) => item.impact_type === "direct") || report.evidences?.[0];
  const explanation = (report.explanations || []).find(
    (item) => item.evidence?.evidence_reference && item.evidence.evidence_reference === evidence?.evidence_reference,
  );
  const direct = (report.direct_impacts || []).find(
    (item) => item.file === evidence?.location?.file && item.line === evidence?.location?.line,
  );
  return {
    impactType: evidence?.impact_type || "direct",
    file: evidence?.location?.file || direct?.file || "-",
    line: evidence?.location?.line ?? direct?.line ?? "-",
    snippet: (evidence?.source_snippet || evidence?.call_expression || "-").trim(),
    reason: explanation?.explanation?.why_affected || explanation?.explanation?.summary || evidence?.reason || direct?.reason || "-",
    rule: evidence?.rule || direct?.rule_id || "-",
    target: evidence?.target_symbol || direct?.target_symbol_id || report.change?.target_symbol_id || "-",
    caller: direct?.caller_symbol_id || "-",
    resolutionBasis: direct?.resolution_basis || "-",
  };
}

function renderEvidence(report) {
  const evidence = primaryEvidence(report);
  const evidenceCard = document.querySelector(".evidence-card");
  if (evidenceCard) {
    const title = evidenceCard.querySelector(".detail-title");
    const tag = evidenceCard.querySelector(".tag");
    const code = evidenceCard.querySelector("code");
    const explanation = evidenceCard.querySelector(".explanation-panel p");
    if (title) title.innerHTML = `<b>▤</b> ${escapeHtml(evidence.file)}:${escapeHtml(evidence.line)}`;
    if (tag) tag.textContent = impactLabel(evidence.impactType);
    if (code) code.textContent = evidence.snippet;
    if (explanation) explanation.textContent = evidence.reason;
  }

  const metaList = document.querySelector(".evidence-meta-card .info-list");
  if (metaList) {
    metaList.innerHTML = `
      <div><span>${escapeHtml(t("规则"))}</span><b>${escapeHtml(evidence.rule)}</b></div>
      <div><span>${escapeHtml(t("目标"))}</span><b>${escapeHtml(evidence.target)}</b></div>
      <div><span>${escapeHtml(t("调用者"))}</span><b>${escapeHtml(evidence.caller)}</b></div>
      <div><span>${escapeHtml(t("解析依据"))}</span><mark class="tag change">${escapeHtml(evidence.resolutionBasis)}</mark></div>`;
  }
}

function projectNameFromFile(fileName) {
  return (fileName || "signature_change.zip").replace(/\.zip$/i, "") || "signature_change";
}

async function inspectProject(file) {
  const uploadFile = file || (await loadSampleZipFile());
  const inspect = await requestJson("/projects/inspect", {
    method: "POST",
    body: buildForm(uploadFile),
  });
  if (!inspect.project_name) inspect.project_name = projectNameFromFile(uploadFile.name);
  return inspect;
}

function buildChangeSpec(state) {
  const symbol = findSymbol(state);
  const parameterName = (state.parameterName || "").trim();
  const beforeParameters = symbol.parameters.map((parameter) => ({
    name: parameter.name,
    kind: parameter.kind || "positional_or_keyword",
    has_default: Boolean(parameter.has_default),
    default_source: parameter.default_source || null,
    annotation_source: parameter.annotation_source || null,
  }));
  const addedParameter = {
    name: parameterName,
    kind: state.parameterKind || "positional_or_keyword",
    has_default: false,
    default_source: null,
    annotation_source: null,
  };
  return {
    change_type: "add_required_parameter",
    target_symbol_id: state.selectedSymbolId,
    before: {
      name: shortFunctionName(symbol.symbol_id),
      parameters: beforeParameters,
      is_async: false,
      return_annotation_source: null,
    },
    after: {
      name: shortFunctionName(symbol.symbol_id),
      parameters: parameterName ? [...beforeParameters, addedParameter] : beforeParameters,
      is_async: false,
      return_annotation_source: null,
    },
    added_parameter: parameterName
      ? { name: parameterName, kind: addedParameter.kind, required: true, annotation_source: null }
      : null,
  };
}

function buildApiChange(state) {
  return {
    target_symbol_id: state.selectedSymbolId,
    added_parameter: {
      name: (state.parameterName || "").trim(),
      kind: state.parameterKind || "positional_or_keyword",
    },
  };
}

function validateParameterName(state) {
  const symbol = findSymbol(state);
  const parameterName = (state.parameterName || "").trim();
  if (!parameterName) return "新增参数名不能为空。";
  if (!/^[A-Za-z_]\w*$/.test(parameterName)) return "新增参数名必须是合法的 Python 标识符。";
  if (symbol.parameters.some((parameter) => parameter.name === parameterName)) return "新增参数不能和已有参数重名。";
  return null;
}

async function validateChange(state) {
  const diagnostic = validateParameterName(state);
  if (diagnostic) {
    const response = clone(MOCK_VALIDATE);
    response.project_name = state.inspect?.project_name || response.project_name;
    response.project_fingerprint = state.inspect?.project_fingerprint || response.project_fingerprint;
    response.coverage = clone(state.inspect?.coverage || response.coverage);
    response.change_spec = buildChangeSpec(state);
    response.validation = { valid: false, diagnostics: [{ code: "invalid_change_config", message: diagnostic }] };
    response.diagnostics = clone(state.inspect?.diagnostics || response.diagnostics || {});
    return response;
  }

  const file = await fileForFollowupRequest(state);
  return requestJson("/changes/validate", {
    method: "POST",
    body: buildForm(file, buildApiChange(state), state.inspect?.project_fingerprint),
  });
}

async function analyzeProject(state) {
  if (!state.validation?.validation?.valid) throw new Error("请先通过校验。");
  const file = await fileForFollowupRequest(state);
  return requestJson("/projects/analyze", {
    method: "POST",
    body: buildForm(file, buildApiChange(state), state.inspect?.project_fingerprint),
  });
}

window.OpenImpactApi = { inspectProject, validateChange, analyzeProject };

function formatUploadSize(bytes) {
  if (!Number.isFinite(bytes)) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function validateUploadFile(file) {
  if (!file) return "请先选择 ZIP 文件。";
  if (!file.name.toLowerCase().endsWith(".zip")) return "只支持 .zip 文件。";
  if (file.size > MAX_UPLOAD_BYTES) return "ZIP 文件不能超过 5MB。";
  return null;
}

function setUploadUi(status, message) {
  const statusTag = document.querySelector("[data-upload-status]");
  const messageNode = document.querySelector("[data-upload-message]");
  if (statusTag) {
    statusTag.textContent = t(status);
    statusTag.className = status === "读取完成" ? "tag low" : status === "读取失败" ? "tag high" : "tag medium";
  }
  if (messageNode) messageNode.textContent = t(message);
}

async function resetFlowAfterInspect(state, file, inspect) {
  const firstSymbol = inspect.symbols?.[0]?.symbol_id || "utils.format_date";
  await saveWorkflowFile(file);
  Object.assign(state, {
    fileName: file.name,
    zipSource: file.name === "signature_change.zip" ? "sample" : "browser_file",
    uploadStatus: "success",
    inspect,
    selectedSymbolId: firstSymbol,
    parameterName: "timezone",
    parameterKind: "positional_or_keyword",
    validation: null,
    report: null,
    validationLoading: false,
    validationError: null,
    analyzeLoading: false,
    analyzeError: null,
  });
  saveState(state);
}

function initUpload(state) {
  const input = document.querySelector("[data-upload-input]");
  const dropzone = document.querySelector("[data-upload-dropzone]");
  const submit = document.querySelector("[data-upload-submit]");
  const fileLabel = document.querySelector("[data-upload-file]");
  const projectLabel = document.querySelector("[data-upload-project-label]");
  let selectedFile = null;

  const setSelectedFile = (file) => {
    selectedFile = file;
    if (!file) {
      if (fileLabel) fileLabel.textContent = t("未选择文件");
      if (projectLabel) projectLabel.textContent = t("等待上传");
      dropzone?.classList.remove("selected", "error");
      if (submit) submit.disabled = true;
      setUploadUi("等待上传", "只接受 ZIP。上传后会读取函数列表，不会运行项目代码。");
      return;
    }

    const error = validateUploadFile(file);
    if (fileLabel) {
      fileLabel.textContent = `${file.name} · ${formatUploadSize(file.size)}`;
    }
    if (projectLabel) projectLabel.textContent = projectNameFromFile(file.name);
    dropzone?.classList.toggle("selected", !error);
    dropzone?.classList.toggle("error", Boolean(error));
    if (submit) submit.disabled = Boolean(error);
    setUploadUi(error ? "读取失败" : file ? "已选择文件" : "等待上传", error || "只接受 ZIP。上传后会读取函数列表，不会运行项目代码。");
  };

  setSelectedFile(null);

  input?.addEventListener("change", () => {
    setSelectedFile(input.files?.[0] || null);
  });

  dropzone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });

  dropzone?.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragging");
  });

  dropzone?.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
    const file = event.dataTransfer?.files?.[0] || null;
    if (input && file) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    }
    setSelectedFile(file);
  });

  submit?.addEventListener("click", async () => {
    const error = validateUploadFile(selectedFile);
    if (error) {
      setUploadUi("读取失败", error);
      showToast(error);
      return;
    }
    submit.disabled = true;
    dropzone?.classList.add("loading");
    setUploadUi("读取中", "只接受 ZIP。上传后会读取函数列表，不会运行项目代码。");
    try {
      const inspect = await window.OpenImpactApi.inspectProject(selectedFile);
      await resetFlowAfterInspect(state, selectedFile, inspect);
      setUploadUi("读取完成", "已读取项目，即将进入函数选择。");
      showToast("已读取项目，即将进入函数选择。");
      window.setTimeout(() => {
        window.location.href = "./function-select.html";
      }, 450);
    } catch (error) {
      submit.disabled = false;
      const message = error?.message || "读取失败";
      setUploadUi("读取失败", message);
      showToast(message);
    } finally {
      dropzone?.classList.remove("loading");
    }
  });
}

function renderProjectSummary(state) {
  const inspect = state.inspect || MOCK_INSPECT;
  const coverage = inspect.coverage || {};
  const functionCount = inspect.symbols?.length || coverage.indexed_functions || 0;
  const fingerprint = inspect.project_fingerprint ? `${inspect.project_fingerprint.slice(0, 8)}...` : "-";
  document.querySelectorAll("[data-project-name]").forEach((item) => {
    item.textContent = inspect.project_name || "signature_change";
  });
  document.querySelectorAll("[data-file-name]").forEach((item) => {
    item.textContent = state.fileName || "uploaded-zip";
  });
  document.querySelectorAll("[data-project-fingerprint]").forEach((item) => {
    item.textContent = fingerprint;
  });
  document.querySelectorAll("[data-python-files]").forEach((item) => {
    item.textContent = coverage.python_files ?? 0;
  });
  document.querySelectorAll("[data-function-count]").forEach((item) => {
    item.textContent = functionCount;
  });
  document.querySelectorAll("[data-coverage-status]").forEach((item) => {
    item.textContent = coverage.status || "unknown";
  });
  document.querySelectorAll("[data-function-total]").forEach((item) => {
    item.textContent = getLanguage() === "en" ? `${functionCount} functions total` : `共 ${functionCount} 个函数`;
  });
}

function renderFunctionTable(state) {
  const table = document.querySelector(".function-table");
  if (!table) return;

  const rows = state.inspect.symbols
    .map((symbol) => {
      const params = symbol.parameters.length
        ? symbol.parameters.map((parameter) => `<mark class="param-chip">${escapeHtml(parameter.name)}</mark>`).join(" ")
        : '<span class="muted-cell">-</span>';
      const selected = symbol.symbol_id === state.selectedSymbolId ? " selected" : "";
      return `
        <div class="function-row${selected}" role="row" data-symbol-id="${escapeHtml(symbol.symbol_id)}">
          <span class="symbol-name">${escapeHtml(symbol.symbol_id)}</span>
          <span>${escapeHtml(symbol.file)}</span>
          <span>${escapeHtml(symbol.line)}</span>
          <span>${params}</span>
        </div>`;
    })
    .join("");

  table.innerHTML = `
    <div class="function-row table-head" role="row">
      <span>${t("函数名")}</span>
      <span>${t("文件")}</span>
      <span>${t("行号")}</span>
      <span>${t("参数")}</span>
    </div>${rows}`;

  table.querySelectorAll("[data-symbol-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedSymbolId = row.dataset.symbolId;
      state.validation = null;
      state.report = null;
      saveState(state);
      renderFunctionTable(state);
      document.querySelectorAll("[data-selected-symbol]").forEach((item) => {
        item.textContent = state.selectedSymbolId;
      });
    });
  });
}

function initFunctionSelect(state) {
  renderProjectSummary(state);
  renderFunctionTable(state);
  document.querySelectorAll("[data-selected-symbol]").forEach((item) => {
    item.textContent = state.selectedSymbolId;
  });
  document.querySelector("[data-reset-flow]")?.addEventListener("click", async () => {
    const sampleFile = await loadSampleZipFile();
    const inspect = await window.OpenImpactApi.inspectProject(sampleFile);
    await resetFlowAfterInspect(state, sampleFile, inspect);
    saveState(state);
    renderProjectSummary(state);
    renderFunctionTable(state);
    document.querySelectorAll("[data-selected-symbol]").forEach((item) => {
      item.textContent = state.selectedSymbolId;
    });
  });
}

function renderValidation(state) {
  const symbol = findSymbol(state);
  const before = signatureFor(symbol);
  const parameterName = (state.parameterName || "").trim();
  document.querySelectorAll("[data-target-symbol]").forEach((item) => {
    item.textContent = state.selectedSymbolId;
  });
  document.querySelectorAll("[data-current-signature]").forEach((item) => {
    item.textContent = before;
  });
  document.querySelectorAll("[data-after-signature]").forEach((item) => {
    const marker = parameterName ? escapeHtml(parameterName) : t("待输入");
    item.innerHTML = `${escapeHtml(before.replace(/\)$/, ""))}, <mark>${marker}</mark>)`;
  });
  const status = document.querySelector("[data-validation-status]");
  if (status) {
    const valid = state.validation?.validation?.valid;
    status.textContent = state.validationLoading ? t("校验中") : valid ? t("校验通过") : state.validation ? t("校验失败") : t("待校验");
    status.className = state.validationLoading ? "tag medium" : valid ? "tag low" : state.validation ? "tag high" : "tag medium";
  }
  const validationMessage = document.querySelector("[data-validation-message]");
  if (validationMessage) {
    const diagnostics = state.validation?.validation?.diagnostics || [];
    const message = state.validationLoading
      ? "校验中"
      : state.validation?.validation?.valid
        ? "校验通过"
        : diagnosticsToText(diagnostics, state.validationError || "填写参数后点击校验。");
    validationMessage.textContent = t(message);
    validationMessage.hidden = false;
    validationMessage.classList.toggle("error", Boolean(state.validation && !state.validation.validation?.valid));
  }
  const validateButton = document.querySelector("[data-action='validate']");
  if (validateButton) validateButton.disabled = Boolean(state.validationLoading || state.analyzeLoading);
  const action = document.querySelector("[data-action='analyze']");
  if (action) action.classList.toggle("disabled-action", !state.validation?.validation?.valid || state.analyzeLoading);
  const analysisMessage = document.querySelector("[data-analysis-message]");
  if (analysisMessage) {
    const message = state.analyzeLoading ? "分析中" : state.analyzeError || "新增必填参数会用于后续影响分析。";
    analysisMessage.textContent = t(message);
    analysisMessage.classList.toggle("error", Boolean(state.analyzeError));
  }
  const fileLocation = document.querySelector("[data-target-location]");
  if (fileLocation) fileLocation.textContent = `${symbol.file}:${symbol.line}`;
}

function initConfigure(state) {
  const nameInput = document.querySelector("[data-parameter-name]");
  const kindSelect = document.querySelector("[data-parameter-kind]");
  if (nameInput) nameInput.value = state.parameterName;
  if (kindSelect) kindSelect.value = state.parameterKind;
  renderValidation(state);

  [nameInput, kindSelect].forEach((input) => {
    input?.addEventListener("input", () => {
      state.parameterName = nameInput?.value.trim() || "";
      state.parameterKind = kindSelect?.value || "positional_or_keyword";
      state.validation = null;
      state.report = null;
      state.validationError = null;
      state.analyzeError = null;
      saveState(state);
      renderValidation(state);
    });
  });

  document.querySelector("[data-action='validate']")?.addEventListener("click", async () => {
    state.validationLoading = true;
    state.validationError = null;
    state.analyzeError = null;
    state.validation = null;
    state.report = null;
    saveState(state);
    renderValidation(state);
    try {
      state.validation = await window.OpenImpactApi.validateChange(state);
    } catch (error) {
      state.validationError = error?.message || "校验失败";
    } finally {
      state.validationLoading = false;
      saveState(state);
      renderValidation(state);
    }
  });

  document.querySelector("[data-action='analyze']")?.addEventListener("click", async (event) => {
    event.preventDefault();
    if (!state.validation?.validation?.valid) {
      state.analyzeError = "请先通过校验。";
      renderValidation(state);
      return;
    }
    state.analyzeLoading = true;
    state.analyzeError = null;
    saveState(state);
    renderValidation(state);
    try {
      state.report = await window.OpenImpactApi.analyzeProject(state);
      state.analyzeLoading = false;
      saveState(state);
      showToast("分析已完成，即将打开报告。");
      window.location.href = "./analysis-report.html";
    } catch (error) {
      state.analyzeLoading = false;
      state.analyzeError = error?.message || "分析失败";
      saveState(state);
      renderValidation(state);
    }
  });
}

function initReport(state) {
  if (!state.report) state.report = clone(MOCK_REPORT);
  const report = state.report;
  const symbol = state.selectedSymbolId;
  document.querySelectorAll("[data-target-symbol]").forEach((item) => {
    item.textContent = symbol;
  });
  document.querySelectorAll("[data-parameter-name-display]").forEach((item) => {
    item.textContent = state.parameterName;
  });
  const summaryMap = {
    direct: report.summary?.direct_impact_count ?? 0,
    hop1: report.summary?.indirect_1hop_count ?? 0,
    hop2: report.summary?.indirect_2hop_count ?? 0,
    manual: report.summary?.manual_review_count ?? 0,
    unresolved: report.summary?.unresolved_call_count ?? 0,
  };
  Object.entries(summaryMap).forEach(([key, value]) => {
    document.querySelectorAll(`[data-summary='${key}']`).forEach((item) => {
      item.textContent = value;
    });
  });

  renderImpactList(report);
  renderEvidence(report);

  const diagnostics = collectDiagnostics(report);
  const diagnosticsList = document.querySelector("[data-diagnostics-list]");
  const diagnosticsStatus = document.querySelector("[data-diagnostics-status]");
  const coverageStatus = report.coverage?.status || state.inspect?.coverage?.status || "complete";
  if (diagnosticsStatus) {
    diagnosticsStatus.textContent = diagnostics.length ? String(diagnostics.length) : t("未发现诊断项");
    diagnosticsStatus.className = diagnostics.length || coverageStatus === "partial" ? "tag medium" : "tag low";
  }
  if (diagnosticsList) {
    const coverageNotice = coverageStatus === "partial" ? `<p>${escapeHtml(t("分析范围不完整，未报告影响不代表整个项目一定没有影响。"))}</p>` : "";
    const items = diagnostics
      .map(
        (item) => `<div class="diagnostic-item"><b>${escapeHtml(t(item.label))}</b><span>${escapeHtml(item.message)}</span></div>`,
      )
      .join("");
    diagnosticsList.innerHTML = coverageNotice || items ? `${coverageNotice}${items}` : `<p>${escapeHtml(t("未发现诊断项"))}</p>`;
  }
}

function showToast(message) {
  let toast = document.querySelector(".app-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "app-toast";
    document.body.appendChild(toast);
  }
  toast.textContent = t(message);
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.classList.remove("visible");
  }, 2200);
}

function initNotices() {
  document.querySelectorAll("[data-notice]").forEach((control) => {
    control.addEventListener("click", () => {
      showToast(control.dataset.notice || "这个控件将在接入真实数据后启用。");
    });
  });
}

const COMING_SOON_MODULES = {
  callgraph: {
    icon: "⌬",
    nav: "callgraph",
    title: "调用关系规划中",
    cardTitle: "调用关系视图暂未接入",
    copy: "后续会把后端已解析的调用边做成可浏览视图。第一版先通过报告页展示 Direct、1-hop 和 2-hop 调用路径。",
  },
  dependency: {
    icon: "◇",
    nav: "dependency",
    title: "依赖分析规划中",
    cardTitle: "依赖分析页暂未接入",
    copy: "依赖分析属于后续扩展。当前第一版只展示函数签名变化、调用位置、传播路径和源码证据。",
  },
  history: {
    icon: "◴",
    nav: "history",
    title: "历史记录规划中",
    cardTitle: "历史报告暂未接入",
    copy: "V1 暂不保存上传项目和历史报告。刷新或更换 ZIP 后，需要重新上传并重新分析。",
  },
  settings: {
    icon: "⚙",
    nav: "settings",
    title: "配置管理规划中",
    cardTitle: "配置管理暂未接入",
    copy: "配置管理会在接入真实后端、模型 Provider 和项目持久化后再实现。当前页面只使用本地 mock 数据。",
  },
  docs: {
    icon: "▤",
    title: "文档入口规划中",
    cardTitle: "前端文档入口暂未接入",
    copy: "项目文档目前仍在仓库 docs 目录中维护。后续可以把 API 契约、前端交接说明和使用说明挂到这里。",
  },
  logs: {
    icon: "◴",
    title: "分析日志规划中",
    cardTitle: "分析日志页暂未接入",
    copy: "真实分析任务接入后，这里可以展示 inspect、validate、analyze 三步的请求状态和诊断信息。",
  },
  modules: {
    icon: "▣",
    title: "模块列表规划中",
    cardTitle: "模块视图暂未接入",
    copy: "模块列表将基于 inspect 返回的 modules[] 展示。当前第一版优先展示可选择的函数列表。",
  },
  diagnostics: {
    icon: "!",
    title: "诊断信息规划中",
    cardTitle: "诊断详情页暂未接入",
    copy: "后续会单独展示解析错误、未解析 import、未解析调用和 partial coverage 提示。",
  },
  paths: {
    icon: "⌘",
    title: "调用路径规划中",
    cardTitle: "调用路径页暂未接入",
    copy: "报告页已展示核心路径。后续可以把每条 propagation_path 做成独立可展开视图。",
  },
};

function initComingSoon() {
  const params = new URLSearchParams(window.location.search);
  const moduleKey = params.get("module") || "callgraph";
  const module = COMING_SOON_MODULES[moduleKey] || COMING_SOON_MODULES.callgraph;

  document.querySelector("[data-coming-title]").textContent = localized(module.title);
  document.querySelector("[data-coming-subtitle]").textContent = t("当前第一版优先完成上传 ZIP、选择函数、配置变更和查看影响报告。");
  document.querySelector("[data-coming-icon]").textContent = module.icon;
  document.querySelector("[data-coming-card-title]").textContent = localized(module.cardTitle);
  document.querySelector("[data-coming-copy]").textContent = localized(module.copy);

  document.querySelectorAll("[data-module-link]").forEach((link) => {
    link.classList.toggle("active", Boolean(module.nav && link.dataset.moduleLink === module.nav));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const state = loadState();
  saveState(state);
  const page = document.body.dataset.page;
  if (page === "upload") initUpload(state);
  if (page === "function-select") initFunctionSelect(state);
  if (page === "configure-change") initConfigure(state);
  if (page === "analysis-report") initReport(state);
  if (page === "coming-soon") initComingSoon();
  initNotices();
  initLanguageToggle();
  applyLanguage();
});
