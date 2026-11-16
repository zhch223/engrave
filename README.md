# 星语铭 (engrave.ren)

一座以星光为墨、以记忆为碑的数字纪念网站——用于纪念那些已经离开的人。

本项目为前后端分离版本：前端为纯静态站点，后端（Python 标准库，零第三方依赖）提供留言 API、资料卡管理、投稿接收与管理后台，单端口部署，支持局域网 / 端口映射访问。

## 本地运行

```bash
python backend/server.py
```

启动后只有一个服务，端口 8080：

- 前台站点：http://127.0.0.1:8080/
- 管理后台：http://127.0.0.1:8080/admin （需登录）
- 手机访问：同一局域网内访问 `http://<电脑IP>:8080/`，或通过端口映射入口访问（留言、投稿均为同源请求，任何入口通用）

账号配置在 `backend/auth.json`（首次启动自动生成默认账号 `admin` / `admin123`，请尽快修改）。

## 目录结构

```
/
├── index.html              # 首页 - 显示纪念人物列表
├── profile.html            # 个人纪念页面
├── contribute.html         # 投稿提交页（任意类型文件，单文件 ≤ 200MB）
├── about.html              # 关于页面
├── compliance.html         # 合规声明
├── 404.html                # 404 错误页面
├── css/
│   └── style.css          # 样式文件（含手机端响应式适配）
├── js/
│   ├── main.js            # 首页 JavaScript
│   ├── profile.js         # 个人页面 JavaScript
│   └── guestbook.js       # 留言板组件（替代原 Utterances 评论）
├── images/
│   └── default-avatar.svg # 默认头像
├── data/
│   ├── profiles.json      # 纪念人物 ID 列表
│   └── people/
│       └── [人物ID]/
│           ├── resources/
│           │   └── xxx.xxx # 资源文件（照片，视频等）
│           ├── info.json  # 基本信息
│           ├── bio.md     # 生平介绍 (Markdown)
│           └── avatar.jpg # 头像图片
└── backend/
    ├── server.py          # 后端：静态服务 + API + 管理后台（单端口全包）
    ├── admin.html         # 管理后台界面（留言 / 资料卡 / 投稿 三大模块）
    ├── auth.json          # 登录账号配置
    ├── messages.json      # 留言数据
    ├── contributions.json # 投稿登记
    └── contributions/     # 投稿文件存放处
```

## 管理后台

访问 `/admin` 登录后可使用三个模块：

- **留言管理**：统计概览、按人物/关键词筛选、删除留言、清空
- **资料卡管理**：直接编辑 info.json 各字段与 bio.md 生平、上传头像、新建/删除人物（保存后前台刷新即生效）
- **投稿管理**：查看投稿列表（文件名/大小/投稿人/备注/IP/时间），在线下载、删除

留言与投稿接口为公开接口；所有管理接口需登录（会话 Cookie，24 小时有效）。

## 添加新人物

推荐在管理后台「资料卡管理」中直接新建；也可手动操作：

1. 在 `data/people/` 下创建新文件夹，文件夹名称即为人物 ID（请使用全小写）
2. 创建 `info.json` - 基本信息
3. 创建 `bio.md` - 生平介绍（支持完整 Markdown 语法）
4. 添加 `avatar.jpg` - 头像图片（可选）

### info.json 格式

```json
{
  "id": "example",
  "name": "示例人物",
  "handle": "example",
  "aliases": "示例",
  "location": "示例地点",
  "birthDate": "2000-01-01",
  "passDate": "2024-01-01",
  "summary": "一言总结/引用语句",
  "websites": [
    "[网站名称](https://example.com)",
    "[B站](https://bilibili.com)",
    "[GitHub](https://github.com)"
  ],
  "sources": [
    "[新闻报道](https://example.com/news)",
    "[纪念文章](https://example.com/memorial)"
  ]
}
```

**字段说明：**
- `id` - 人物唯一标识（文件夹名称）（请使用全小写）
- `name` - 姓名
- `handle` - 昵称/用户名
- `aliases` - 别名（多个用逗号分隔）
- `location` - 地点
- `birthDate` - 出生日期 (YYYY-MM-DD)
- `passDate` - 离开日期 (YYYY-MM-DD)
- `summary` - 一言总结/引用（显示在首页卡片）
- `websites` - 网站链接数组，格式：`[显示名称](链接)`
- `sources` - 引用资料链接数组，格式：`[显示名称](链接)`

### 更新人物列表

在 `data/profiles.json` 中添加人物 ID：

```json
["example", "gqt", "zhangyubaka", "新人物ID"]
```

## 投稿系统

前台「投稿」页（导航栏入口）可提交任意类型文件，单文件上限 200MB，支持点击选择与拖拽上传，带实时进度。后端以 multipart 方式接收，超限直接拒绝（HTTP 413）。投稿内容仅管理员在后台可见。

## 留言系统

由 `js/guestbook.js` 提供留言板组件（替代原 Utterances / GitHub Issues 评论），资料页底部渲染，昵称可选（默认匿名），内容限 500 字，HTML 转义防 XSS，数据持久化于 `backend/messages.json`。

## 资源引用

### 图片引用

使用标准 Markdown 语法引用图片：

```markdown
![图片描述](https://raw.githubusercontent.com/engrave-ren/engrave-ren/main/data/people/[人物ID]/resources/图片文件名.jpg)
```

---

### 视频引用

使用链接方式引用视频文件：

```markdown
[视频标题](https://cdn.jsdelivr.net/gh/engrave-ren/engrave-ren@main/data/people/[人物ID]/resources/视频文件名.mp4)
```

---

### 说明

- **图片**：使用 `![描述](链接)` 语法，图片会直接显示在页面中
- **视频**：使用 `[标题](链接)` 语法，点击链接可在浏览器中打开播放
- 本地部署时也可用相对路径直接引用站内资源，如 `data/people/[人物ID]/resources/xxx.jpg`
- 将 `[人物ID]` 替换为实际的人物文件夹名称
- 将文件名替换为实际的资源文件名
