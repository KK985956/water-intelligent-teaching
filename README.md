# 水利智能教学应用

这是一个面向水利课程教学资料自动生成的 Web 应用原型。项目依据详细设计报告中的“用户层、应用层、业务层、数据层、资源层”分层思想实现，围绕模板管理、教学方案生成、课件生成、资源管理、格式校验、人工编辑、导出分享、用户权限、审计日志和 WebSocket 任务进度推送构建完整演示闭环。

> 当前工程采用 `Flask + SQLite + 原生 Web 前端` 的轻量实现方式。详细设计报告中提出的 `Spring Boot + Python 服务` 可作为后续工程化拆分方向；本仓库优先保证课程实训场景下能本地运行、能演示、能测试、能持续迭代。

## 一、功能概览

| 功能模块 | 已实现能力 |
| --- | --- |
| 用户与权限模块 | 登录认证、Token 校验、管理员/教师/学生角色权限、用户创建、停用、改角色、重置密码 |
| 模板管理模块 | 模板上传、模板分类、占位符提取、格式规则 JSON、版本历史、版本回滚 |
| 教学方案生成模块 | 根据课程名称、课时、授课对象、教学目标和重难点生成教学方案 |
| 课件生成模块 | 基于已生成教学方案继续生成课件结构、页面标题和页面要点 |
| 资源管理模块 | 上传案例、图片、视频、公式、习题等资源，支持标签和资源引用 |
| 格式校验模块 | 对教学方案和课件进行规则检查，生成问题列表、得分和状态 |
| 人工编辑模块 | 可读取生成结果 JSON，修改后重新生成预览、Word/PPT 输出和校验记录 |
| 导出分享模块 | 支持 Word、PPT、HTML、JSON、Markdown、TXT、PDF 等导出入口，分享链接支持有效期和最大下载次数 |
| 任务进度模块 | 生成任务异步执行，支持轮询和 WebSocket 进度推送，支持取消和重试 |
| 审计日志模块 | 记录登录、上传、生成、编辑、导出、用户管理等关键行为 |

## 二、项目结构

```text
.
├── backend/                     # Flask 后端、前端静态工作台和运行入口
│   ├── app/                     # 后端核心应用包
│   │   ├── __init__.py          # create_app 工厂函数、错误处理和路由注册
│   │   ├── auth.py              # 密码哈希、Token 签发与接口鉴权装饰器
│   │   ├── config.py            # 系统配置、目录配置、上传格式和端口配置
│   │   ├── database.py          # SQLite 表结构、初始化、迁移和通用查询函数
│   │   ├── documents.py         # 教学内容生成、模板解析、HTML/DOCX/PPTX 基础生成与校验
│   │   ├── errors.py            # ServiceError 业务异常定义
│   │   ├── office.py            # Word/PPT 模板填充和 Office/PDF 导出适配
│   │   ├── realtime.py          # WebSocket 进度推送服务
│   │   ├── routes.py            # RESTful API 路由定义
│   │   └── services.py          # 业务服务层，组织模板、任务、用户、资源、导出等核心流程
│   ├── data/                    # 内置知识库和示例模板
│   ├── tests/                   # 后端集成测试
│   ├── web/                     # 前端 Web 工作台
│   │   ├── dashboard.html       # 单页工作台入口
│   │   └── assets/
│   │       ├── dashboard-v2.js  # 前端状态管理、接口调用和页面交互
│   │       └── dashboard.css    # 工作台视觉样式
│   ├── requirements.txt         # Python 依赖
│   └── run.py                   # 本地启动入口
├── docs/                        # GitHub 上传、迭代与发布说明
├── .gitignore                   # 忽略本地运行数据、Office 文档和环境文件
└── README.md                    # 项目总说明
```

`backend/storage/` 是运行时目录，会保存数据库、上传资源、生成结果和导出文件，不应提交到 GitHub。本地设计报告、Word/PPT 模板成品和个人数据默认不提交，可按需要单独备份。

## 三、整体架构设计

系统按详细设计报告拆分为五层：

