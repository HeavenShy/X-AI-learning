# 测试素材

在小程序页面里上传或输入过的测试素材：文件、链接、输入的文字。测试代码不放这里，在 `backend/tests`、`frontend/tests`。

## 文件（`files/`）

| 文件 | 用在哪 | 说明 |
| --- | --- | --- |
| `员工手册.pdf` | 我的知识库 → 上传资料 → 用知识库出题 | 10 页文字版 PDF。重点可以填“报销审批” |
| `理财三个基础概念.mp4` | 用视频出题 → 选视频文件 | 200 秒，320×240 黑画面。**音轨只是正弦音，没有真人讲话**，只用来测上传、解析进度和界面。用真转写解析时会提示“没识别到讲话内容” |
| `理财三个基础概念-讲稿时间轴.json` | 配合上面的视频，转写换成讲稿替身时用 | 4 节内容（复利、单利、七十二法则、通货膨胀），每节 50 秒。用法：`python -m scripts.smoke_video --video ../test-materials/files/理财三个基础概念.mp4 --fake-asr ../test-materials/files/理财三个基础概念-讲稿时间轴.json`（在 backend 目录） |

要测真实转写，需要一段有人讲话的视频（硅基流动账户要有余额），比如把讲稿用手机录一遍再上传。

## 链接

### 用网页出题

| 链接 | 2026-11-08 实测结果 |
| --- | --- |
| https://mp.weixin.qq.com/s/gLyaLhWWDj1WoDSxEwpT6Q | 公众号文章《别搞Graph RAG了，拥抱新一代RAG范式DeepSearcher》：本地读取成功，约 6900 字 |
| https://mp.weixin.qq.com/s/EdoA5fcyzgTw3LarMMe00g | 公众号文章《中文RAG检索增强生成榜单出炉！》：本地读取成功 |
| https://www.ruanyifeng.com/blog/2019/09/getting-started-with-github-actions.html | 博客《GitHub Actions 入门教程》：成功，约 4400 字 |
| https://docs.python.org/zh-cn/3/tutorial/controlflow.html | Python 中文文档《更多控制流工具》：成功，约 1.5 万字（长文，范围判断只看每块开头） |
| https://www.infoq.cn/article/L452I9YAB4gaKJMmiY0T | InfoQ《从 RAG 到 Context：2025 年 RAG 技术年终总结》：成功，约 1.8 万字 |
| https://medium.com/@karpathy/software-2-0-a64152b37c35 | 英文文章《Software 2.0》：成功 |
| https://github.com/login | 登录页：预期返回 4032“AI 读完觉得这个网页没有可以出题的知识内容” |
| https://baike.baidu.com/item/%E5%A4%8D%E5%88%A9 | 百度百科：本地 403，Tavily 也取不到，返回 4031“网站拒绝了访问” |
| https://www.zhihu.com/question/19550224 | 知乎：同上，4031 |
| https://xie.infoq.cn/article/74b03f811da5ed053c6533473 | 动态渲染的页面：读不出正文，返回 4032 |
| http://10.0.0.1/admin | 内网地址：预期返回 4030“这个地址不能访问” |

### 用视频出题（B 站）

| 链接 | 说明 |
| --- | --- |
| https://www.bilibili.com/video/BV1ns411w7tt | 《两分钟告诉你什么是复利？》，2 分 19 秒，没有 CC 字幕。取信息、下载音频都成功过，几次请求后被 B 站风控挡住（HTTP 567） |
| https://www.bilibili.com/video/av25762973 | 李永乐老师讲复利，约 9.5 分钟，没有 CC 字幕 |
| https://www.bilibili.com/video/BV1LL411M7Wq | 《【方少谈钱】你可能不太清楚什么是复利》，约 14.5 分钟，没有 CC 字幕 |
| `BV1ns411w7tt` | 只填 BV 号也能识别 |
| https://v.qq.com/x/cover/abc.html | 不是 B 站链接：预期提示“没认出 B 站链接” |

B 站有风控，短时间内不要反复用同一个链接测试。

## 输入过的文字

剪贴板内容（测“进页面自动填好链接”时放进剪贴板）：

```text
【DeepSearcher】https://mp.weixin.qq.com/s/gLyaLhWWDj1WoDSxEwpT6Q 复制此链接
【两分钟告诉你什么是复利？】 https://b23.tv/AbCdEf 复制此链接
```

第二条里的 `b23.tv/AbCdEf` 是编的短链，只用来测剪贴板识别，点“读取视频”会失败。

首页输入框：

| 输入 | 预期 |
| --- | --- |
| `https://mp.weixin.qq.com/s/gLyaLhWWDj1WoDSxEwpT6Q` | 点“开始出题”转到网页出题页 |
| `https://www.bilibili.com/video/BV1ns411w7tt` 或 `BV1ns411w7tt` | 点“开始出题”转到视频出题页并直接读取 |

网页 / 视频出题页的“想重点学什么”：

| 页面 | 输入 |
| --- | --- |
| 网页（DeepSearcher 那篇） | `DeepSearcher 和 GraphRAG 的区别` |
| 网页 | `和微调怎么选` |
| 视频（理财三个基础概念） | `七十二法则` |
| 知识库（员工手册） | `报销审批` |

视频出题页的“只学其中一段”：

| 开始 | 结束 | 预期 |
| --- | --- | --- |
| `03:00` | `01:00` | 提示“结束时间要晚于开始时间” |
| `01:00` | `03:20` | 通过；结束等于视频结尾，等于只填了开始，出题中页显示“01:00–结尾” |
| `13:00` | 空 | 提示“开始时间超出了视频长度” |
| `5` | 空 | 只写分钟数也行，等于 05:00 |

网页出题页的链接框输入 `什么是 RAG`：预期提示“没认出网址”。
