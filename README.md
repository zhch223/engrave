# 星语铭 (engrave.ren)

纪念逝者的网站。原站由晴樱Novi搭建，现在这版是她备考期间由氢氧根重建的，前后端分离，后端只用了 Python 标准库，没有第三方依赖。

仓库描述里的"站长仍是晴樱Novi"，不是客套话。

## 原项目

本站的原始版本出自 [engrave-ren/engrave-ren](https://github.com/engrave-ren/engrave-ren)，由晴樱Novi搭建的纯静态站。原版完整代码保留在本仓库的 [`original` 分支](https://github.com/zhch223/engrave/tree/original)，提交历史原样保留，没有改动。

现在看到的 main 分支是在原版基础上改造的：加了后端、后台管理、留言和投稿系统，页面结构和视觉风格沿用原站。

## 跑起来

```bash
python backend/server.py
```

一个服务全包了，端口 8080：

- 网站本身：http://127.0.0.1:8080/
- 后台：http://127.0.0.1:8080/admin （要登录）
- 手机：同一局域网访问 `http://电脑IP:8080/`，或者走端口映射。留言和投稿都是同源请求，怎么进来都行

账号在 `backend/auth.json`，第一次启动会生成默认的 `admin` / `admin123`，用之前先改掉。

## 文件结构

```
/
├── index.html              # 首页（人物列表、今日生日/祭日）
├── profile.html            # 个人页
├── contribute.html         # 投稿页
├── about.html / compliance.html / 404.html
├── css/style.css          # 全站样式（带手机端适配）
├── js/
│   ├── main.js            # 首页逻辑
│   ├── profile.js         # 个人页逻辑
│   └── guestbook.js       # 留言板
├── data/
│   ├── profiles.json      # 人物 ID 列表
│   └── people/<人物ID>/
│       ├── info.json      # 基本信息
│       ├── bio.md         # 生平（Markdown）
│       ├── avatar.jpg     # 头像
│       └── resources/     # 照片、视频等资料
└── backend/
    ├── server.py          # 后端：静态服务 + API + 管理后台
    ├── admin.html         # 后台界面（留言/资料卡/投稿三个模块）
    ├── auth.json          # 登录账号（不入库）
    ├── messages.json      # 留言数据（不入库）
    └── contributions/     # 投稿文件（不入库）
```

## 后台能干什么

浏览器开 `/admin`，登录后三个标签页：

- 留言管理：看留言、删留言、按人物清空
- 资料卡管理：改 info.json 的字段、写 bio.md、传头像、传资源文件（进 `resources/`）、直接编辑原文件（txt/md/json）
- 投稿管理：看投稿、下载、删

留言和投稿接口是公开的，管理接口全部要登录（会话 24 小时过期）。

## 加新人物

后台「资料卡管理」里点新建就行。想手动加也可以：

1. `data/people/` 下建文件夹，文件夹名就是人物 ID（小写）
2. 写 `info.json`、`bio.md`，头像可选 `avatar.jpg`
3. 把 ID 加进 `data/profiles.json`

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
  "summary": "一句话",
  "websites": [
    "[网站名称](https://example.com)"
  ],
  "sources": [
    "[新闻报道](https://example.com/news)"
  ]
}
```

字段就这些：`id` 是文件夹名，`birthDate`/`passDate` 用 `YYYY-MM-DD`。首页的「今日生日」「今日祭日」靠这两个日期驱动——到月对日就显示，忽略年份。守夜人（还在世的管理员）在 info.json 里加 `"watcher": true`，祭日区会自动跳过。

## bio.md 里放图片和视频

文件先传到该人物的 `resources/`（后台可传，或手动拷进去），然后在 bio.md 里：

```markdown
![照片说明](/data/people/<人物ID>/resources/photo.jpg)
[视频标题](/data/people/<人物ID>/resources/clip.mp4)
```

路径以 `/` 开头。图片会直接显示，视频渲染成链接点开播放。想走外链也可以用 raw.githubusercontent.com（图）和 cdn.jsdelivr.net（视频，快）。

## 投稿

导航栏「投稿」进去，任意类型文件，单个 200MB 封顶，有进度条。传的东西只有后台能看到。

## 数据备份

代码推 GitHub，但下面这些只在本地，建议定期备份：

- `backend/messages.json` —— 所有留言
- `backend/contributions/` 和 `backend/contributions.json` —— 投稿文件
- `backend/auth.json` —— 账号配置（备份时注意别外泄）
- `data/people/` —— 人物资料卡（这个其实也推了 GitHub，但后台改完记得 push）