| 层次 | 代码位置 | 作用 |
| --- | --- | --- |
| 用户层 | `backend/web/dashboard.html`、`dashboard-v2.js`、`dashboard.css` | 提供登录、模板、生成、资源、编辑、导出、审计等可操作界面 |
| 应用层 | `backend/app/routes.py`、`backend/app/auth.py` | 接收 HTTP 请求，完成 Token 鉴权、权限校验和 API 路由分发 |
| 业务层 | `backend/app/services.py`、`backend/app/documents.py`、`backend/app/office.py` | 完成模板管理、任务调度、内容生成、格式校验、导出分享和人工编辑 |
| 数据层 | `backend/app/database.py` | 初始化 SQLite 表结构，保存用户、角色、模板、任务、资源、校验、导出和审计日志 |
| 资源层 | `backend/data/`、`backend/storage/` | 管理知识库、模板文件、上传素材、生成文件和导出文件 |

核心业务流程：

```text
登录认证
  → 选择模板
  → 输入课程参数
  → 创建生成任务
  → 匹配知识点与案例
  → 生成教学方案/课件
  → 格式校验
  → 人工编辑与再生成
  → 导出/分享
  → 写入审计日志
```

## 四、核心数据对象与表设计

详细设计报告中的实体类在当前实现中主要映射为 SQLite 表、序列化函数和业务服务对象。

| 设计对象 | 当前表/结构 | 说明 |
| --- | --- | --- |
| `User` | `t_user` | 用户账号、密码哈希、姓名、部门、角色、状态 |
| `RolePermission` | `t_role` | 角色编码、角色名称、权限集合 JSON |
| `Template` | `t_template` | 当前模板元数据、类型、文件路径、版本号、格式规则、占位符 |
| `TemplateVersion` | `t_template_version` | 模板历史版本、变更说明、是否当前版本，用于回滚 |
| `GenerationTask` | `t_generation_task` | 异步生成任务、参数快照、状态、进度、结果路径和错误信息 |
| `TeachingPlan` | `t_teaching_plan` | 教学方案结果、课程信息、结构化内容、预览路径和文件路径 |
| `Courseware` | `t_courseware` | 课件结果、幻灯片数量、页面结构、预览路径和文件路径 |
| `Resource` | `t_resource` | 教学资源文件、类型、标签、校验值和上传人 |
| `ValidationResult` | `t_validation_result` | 格式校验问题、得分、状态和检查时间 |
| `ExportPackage` | `t_export_record` | 导出文件、分享链接、有效期、下载次数、分享范围 |
| `AuditLog` | `t_audit_log` | 用户操作审计日志 |

## 五、后端程序文件与函数说明

### 1. 应用初始化

| 文件 | 函数/对象 | 功能 |
| --- | --- | --- |
| `backend/run.py` | `create_app()` 调用入口 | 启动本地 Flask 服务，默认地址为 `http://127.0.0.1:5000/` |
| `backend/app/__init__.py` | `create_app(config_overrides=None)` | 创建 Flask 应用，加载配置、初始化数据库、启动后台任务、注册路由和错误处理 |
| `backend/app/config.py` | `Config` | 定义数据目录、上传目录、数据库路径、Token 有效期、上传大小、WebSocket 端口和允许文件类型 |
| `backend/app/errors.py` | `ServiceError` | 统一业务异常，包含错误码、错误信息、HTTP 状态码和详情 |

### 2. 认证与权限

| 文件 | 函数 | 功能 |
| --- | --- | --- |
| `auth.py` | `hash_password(password)` | 使用安全哈希保存密码 |
| `auth.py` | `verify_password(password, password_hash)` | 校验登录密码 |
| `auth.py` | `issue_token(user)` | 签发登录 Token |
| `auth.py` | `read_token(token)` | 解析并校验 Token 有效期 |
| `auth.py` | `require_auth(permission=None)` | Flask 装饰器，校验 Bearer Token 和角色权限 |
| `services.py` | `authenticate_user(username, password, captcha, ip_addr)` | 登录认证，返回 Token、用户信息和过期时间 |
| `services.py` | `role_permissions(role_code)` | 查询角色权限集合 |
| `services.py` | `user_has_permission(role_code, permission)` | 判断角色是否具备指定权限 |

