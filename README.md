# 水利智能教学应用

这是一个面向水利课程教学资料生成的 Web 应用原型，已实现模板管理、教学方案生成、课件生成、资源管理、格式校验、导出分享、用户管理和 WebSocket 任务进度推送。

## 项目结构

```text
.
├── backend/                 # Flask 后端与前端静态工作台
│   ├── app/                 # 业务服务、路由、数据库、Office 导出与实时推送
│   ├── data/                # 内置知识库和示例模板
│   ├── tests/               # 后端接口测试
│   ├── web/                 # 工作台页面与前端资源
│   ├── requirements.txt     # Python 依赖
│   └── run.py               # 本地启动入口
└── docs/                    # 迭代、发布、GitHub 操作说明
```

`backend/storage/` 是运行时目录，包含数据库、上传资源、生成结果和导出文件，不应提交到 GitHub。
本地设计报告、Office 文档等资料默认不提交到 GitHub，可按需要单独备份。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python backend\run.py
```

打开：

```text
http://127.0.0.1:5000/
```

示例账号：

```text
admin / admin123
teacher / teacher123
student / student123
验证码：2026
```

## 测试

```powershell
python -m unittest backend.tests.test_api
node --check backend\web\assets\dashboard-v2.js
```

## GitHub 上传

完整步骤见 [docs/GITHUB_UPLOAD.md](docs/GITHUB_UPLOAD.md)。
