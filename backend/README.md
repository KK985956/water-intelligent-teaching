# 水利智能教学应用后端 MVP

这个版本是根据需求分析、概要设计、详细设计三份文档落出来的一个可运行后端骨架，优先打通了以下主链路：

- 前端工作台首页
- 用户登录认证与基础 RBAC
- 模板列表、模板上传、模板详情
- 模板版本上传、版本历史与回滚
- 教学方案异步生成
- 课件异步生成
- WebSocket 实时进度推送
- 格式校验
- 资源上传
- 用户管理
- 导出与分享

## 技术取舍

详细设计里给的是 `Spring Boot + Python` 双服务方案。当前仓库没有现成工程，且本机现成依赖以 `Flask` 为主，所以这里先实现了单体 Python 后端，但接口、任务流、模块边界都按详细设计保留，后续可以再拆服务。

## 启动

```powershell
python backend/run.py
```

默认地址：

```text
http://127.0.0.1:5000
```

浏览器直接打开根路径 `/` 即可进入 Web 工作台。

默认实时进度端口：

```text
ws://127.0.0.1:8765
```

## 示例账号

- 管理员：`admin / admin123`
- 教师：`teacher / teacher123`
- 学生：`student / student123`
- 演示验证码：`2026`

## 已实现接口

- `POST /api/v1/auth/login`
- `GET /api/v1/templates`
- `POST /api/v1/templates/upload`
- `GET /api/v1/templates/{id}`
- `POST /api/v1/templates/{id}/versions`
- `POST /api/v1/templates/{id}/rollback`
- `GET /api/v1/runtime/context`
- `GET /api/v1/roles`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{id}`
- `GET /api/v1/resources`
- `POST /api/v1/generation/plans`
- `POST /api/v1/generation/coursewares`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{id}`
- `POST /api/v1/validation/format`
- `POST /api/v1/resources/upload`
- `POST /api/v1/exports`
- `GET /api/v1/exports/{id}/download`
- `GET /api/v1/previews/{targetType}/{targetId}`
- `GET /share/{shareToken}`

## 导出说明

- 教学方案支持：`docx/html/json/md/txt/pdf`
- 教学课件支持：`pptx/html/json/txt/pdf`
- 教学方案 `pdf` 导出依赖本机 Word 自动化
- 教学课件 `pptx/pdf` 导出依赖本机 PowerPoint 自动化

如果机器上没有对应的 Office 组件，接口会返回明确错误提示。

## 前端功能

- 登录后查看模板、资源、最近任务
- 模板新版本上传、历史版本查看与回滚
- 填写教学方案参数并发起生成
- 基于已成功的方案继续生成课件
- 通过 WebSocket 实时接收任务状态更新
- 在线预览方案/课件 HTML 结果
- 上传案例、图片、视频、公式、习题资源
- 管理员可直接在工作台创建、停用、改角色、重置用户密码
- 触发格式校验、导出并下载文件

## 测试

```powershell
python -m unittest backend.tests.test_api
```