### 3. 模板管理

| 文件 | 函数 | 功能 |
| --- | --- | --- |
| `documents.py` | `extract_template_text(file_path)` | 从 `md/txt/docx/pptx` 模板中提取预览文本 |
| `documents.py` | `extract_placeholders(template_text)` | 提取 `{{ placeholder }}` 格式的模板占位符 |
| `services.py` | `list_templates(template_type, keyword, page, size)` | 分页查询模板 |
| `services.py` | `create_template(upload_file, template_type, template_name, rules_json, user_id)` | 上传模板，保存元数据、格式规则、占位符和初始版本 |
| `services.py` | `get_template_detail(template_id)` | 查询模板详情和版本历史 |
| `services.py` | `upload_template_version(template_id, upload_file, change_log, rules_json, user_id, template_name)` | 给已有模板上传新版本 |
| `services.py` | `rollback_template_version(template_id, version_no, user_id)` | 将模板回滚到指定历史版本 |

### 4. 教学方案与课件生成

| 文件 | 函数 | 功能 |
| --- | --- | --- |
| `documents.py` | `load_knowledge_base()` | 读取内置水利知识库 |
| `documents.py` | `build_teaching_plan(params, template_meta)` | 根据课程参数、模板类型和知识库生成教学方案结构 |
| `documents.py` | `render_plan_markdown(plan, template_text)` | 将教学方案渲染为 Markdown |
| `documents.py` | `render_plan_html(plan)` | 将教学方案渲染为 HTML 预览 |
| `documents.py` | `build_courseware(plan, template_meta, resource_items)` | 根据教学方案和资源生成课件页面结构 |
| `documents.py` | `render_courseware_html(courseware)` | 将课件结构渲染为 HTML 预览 |
| `documents.py` | `build_docx(path, paragraphs, title)` | 生成基础 DOCX 文件 |
| `office.py` | `fill_word_template(template_path, output_path, replacements)` | 高保真填充 Word 模板占位符 |
| `office.py` | `fill_ppt_template(template_path, output_path, replacements)` | 高保真填充 PowerPoint 模板占位符 |
| `office.py` | `slides_to_pptx(slides, output_path)` | 根据课件结构生成 PPTX |
| `services.py` | `create_plan_task(user_id, payload)` | 创建教学方案生成任务 |
| `services.py` | `create_courseware_task(user_id, payload)` | 创建课件生成任务 |
| `services.py` | `process_task(task_id)` | 后台执行任务，推进 `RUNNING → GENERATING → VALIDATING → SUCCESS/FAILED` |
| `services.py` | `cancel_task(task_id, user_row)` | 取消运行中的任务 |
| `services.py` | `retry_task(task_id, user_row)` | 重试失败或已取消任务 |

### 5. 格式校验、人工编辑与导出

| 文件 | 函数 | 功能 |
| --- | --- | --- |
| `documents.py` | `validate_plan(plan, rules)` | 校验教学方案目标数量、流程完整度、总结等规则 |
| `documents.py` | `validate_courseware(courseware, rules)` | 校验课件页数、标题、单页要点数量等规则 |
| `services.py` | `validate_target(target_id, target_type, user_row)` | 对指定方案或课件执行格式校验并保存结果 |
| `services.py` | `get_generated_content(target_id, target_type, user_row)` | 读取已生成的方案/课件结构化 JSON |
| `services.py` | `update_generated_content(target_id, target_type, payload, user_row)` | 保存人工编辑内容，重新生成预览文件和导出源文件 |
| `office.py` | `docx_to_pdf(source_path, target_path)` | 将 Word 文档转换为 PDF，需要本机 Office 支持 |
| `office.py` | `pptx_to_pdf(source_path, target_path)` | 将 PowerPoint 转换为 PDF，需要本机 Office 支持 |
| `services.py` | `create_export(target_id, requested_format, expiry_days, share_scope, user_id, max_downloads)` | 创建导出文件和分享链接 |
| `services.py` | `ensure_not_expired(export_row)` | 校验分享链接是否过期或超过下载次数 |
| `services.py` | `increase_download_count(export_id)` | 记录导出文件下载次数 |

