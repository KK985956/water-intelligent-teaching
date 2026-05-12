# GitHub 上传与迭代操作说明

## 上传前需要确认

1. 提交代码前先运行测试：

```powershell
python -m unittest backend.tests.test_api
node --check backend\web\assets\dashboard-v2.js
```

2. 不要提交运行期文件：

```text
backend/storage/
backend/**/__pycache__/
*.db
*.db-journal
.env
*.docx
*.doc
*.pptx
*.ppt
```

这些内容已经写入根目录 `.gitignore`。

3. 本地设计报告、Office 文档等资料默认不提交到 GitHub。如果确实要公开某份文档，需要先从 `.gitignore` 中移除对应规则，再单独提交。

如果文档已经被提交过，只追加 `.gitignore` 不会自动移除历史提交中的文件，需要执行 `git rm --cached` 后再提交一次。

## 第一次上传

在 GitHub 网站新建一个空仓库，例如：

```text
water-intelligent-teaching
```

仓库创建时不要勾选自动生成 README、.gitignore 或 License，因为本地已经准备好了。

然后在 PowerShell 中进入项目根目录：

```powershell
cd E:\big3\水利系统
```

初始化 Git：

```powershell
git init
git branch -M main
git add .
git commit -m "Initial water teaching application"
```

绑定远程仓库并推送：

```powershell
git remote add origin https://github.com/你的用户名/water-intelligent-teaching.git
git push -u origin main
```

## 后续迭代流程

每次开始一个功能，建议单独建分支：

```powershell
git switch -c feature/template-versioning
```

开发完成后查看变更：

```powershell
git status
git diff
```

运行测试：

```powershell
python -m unittest backend.tests.test_api
node --check backend\web\assets\dashboard-v2.js
```

提交并推送：

```powershell
git add .
git commit -m "Add template version rollback"
git push -u origin feature/template-versioning
```

然后在 GitHub 页面创建 Pull Request，确认 CI 通过后合并到 `main`。

## 常见命令

查看当前状态：

```powershell
git status
```

拉取远端最新代码：

```powershell
git pull --rebase origin main
```

查看提交历史：

```powershell
git log --oneline --decorate --graph --all
```

临时保存未完成改动：

```powershell
git stash push -m "work in progress"
git stash pop
```

## GitHub Token 说明

如果使用 HTTPS 推送，GitHub 通常会要求使用 Personal Access Token 代替账号密码。推荐权限只勾选当前仓库需要的 `Contents: Read and write`。

也可以安装 GitHub CLI 后登录：

```powershell
gh auth login
```
