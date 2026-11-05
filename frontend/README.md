# 前端（Taro 4 + React + TypeScript）

微信小程序“一话一懂”，UI 按 `prototype/01-core-flow.html` 与 `00-style-board.html` 还原；“我的”、历史记录按 `03-review-and-stats.html` 第 1、4、6 屏。

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

不要改提交进仓库的 `.env.development`，在 `frontend/` 下新建 `.env.development.local`（已被 `*.local` 忽略，优先级更高）覆盖后端地址：

```
TARO_APP_API_BASE="http://192.168.1.10:8000"   # 换成电脑 Wi-Fi 的局域网 IP（ipconfig 查看）
```

改完重启 `npm run dev:weapp`（env 只在构建启动时读取）。后端用 `--host 0.0.0.0` 启动，手机和电脑连同一个 Wi-Fi；Windows 防火墙需放行 8000 端口。回到模拟器调试时删掉该文件即可。

> iOS 上 `wx.loadFontFace` 只支持 HTTPS。HTTP 环境下漫画标题字体加载失败时，会自动退回系统粗体，不影响功能。

### 上线前

- `.env.production` 的 `TARO_APP_API_BASE` 改成已备案的 HTTPS 域名。
- 小程序后台把该域名加入 **request 合法域名** 和 **downloadFile 合法域名**（字体从后端 `/static/fonts` 加载）。
- `project.config.json` 的 `urlCheck` 改回 `true`。

## 脚本

| 命令 | 说明 |
| --- | --- |
| `npm run dev:weapp` / `build:weapp` | 小程序开发（监听）/ 生产构建。`build:weapp` 走 production 模式、读 `.env.production`；本地一次性构建用 `npx taro build --type weapp --mode development` |
| `npm run dev:h5` | H5 调试（http://localhost:10086），方便在浏览器里看效果 |
| `npm test` | 纯逻辑单测（`node:test` + tsx）：判题、等级经验、会话、格式化、折行、图形 |
| `npm run typecheck` | TypeScript 类型检查 |
| `npm run gen:icons` | 修改 `src/assets/icons.ts` 后重新生成 `src/styles/icons.generated.scss` 与 `tab-icons.generated.scss`（单测会校验是否最新） |

## 目录

```text
src/
  pages/        index 首页（标签“闯关”）· generating 出题中/失败 · overview 本话目录 · quiz 闯关
                clear 通关结算 · report 复盘报告（?quiz_id= 时为历史回看）· poster 分享海报
                me 我的（标签）· review 复习（标签，本期占位）· history 历史记录
  custom-tab-bar/  自定义底部标签栏（闯关 / 复习 / 我的）
  components/   NavBar（按胶囊按钮计算的自定义导航栏）、ui（按钮、选项、讲解框、拟声词、弹窗…）、TabPage、Empty
  core/         纯逻辑，不依赖 Taro，可单测
  services/     请求封装（可中止）、登录态（auth）、账号同步（account）、报告生成（report-flow）、API、字体、海报
  store/        Zustand；个人资料 / 后端档案缓存 / 草稿 / 闯关会话持久化到本地，支持中断续答
  assets/       图标（SVG → data URI）
tests/          node:test 单测
```

## 实现说明

- `designWidth: 375`：样式里的 px 与原型 1:1，构建时换算为 rpx。
- 小程序不支持内联 SVG：图标、爆炸框、太阳码生成为 CSS 类（`icons.generated.scss`，base64 data URI 背景），不放在内联 style 里，避免每次 setData 传输大段 base64；判题打勾/打叉的“描线”动画用 `clip-path` 揭开实现，时序与原型一致。
- 经验门槛：路人 0 / 龙套 150 / 配角 400 / 主角 1000 / 传说 2000；每答对一格 +10 经验、+5 金币，答错不扣。
- 海报小程序码目前是太阳码占位图；接入真码需要后端用 AppSecret 调 `wxacode.getUnlimited`，并且小程序已发布。

## 用户系统

- **静默登录**：App 启动时 `wx.login()` 拿 code → `POST /user/login` 换 JWT，存在本地（`yhyd.token`）。所有请求自动带 `Authorization`；后端返回 4010 时清掉 token、静默重登一次再重发（`core/reauth.ts`）。登录失败不拦用户：出题、报告照常匿名可用，只是不保存记录。
- **数据来源**：登录后经验、金币、话数以后端为准（启动、回到首页 / 我的、报告生成后同步）；结算页仍按同一规则先在本地算，升级动画不用等接口。
- **落库时机**：结算页一进入就在后台请求报告接口——后端先保存答题记录并结算经验，再生成 AI 复盘。用户直接“回首页”不看报告，记录也不会丢。
- **改昵称**：点“我的”页头像或昵称，弹窗里用 `type="nickname"` 输入框（微信头像昵称填写能力，键盘上方可选微信昵称），按微信文档用 form 提交读取最终值。头像按原型显示昵称首字，本期不做头像上传。
- **标签栏**：原生 tabBar 画不出原型样式，用自定义 tabBar。它是独立组件：`app.wxss` 对它不生效，图标单独生成 `styles/tab-icons.generated.scss`；它固定在页面之上，标签页底部用 `TabBarSpace` 留位，页面弹窗时用 `setTabBarHidden` 收起（`wx.hideTabBar` 管不到自定义 tabBar）。
- **历史记录**：已完结的话来自后端（分页）；“没答完”只有本机那一条可续答的会话。点已完结的一话进入报告页历史模式，AI 复盘当时失败的可以在那里重试补上。

### 开发者工具缓存

改了跨页面共用模块的导出后，模拟器偶尔会出现“旧页面代码 + 新公共包”的错配（如 `(0, o.G) is not a function`、页面空白）。清编译缓存后重开项目即可：

```bash
cli.bat cache --clean compile --project <frontend 目录>
cli.bat close --project <frontend 目录>
cli.bat open --project <frontend 目录>
```