### 6. 资源、审计与实时进度

| 文件 | 函数 | 功能 |
| --- | --- | --- |
| `services.py` | `save_resource(upload_file, resource_type, tags, user_id)` | 上传教学资源并计算 SHA256 校验值 |
| `services.py` | `list_resources(resource_type, keyword, page, size)` | 查询资源列表 |
| `services.py` | `record_audit(user_id, action, target_type, target_id, result_status, detail, ip_addr)` | 写入审计日志 |
| `services.py` | `list_audit_logs(keyword, action, page, size)` | 管理员查询审计日志 |
| `realtime.py` | `bootstrap_progress_socket(app)` | 启动 WebSocket 推送服务 |
| `realtime.py` | `notify_user(user_id, payload)` | 向指定用户推送任务进度事件 |
| `realtime.py` | `progress_socket_settings(app)` | 返回实时进度服务配置 |

## 六、RESTful API 设计

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | 用户登录 |
| `GET` | `/api/v1/runtime/context` | 获取当前用户、权限和 WebSocket 配置 |
| `GET` | `/api/v1/templates` | 查询模板列表 |
| `POST` | `/api/v1/templates/upload` | 上传模板 |
| `GET` | `/api/v1/templates/{id}` | 查询模板详情和版本历史 |
| `POST` | `/api/v1/templates/{id}/versions` | 上传模板新版本 |
| `POST` | `/api/v1/templates/{id}/rollback` | 回滚模板版本 |
| `POST` | `/api/v1/generation/plans` | 创建教学方案生成任务 |
| `POST` | `/api/v1/generation/coursewares` | 创建课件生成任务 |
| `GET` | `/api/v1/tasks` | 查询任务列表 |
| `GET` | `/api/v1/tasks/{id}` | 查询任务详情 |
| `POST` | `/api/v1/tasks/{id}/cancel` | 取消任务 |
| `POST` | `/api/v1/tasks/{id}/retry` | 重试任务 |
| `GET` | `/api/v1/content/{targetType}/{targetId}` | 读取生成结果 JSON |
| `PATCH` | `/api/v1/content/{targetType}/{targetId}` | 保存人工编辑内容并重新生成 |
| `POST` | `/api/v1/validation/format` | 执行格式校验 |
| `GET` | `/api/v1/resources` | 查询教学资源 |
| `POST` | `/api/v1/resources/upload` | 上传教学资源 |
| `GET` | `/api/v1/users` | 管理员查询用户 |
| `POST` | `/api/v1/users` | 管理员创建用户 |
| `PATCH` | `/api/v1/users/{id}` | 管理员更新用户 |
| `GET` | `/api/v1/audit-logs` | 管理员查询审计日志 |
| `POST` | `/api/v1/exports` | 创建导出文件和分享链接 |
| `GET` | `/api/v1/exports/{id}/download` | 登录用户下载导出文件 |
| `GET` | `/api/v1/previews/{targetType}/{targetId}` | 查看 HTML 预览 |
| `GET` | `/share/{shareToken}` | 通过分享链接下载文件 |

## 七、前端工作台设计

前端位于 `backend/web/`，采用原生 HTML/CSS/JavaScript 实现单页工作台，便于本地直接演示。

| 文件 | 主要内容 |
| --- | --- |
| `dashboard.html` | 页面结构，包含登录区、指标区、模板中心、版本管理、方案生成、课件生成、资源管理、用户管理、任务中心、人工编辑、结果预览和审计日志 |
| `assets/dashboard.css` | 视觉样式、响应式布局、卡片、按钮、表单、任务进度条、Toast 等 |
| `assets/dashboard-v2.js` | 前端状态、接口请求、登录、模板渲染、任务渲染、生成提交、导出下载、WebSocket 连接、人工编辑和审计日志 |

`dashboard-v2.js` 中的主要函数：

