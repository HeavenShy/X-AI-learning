# 前端（Taro 4 + React + TypeScript）

微信小程序“一话一懂”，UI 按 `prototype/01-core-flow.html` 与 `00-style-board.html` 还原。

## 本地运行（微信开发者工具）

1. 先启动后端（见 `backend/README.md`），确认 http://127.0.0.1:8000/api/v1/health 能访问。
2. 安装依赖并编译：

   ```bash
   cd frontend
   npm install
   npm run dev:weapp      # 监听编译到 dist/
   ```

3. 微信开发者工具 → 导入项目 → 选择 `frontend` 目录（`project.config.json` 已指向 `dist/`）。
4. 本地开发已关闭“校验合法域名”（`urlCheck: false`），可以直接请求 `http://127.0.0.1:8000`。

### 真机调试

把 `.env.development` 里的 `TARO_APP_API_BASE` 改成电脑的局域网 IP，例如 `http://192.168.1.10:8000`，后端用 `--host 0.0.0.0` 启动，手机和电脑连同一个 Wi-Fi。

> iOS 上 `wx.loadFontFace` 只支持 HTTPS。HTTP 环境下漫画标题字体加载失败时，会自动退回系统粗体，不影响功能。

### 上线前

- `.env.production` 的 `TARO_APP_API_BASE` 改成已备案的 HTTPS 域名。
- 小程序后台把该域名加入 **request 合法域名** 和 **downloadFile 合法域名**（字体从后端 `/static/fonts` 加载）。
- `project.config.json` 的 `urlCheck` 改回 `true`。

## 脚本

| 命令 | 说明 |
| --- | --- |
| `npm run dev:weapp` / `build:weapp` | 小程序开发 / 生产构建 |
| `npm run dev:h5` | H5 调试（http://localhost:10086），方便在浏览器里看效果 |
| `npm test` | 纯逻辑单测（`node:test` + tsx）：判题、等级经验、会话、格式化、折行、图形 |
| `npm run typecheck` | TypeScript 类型检查 |

## 目录

```text
src/
  pages/        index 首页 · generating 出题中/失败 · overview 本话目录 · quiz 闯关
                clear 通关结算 · report 复盘报告 · poster 分享海报
  components/   NavBar（按胶囊按钮计算的自定义导航栏）、ui（按钮、选项、讲解框、拟声词、弹窗…）
  core/         纯逻辑，不依赖 Taro，可单测
  services/     请求封装（可中止）、API、字体加载、海报 Canvas 绘制
  store/        Zustand；个人资料 / 草稿 / 闯关会话持久化到本地，支持中断续答
  assets/       图标（SVG → data URI）
tests/          node:test 单测
```

## 实现说明

- `designWidth: 375`：样式里的 px 与原型 1:1，构建时换算为 rpx。
- 小程序不支持内联 SVG：图标、爆炸框、太阳码用 SVG data URI 作背景；判题打勾/打叉的“描线”动画用 `clip-path` 揭开实现，时序与原型一致。
- 经验门槛：路人 0 / 龙套 150 / 配角 400 / 主角 1000 / 传说 2000；每答对一格 +10 经验、+5 金币，答错不扣。
- 海报小程序码目前是太阳码占位图；接入真码需要后端用 AppSecret 调 `wxacode.getUnlimited`，并且小程序已发布。
