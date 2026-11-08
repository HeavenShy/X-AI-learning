# 前端（Taro 4 + React + TypeScript）

微信小程序“一话一懂”，UI 按 `prototype/01-core-flow.html` 与 `00-style-board.html` 还原；“我的”、历史记录按 `03-review-and-stats.html` 第 1、4、6 屏；知识库按 `02-input-and-library.html` 第 7、9、10、12 屏。

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
| `npm test` | 纯逻辑单测（`node:test` + tsx）：判题、等级经验、会话、格式化、折行、图形、知识库（预检 / 状态 / 出处文案） |
| `npm run typecheck` | TypeScript 类型检查 |
| `npm run gen:icons` | 修改 `src/assets/icons.ts` 后重新生成 `src/styles/icons.generated.scss` 与 `tab-icons.generated.scss`（单测会校验是否最新） |

## 目录

```text
src/
  pages/        index 首页（标签“闯关”）· generating 出题中/失败 · overview 本话目录 · quiz 闯关
                clear 通关结算 · report 复盘报告（?quiz_id= 时为历史回看）· poster 分享海报
                me 我的（标签）· review 复习（标签，错题本）· review-answer 重做错题 · history 历史记录
                kb-list 我的知识库 · kb-detail 知识库详情（上传 / 状态 / 删除）· kb-quiz 用知识库出题 · web-quiz 用网页出题 · video-quiz 用视频出题
  custom-tab-bar/  自定义底部标签栏（闯关 / 复习 / 我的）
  components/   NavBar（按胶囊按钮计算的自定义导航栏）、ui（按钮、选项、讲解框、拟声词、弹窗…）、TabPage、Empty、KbNameDialog
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

## 知识库

- **入口**：“我的”页“我的知识库”、首页输入框下的“传文档”都打开 `pages/kb-list`（“贴网址”“贴视频”见下两节）。后端没配 Embedding Key 时接口返回 5000，页面显示“知识库暂时不可用”，文本出题不受影响。
- **列表**（`kb-list`）：顶部“已存资料 x / 50 份”，列表为各知识库（资料数、更新时间）。底部新建（弹窗填名称，建好直接进详情）；长按知识库弹出“改名 / 删除”，删除前确认。
- **详情**（`kb-detail`）：资料与状态（处理中 / 可出题 / 失败 + 原因）。“上传”用 `wx.chooseMessageFile` 从微信聊天里选文件（小程序只能这样拿到文件），先按后端同规则预检扩展名与 20 MB（`core/kb.ts`），再用 `Taro.uploadFile` 上传（multipart，字段 `file`；返回的 data 是字符串需自己解析，见 `services/request.ts`，带 token / 4010 重登见 `services/auth.ts` 的 `authedUpload`）。有资料处理中时每 3 秒刷新一次，处理完或页面隐藏 / 卸载即停。长按资料删除（先确认）。H5 没有 `chooseMessageFile`，只提示去微信里上传。
- **出题设置**（`kb-quiz`）：默认勾选全部可出题资料，未就绪的不能勾并显示状态；选填“想重点学什么”（≤200 字）、题量 3 / 5 / 10。全选时向后端传空 `document_ids`（= 整个库）。开始后进入 `pages/generating`：`GenRequest.kb` 有值时调 `POST /knowledge-bases/{kb_id}/quiz`，步骤文案为“读取资料 / 找到相关片段 / 出题并写讲解”；资料未就绪（4023）、重点不合规（4003）回到设置页提示。成功后与文本出题一样进本话目录、闯关、结算、报告。
- **出处**：知识库出的题每题带 `sources`，闯关页与重做错题页的讲解框（`CaptionBox`）在讲解下方显示“出处：文件名，第 N 页”和原文摘录；文本题 `sources` 为空，显示与之前一致。`Question.sources` 在类型里是可选的：本地存的旧闯关进度没有这个字段。
- 知识库出的一话在报告页点“再来一话”回到知识库列表重新选（题目里没有记录用的是哪个库）。

## 网页出题

- **入口**：首页输入框下的“贴网址”打开 `pages/web-quiz`；首页输入框里整段就是一个链接时，点“开始出题”也会带着链接转过去（`core/web.ts` 的 `isBareUrl`）。
- **链接与预览**（`web-quiz`，原型 02 第 3 屏）：进页面时用 `Taro.getClipboardData` 读剪贴板，里面有链接（能从“【标题】https://… 复制此链接”这类分享文案里抠出来）就自动填好并提示。上线前要在小程序隐私协议里声明剪贴板，否则读取会失败（失败时静默忽略）。输入停下 600ms、失焦或按“前往”时调 `POST /web/preview`，卡片显示站点、标题、字数和阅读时长；只有预览成功才能点“解析并出题”。
- **失败**：预览失败、或出题中页遇到 4030–4033 / 4003（`setWebError` 带回来）时，预览卡片显示原因和替代方式：再读一次、粘贴要学的段落（回首页）、PDF 去知识库上传（`webErrorCopy`）。
- **出题**：`GenRequest.web` 有值时出题中页调 `POST /web/quiz`，步骤为“读取网页 / 判断主题与范围 / 出题并写讲解”。讲解框的出处显示“出处：网页《标题》”和原文摘录。报告页“再来一话”回到网页出题页并预填这个链接（`webUrlOf` 从题目出处里取网址）。

## 视频出题

- **入口**：首页“贴视频”打开 `pages/video-quiz`；首页输入框里整段是 B 站链接或 BV 号时，点“开始出题”带着链接转过去并直接读取（`core/video.ts` 的 `isBareBilibili`，先于网页链接判断）。
- **来源**（原型 02 第 4 屏）：“选视频文件”用 `showActionSheet` 让用户选“从微信聊天里选”（`chooseMessageFile({type:'video'})`）或“从手机相册选”（`chooseMedia`），先按后端同规则预检扩展名、200 MB、30 分钟（`precheckVideo`）；上传用 `uploadVideo`，带原始文件名（表单字段 `name`，临时路径里没有原名）和进度回调（`services/request.ts` 的 `upload` 新增 `formData`、`onProgress`）。“贴 B 站链接”：进页面读剪贴板，有 B 站分享文案就切到链接模式并填好（不自动读取）。H5 没有选文件能力，只提示去微信里上传。
- **解析进度**（第 5 屏）：上传 / 读取视频 → 提取音频 → 转文字 n/m 段，每 2 秒轮询 `GET /video/jobs/{id}`，页面隐藏时暂停、回来继续，断网的那次轮询不算失败。
- **就绪**：预览（视频名、时长、文字稿字数与来源），“只学其中一段”两个时间输入（mm:ss 或分钟数，`validateRange` 校验，从 0 开始 / 到结尾等于没填）、重点、题量，然后进出题中页（`GenRequest.video`）。
- **失败**（第 6 屏）：后台失败原因（`fail_reason`）或接口错误按 `videoErrorCopy` 给替代方式：改为上传视频文件 / 粘贴要学的段落 / 再试一次。出题中页遇到 4040 / 4053 / 4054 / 4032 / 4003 带回这里提示（`setVideoError`）。
- **出处**：讲解框显示“出处：视频《名》02:10”和文字稿摘录。报告页“再来一话”回到视频出题页：B 站视频预填链接重新解析，上传的视频要重新选（解析结果只保留 2 小时）。

### 开发者工具缓存

改了跨页面共用模块的导出后，模拟器偶尔会出现“旧页面代码 + 新公共包”的错配（如 `(0, o.G) is not a function`、页面空白）。清编译缓存后重开项目即可：

```bash
cli.bat cache --clean compile --project <frontend 目录>
cli.bat close --project <frontend 目录>
cli.bat open --project <frontend 目录>
```