| 函数 | 功能 |
| --- | --- |
| `cacheElements()` | 缓存页面 DOM 节点 |
| `bindEvents()` | 绑定登录、生成、上传、编辑、导出等交互事件 |
| `api(path, options)` | 封装 Fetch 请求，自动携带 Token |
| `handleLogin(event)` | 登录并保存 Token |
| `loadDashboard()` | 加载模板、资源、任务、用户、审计等工作台数据 |
| `renderTemplates()` | 渲染模板卡片 |
| `renderTasks()` / `renderTaskCard(task)` | 渲染任务列表、进度条和操作按钮 |
| `handlePlanSubmit(event)` | 提交教学方案生成参数 |
| `handleCoursewareSubmit(event)` | 提交课件生成参数 |
| `loadTaskIntoEditor(task)` | 将成功任务载入人工编辑器 |
| `handleEditorSave(event)` | 保存人工编辑后的 JSON 并触发重新生成 |
| `runExport(task, format)` | 调用导出接口并下载文件 |
| `connectProgressSocket()` | 建立 WebSocket 任务进度连接 |
| `renderAudits()` | 渲染管理员审计日志 |

## 八、权限设计

| 角色 | 默认权限 |
| --- | --- |
| `ADMIN` 管理员 | 模板管理、资源管理、生成、校验、导出、用户管理、审计日志、人工编辑 |
| `TEACHER` 教师 | 模板管理、资源管理、生成、校验、导出、人工编辑 |
| `STUDENT` 学生 | 模板查看、基础生成、资源查看 |

敏感接口通过 `@require_auth(permission)` 校验角色权限。生成结果、预览和导出下载会进一步校验资源归属，管理员可管理全部数据，普通用户只能访问自己的任务结果。

## 九、运行方式

### 1. 安装依赖

```powershell
cd E:\big3\水利系统
pip install -r backend\requirements.txt
```

如果使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 2. 启动项目

```powershell
python backend\run.py
```

或使用你的 Python 路径：

```powershell
& D:\pythoninter\python.exe E:\big3\水利系统\backend\run.py
```

浏览器打开：

```text
http://127.0.0.1:5000/
```

### 3. 示例账号

```text
管理员：admin / admin123 / 验证码 2026
教师：teacher / teacher123 / 验证码 2026
学生：student / student123 / 验证码 2026
```

## 十、测试方式

```powershell
python -m unittest backend.tests.test_api
node --check backend\web\assets\dashboard-v2.js
```

当前测试覆盖：

- 登录认证与默认角色
- 模板查询、模板上传、模板版本上传和回滚
- 教学方案生成、课件生成、预览、校验和导出
- 生成内容人工编辑后重新生成
- 分享链接有效期和最大下载次数限制
- 用户管理和审计日志

## 十一、导出与 Office 说明

- 教学方案支持：`docx`、`html`、`json`、`md`、`txt`、`pdf`
- 教学课件支持：`pptx`、`html`、`json`、`txt`、`pdf`
- Word/PPT 模板占位符支持 `{{ course_name }}`、`{{ 教学目标 }}` 等形式
- PDF 导出依赖本机 Microsoft Word/PowerPoint 自动化能力；如果本机没有 Office，对应接口会返回明确错误提示
- 如果没有上传 Word/PPT 模板，系统会使用结构化内容生成基础 DOCX/PPTX 或 HTML 预览

## 十二、扩展方向

后续可按详细设计报告继续增强：

- 将当前 Flask 单体拆分为 `Spring Boot 业务服务 + Python 生成服务`
- 使用 MySQL/PostgreSQL 替换 SQLite
- 使用 Redis 缓存模板元数据、权限信息和任务进度
- 使用 Celery/RQ 等任务队列替代内存队列
- 引入 Vue3 + Element Plus 重构前端组件
- 增加模板插件、校验规则插件和更多导出转换器
- 增加 HTTPS、CSRF 防护、对象存储和生产环境部署脚本

## 十三、GitHub 协作说明

完整上传和迭代步骤见：[docs/GITHUB_UPLOAD.md](docs/GITHUB_UPLOAD.md)。

常用命令：

```powershell
git pull
git status
git add .
git commit -m "Update project"
git push
```

本项目默认不提交本地运行数据、数据库、上传资源、生成文件、导出文件和 Office 设计报告。请确认 `git status` 中没有不希望公开的文件后再提交。
