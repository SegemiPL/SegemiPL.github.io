# 博客项目说明（供 AI / 协作者快速上手）

本文档描述本仓库的定位、目录结构、构建与发布方式。修改博客或站点配置时请先阅读本节。

## 项目是什么

- **类型**：个人静态博客 / 文档站。
- **生成器**：[Zensical](https://zensical.org/)（类 MkDocs Material 体验，配置为 `zensical.toml`）。
- **内容语言**：站点界面语言为中文（`language = "zh"`），文章以 Markdown 为主。
- **线上地址**：`https://SegemiPL.github.io/`（`site_url` 与 GitHub Pages 用户站一致）。
- **源码仓库**：`https://github.com/SegemiPL/SegemiPL.github.io`（`repo_url` / `repo_name`）。

## 目录结构（重要）

| 路径 | 说明 |
|------|------|
| `zensical.toml` | 站点元数据、导航 `nav`、主题、功能开关等**唯一主配置**。新增顶栏/侧栏入口通常要改这里。 |
| `docs/` | **源内容目录**（Markdown 等）。构建时以此为 `docs_dir`。 |
| `docs/index.md` | 首页。 |
| `docs/blog/` | 博客短文、随笔等（非课程类）；`docs/blog/index.md` 为列表页。 |
| `docs/<主题>/` | 按主题分目录的笔记（如 `docs/hpc/` 对应高性能计算课程），各目录内可有 `index.md` 作索引。 |
| `docs/assets/` | 图片等静态资源（按主题分子目录，如 `docs/assets/hpc/`）。 |
| `docs/*.md` | 根目录独立页面（可选）。 |
| `site/` | **构建输出**（`zensical build` 生成）。已列入 `.gitignore`，一般不入库；CI 在干净环境中生成并上传。 |
| `scripts/` | Obsidian 导入、批量导入、内容卡片/元数据辅助与测试脚本。脚本本身入库；机器本地配置放 `scripts/local/`。 |
| `.github/workflows/docs.yml` | GitHub Actions：推送 `main`/`master` 时安装 Zensical、构建、部署到 GitHub Pages。 |
| `.venv/` | 本地 Python 虚拟环境（已忽略）。 |

## 发布新内容的典型流程

1. **课程/主题笔记**：在对应的 `docs/<主题>/` 下新建 `.md`（例如 `docs/hpc/`），并在该主题的 `index.md` 中增加链接；侧栏 `nav` 中通常**只挂该主题的 `index.md`**，不把每篇笔记单独列在导航里。若为新主题，新建 `docs/<主题>/index.md` 并在 `zensical.toml` 的 `nav` 中增加一条指向该 `index.md` 的入口。
2. **博客短文**（非课程）：在 `docs/blog/` 下新建文章，并更新 `docs/blog/index.md`。
3. 文件开头使用 YAML frontmatter（与现有文章一致），常用字段：`date`、`icon`、`description`。
4. 图片等资源放在 `docs/assets/`（或主题子目录）下，正文中使用相对 `docs/` 的路径。
5. 本地预览：`zensical serve`；提交并推送后由 Actions 构建部署。

## 本地开发命令

```bash
# 建议使用项目已有 venv 或自行创建后：
pip install 'zensical>=0.0.28'

# 本地预览（默认会监听变更）
zensical serve

# 干净构建（与 CI 接近）
zensical build --clean
```

构建产物目录名为 `site`（与 workflow 中 `upload-pages-artifact` 的 `path: site` 一致）。

## CI / 部署要点

- 触发分支：`main` 或 `master`。
- 安装：`pip install 'zensical>=0.0.28'`。
- 构建：`zensical build --clean`。
- 部署：将 `site` 作为 Pages artifact 上传；需仓库开启 GitHub Pages 并使用 Actions 作为来源。

## 自定义与扩展（当前状态）

- 主题 variant 默认 **modern**（`[project.theme]` 中 `variant = "classic"` 被注释）。
- `extra_css` / `extra_javascript`、`custom_dir`（模板覆盖）、`logo` / `favicon` 等均在 `zensical.toml` 中留有注释说明，可按官方文档启用。
- 数学公式：全站 MathJax 配置在 `docs/javascripts/extra.js`，通过 `zensical.toml` 的 `extra_javascript` 加载；文章中直接写 `$...$` / `$$...$$`，不要逐页粘贴 MathJax 脚本。

## 与 AI 协作时的注意点

- **改内容**：主要编辑 `docs/` 下 Markdown，不要改 `site/`（生成物）。
- **改导航或站点信息**：编辑 `zensical.toml` 的 `[project]`、`nav`、`theme` 等。
- **改部署**：编辑 `.github/workflows/docs.yml`。
- 保持与现有文章相同的 frontmatter 与链接风格，避免破坏站内相对链接与 GitHub「编辑」按钮路径（`edit_uri` 指向 `edit/main/docs/`）。

---

*若项目结构或部署方式有变，请同步更新本文件与 `.cursor/rules/blog-project.mdc`。*
