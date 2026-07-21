# 灵笺 / 心序（Attune）· 行动方案与开发交接文档

> **这份文件是本项目的"单一事实来源（Single Source of Truth）"。**
> 它同时是:①行动方案 ②进度日志 ③交接文档。
> **新窗口 / 新同学接力开发,请先从头读这份文件。** 有任何决策、进展、技术细节,都记录到这里,不要散落在别处。

- **最后更新**: 2026-07-21
- **维护方式**: 每次有进展,更新对应章节 + 在文末【15. 进度日志】追加一条
- **当前阶段**: 方案已定 + 关键技术细节已联网核实,准备进入开发阶段①

---

## 🔴 0. 两条"现在就必须知道"的紧急事项

1. **DeepSeek 模型名有个时间炸弹**:旧名 `deepseek-chat` / `deepseek-reasoner` 将于 **2026-07-24 15:59 UTC(约3天后)彻底停用**,之后调用直接报错。**比赛必须用新名 `deepseek-v4-flash`**,并把模型 ID 设成后端配置项(别硬编码)。演示当天再 curl 复核一次能用的名字。
2. **后端返回的 JSON 必须和前端现有格式"逐字段一致"**(见 §7)。前端 `paint()` 吃的是 `parseUtterance` 那 **9 个字段**,`domain` 还必须是 6 个合法值之一,否则**真调 AI 成功了反而当场崩溃**,比走本地假数据还难看。**先对齐字段,再谈接 AI。**

---

## 1. 项目一句话

参加**迅雷 AI 产品大赛**的作品:一款依托大模型的 **AI 效率 + 生活管理助手**,核心主张是"**把心理状态纳入日程排序**、**工作只是生活的六分之一**",有一个治愈系吉祥物「**雷萌萌**」。团队 **2 人,均无 app 开发经验**,重度借助 AI 编程助手推进。

---

## 2. 已确定的关键决策（Decisions）

| # | 决策项 | 结论 |
|---|---|---|
| D1 | **产品名** | ⚠️ **待统一** —— 原型叫「灵笺 Lingjian」,方案文档叫「心序 Attune」。**必须二选一**(影响 apk 名、答辩、所有文案)。吉祥物"雷萌萌"两边一致 |
| D2 | **AI 能力来源** | **DeepSeek API**,模型用 **`deepseek-v4-flash`**(非思考模式;便宜快,足够日程解析)。key 待申请 |
| D3 | **产品形态** | **Android app** —— 用 **Capacitor 8** 把现有 HTML 原型"套壳"成 apk,不重写 |
| D4 | **后端** | **Python FastAPI 做代理层**,API key 只放后端,浏览器/app 绝不直连大模型 |
| D5 | **参赛范围** | **狠砍**:只让 **1 条 P0 核心链路"真跑"**(说一句话→出日程),其余功能保持 mock / 录屏 |
| D6 | **主打叙事** | **价值观主线**:"工作只是你生活的六分之一 / 一款会心疼你的助手";技术回路作为壁垒证明 |
| D7 | **iOS** | **暂不做**(需 Mac + $99/年开发者账号);参赛只做 Android apk |
| D8 | **后端部署** | ⏳ **待拍板**,推荐:**HTTPS 隧道(cloudflared/ngrok)做主**、国内轻量服务器 IP 直连做备(详见 §10) |

---

## 3. 技术架构（一张图）

```
 📱 Android App                🖥️ 你的后端(公网)            🤖 DeepSeek
 ┌─────────────────┐  fetch   ┌──────────────────┐  调用   ┌──────────────┐
 │ WebView 里跑     │ ───────▶ │ FastAPI 代理      │ ──────▶ │ v4-flash     │
 │ 现有 HTML 原型   │ ◀─────── │ (握着 API key)    │ ◀────── │              │
 └─────────────────┘  JSON    └──────────────────┘         └──────────────┘
   Capacitor 套壳                key 只在这里,不进 apk
```

**安全红线**: API key **永远只在后端**,不进 apk、不进前端、不进 git、不进提交包。

---

## 4. 资产现状盘点

| 资产 | 状态 | 说明 |
|---|---|---|
| **前端原型** `lingjian-app (17).html` | ✅ 已有,很完整很精致 | **单文件、原生 JavaScript(非 React)**、~470KB。5 页(首页/规划/习惯/洞察/我的)、雷萌萌桌宠(WebAudio 声音)、白板 canvas、新手引导。**但:全部 mock;0 网络请求;0 持久化(刷新即清空);唯一外部依赖 Google Fonts** |
| **方案文档** `心序AI(Attune)方案设计文档_V7.docx` | ✅ 质量很高 | 13 章完整方案,答辩底稿 |
| **构思文档** `迅雷AI产品大赛想法设计.docx` | ✅ 已有 | 三个创意原始构思 |
| **后端** | ❌ 未建 | 阶段① 要新建的 FastAPI |
| **DeepSeek key** | ⏳ 待申请 | platform.deepseek.com 注册→实名→生成→充 ¥10-20 |

---

## 5. 核心链路（P0 —— 唯一要"真跑"的那条）

**"说一句话 → 真调 DeepSeek → 生成带依赖的日程"**

```
用户说/输入一句话
  → 前端 renderResult()(HTML 第3541行) fetch 后端 /parse
  → 后端把这句话 + 提示词发 DeepSeek(v4-flash, JSON模式)
  → DeepSeek 返回 9 字段的规范 JSON 数组(见 §7)
  → 前端 paint() 渲染成任务卡片(渲染代码现成,不改)
```

**代码落点**:现在 `renderResult`(第3541行)用 `setTimeout` 假装解析后调 `parseUtterance`(第3462行)。改法见 §10(try 后端 / catch 回退本地)。

---

## 6. 功能清单:谁的活 + 完成度

**判断尺**:只有两种情况需要后端 —— ①要用大模型(key 不能进浏览器);②要持久保存数据。其余纯算法/纯界面都是前端。

| 功能 | 现状 | 归属 |
|---|---|---|
| 说一句话→切分/归类/估时 (`parseUtterance`) | 假·本地关键词 | **后端(P0)** |
| AI 帮我拆解任务 (`chainSteps`) | 假·写死模板 | 后端(P1) |
| 意图自动补全 | 假·写死 | 后端/前端(P2) |
| 雷萌萌情感对话(树洞) | 假·固定回复 | 后端(P1) |
| 周报 / 归因洞察**文案** | 假·写死文字 | 后端(P2) |
| 压力校准**结果** | 假·定时器+预设 | 后端+前端(P2) |
| 白板涂鸦→任务 | 假/空壳 | 后端多模态(P3,保持 mock) |
| 危机词兜底过滤 | 无 | 后端(P1·安全) |
| **保存数据(刷新不丢)** | **无,刷新即清空** ⚠️ | 前端 localStorage(临时)/后端 DB(正式) |
| 拓扑排序/关键路径、智能顺延、热力图/时间盘、界面/动画/声音 | ✅ 大多已完成 | **前端** |

---

## 7. 前后端接口约定（API 契约）—— ✅ 已按真实代码核定

> **这是本项目最容易翻车、也最先要做对的一件事。** 后端返回的 JSON 必须和前端 `parseUtterance`(HTML 第3462行)的输出**逐字段一致**,否则 `paint()` 渲染崩溃。
> ⚠️ **不要用** `{events:[{title,start,end,depends_on}]}` + ISO8601 这种"通用"格式 —— 那是错的,喂进前端会崩。

**`POST /parse`**

```
请求:  { "text": "明天上午写完实验部分,晚上八点陪我妈散步半小时,这周得去趟医院" }

响应:  一个数组,每项严格含以下 9 个字段:
[
  {
    "title":       "写完实验部分",   // 字符串,已去掉时间词/口语词
    "domain":      "work",         // ⚠️ 只能是: work|study|life|health|social|leisure(6选1,否则崩)
    "time":        "上午",         // 中文label: 上午|中午|下午|晚上 或 "8点半" 之类;无则 null(不是时间戳!)
    "deadline":    "明天",         // 中文label: 今天|明天|后天|本周;无则 null
    "est":         90,             // 预计时长,分钟整数
    "load":        "deep",         // deep(≥90)|medium(≥40)|light,可由 est 推
    "restorative": false,          // 布尔,= 该 domain 是否恢复性(health/social/leisure 为 true)
    "conf":        93,             // 置信度数字(如 72/88/93)
    "day":         1               // 整数: 今天=0,明天=1,后天=2
  }
]
```

**给后端的硬要求**:
- system 提示里明确列出上面 9 个字段 + `domain` 的 6 个合法值 + 给一个完整 JSON 示例。
- 让 DeepSeek**只输出这个数组**(开 JSON 模式,见 §8)。
- 后端拿到后**再校验一遍**:字段齐不齐、`domain` 是否在 6 个里、`day` 是否整数;不合格就重试或丢弃该项。
- **联调技巧**:先用一个"假后端"(直接返回上面的示例数组)把前端 fetch 打通,确认 `paint()` 正常,再把假后端换成真调 DeepSeek。

---

## 8. DeepSeek 接入细节 —— ✅ 已联网核实(2026-07-21)

**核实结论**:DeepSeek 是 **OpenAI 兼容接口**,后端直接用官方 `openai` Python SDK,只改 `base_url` 即可。

| 项 | 值 |
|---|---|
| base_url | `https://api.deepseek.com`(部分工具需 `/v1`) |
| 认证 | HTTP Header `Authorization: Bearer <API_KEY>` |
| **模型** | **`deepseek-v4-flash`**(非思考模式)。⚠️ 别用 `deepseek-chat`/`deepseek-reasoner`(07-24 停用)。别用 v4-pro/思考模式(更慢更贵,这任务不需要) |
| JSON 模式 | `response_format={'type':'json_object'}`。**硬性要求:提示词里必须出现字面词 "json",否则静默失效**;并给一个 JSON 示例;空返回要重试 |
| Function Calling | 支持(128 函数上限,strict 模式需 beta base_url)。本项目用 json_object 已够,不必上 |
| 价格 | v4-flash 极便宜,一次调用不到 1 分钱,**¥10-20 够整个比赛反复演示**(以控制台实时价为准) |
| 申请 | platform.deepseek.com 手机号注册 → **实名认证(传身份证,几分钟)** → 生成 Key(**只显示一次,立刻存后端环境变量**)→ 充值(支付宝/微信)。⚠️ 赠送额度政策不确定(有资料称已取消),别指望,直接充值最稳 |

**FastAPI 最小可用写法(伪代码,注意:输出对齐 §7 的 9 字段,不是 events)**:
```python
import os, json
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'],       # ← key 只在这行,从环境变量读,严禁硬编码
    base_url='https://api.deepseek.com'            # ← OpenAI 兼容,只改这里
)
app = FastAPI()
MODEL = os.environ.get('DS_MODEL', 'deepseek-v4-flash')   # ← 模型设成配置项,方便切换

class Req(BaseModel):
    text: str

def build_system(now_str):
    return f'''你是日程解析器,把用户中文口语解析成 JSON 数组,只输出 json。
当前时间:{now_str}(据此把"明天/下午三点"换算成绝对日期)。
每个元素严格含9字段:title(去掉时间词的动作),domain(只能是 work|study|life|health|social|leisure),
time(中文label 上午/中午/下午/晚上 或 "8点半",无则 null),deadline(今天/明天/后天/本周,无则 null),
est(分钟整数),load(deep/medium/light),restorative(布尔,health/social/leisure 为 true),
conf(置信度数字),day(今天0 明天1 后天2)。
一句话含多件事要拆分。示例:[{{"title":"陪妈妈散步","domain":"social","time":"晚上","deadline":"今天","est":30,"load":"light","restorative":true,"conf":88,"day":0}}]'''

@app.post('/parse')
def parse(r: Req):
    now = '2026-07-22 周三 14:00'   # TODO: 用服务器真实时间
    for _ in range(2):             # 失败重试一次兜底
        resp = client.chat.completions.create(
            model=MODEL,
            response_format={'type':'json_object'},
            messages=[{'role':'system','content':build_system(now)},
                      {'role':'user','content':r.text}],
            temperature=0.2)
        try:
            data = json.loads(resp.choices[0].message.content)
            items = data if isinstance(data, list) else data.get('tasks') or data.get('events') or []
            # TODO: 校验每项 9 字段 + domain 合法性,不合格丢弃
            return items
        except Exception:
            continue
    return []   # 前端会因空结果自动走本地回退(见 §10)
```

**关键坑(已核实)**:①不注入当前真实时间→相对时间算错;②提示无"json"字→JSON模式失效;③key 混进前端/apk/git→泄露被盗刷。

---

## 9. Capacitor 安卓打包细节 —— ✅ 已联网核实(2026-07-21)

**环境要求**:Node.js **22+**、Android Studio **2025.2.1+**(自带 JDK/SDK,最低 API 24)、一台 **8GB 内存以上**电脑、预留 15-20GB。一次性配置约 1-2 小时。**两个新手预估 1-2 天出可安装真跑 apk。**

**步骤**:
```
0. 装 Node 22 + Android Studio(向导装好 SDK)
1. npm init -y; npm i @capacitor/core@latest @capacitor/cli@latest
   npx cap init 灵笺 com.leimengmeng.lingjian --web-dir=www   # ← 包名一次定死,别再改
2. 建 www/,把 lingjian-app(17).html 复制进去【重命名为 index.html】  # 单文件,无需打包工具
3. 【别跳】字体离线内嵌:gwfh.mranftl.com 下 Fraunces+Manrope 的 woff2 → 放 www/fonts/
   删掉 HTML 第9-11行三个 Google <link>,改本地 @font-face(font-display:swap)
4. npm i @capacitor/android@latest; npx cap add android; npx cap sync android
   ⚠️ 每次改了 HTML,都要重新 npx cap sync android 再打包(否则 apk 还是旧内容)
5. 处理联网(见下"头号坑")
6. 出 apk:npx cap open android → Build > Build APK(s) → 拿 app-debug.apk
7. 传手机,允许"安装未知应用"即可装(debug apk 能正常装跑)
8. (加分)@capacitor/assets 生成图标/启动图;strings.xml 里 app_name 改"灵笺"
```

**三个"必翻车"的坑(已核实)**:
1. 🔴 **头号坑:安卓默认禁止明文 HTTP**。Android 9+ 拦截 `http://` 请求,且**静默失败没报错**。"浏览器好使、装进 apk 真机就不好使"几乎都是这个。→ 后端走 **HTTPS**(隧道最省事,见 §10),或 capacitor.config 设 `server.cleartext=true` + `network_security_config.xml` 放行后端 IP。**打完 apk 必须真机验证,靠"AI在线/离线"徽章确认走的是后端。**
2. **Google Fonts 联网依赖** → 无网/国内会字体白屏/跳动。按步骤3内嵌成离线。
3. **首次 `cap sync`/gradle 构建**要联网下大量依赖,国内极慢 → 配阿里云 maven 镜像或挂稳定代理,预留时间别中途打断。

其它:WebAudio 桌宠声音需用户**先触摸一次**才响(autoplay 策略,正常,不用改);canvas 白板 WebView 原生支持。

---

## 10. 提交物 & "评委一定看得到效果"的兜底 —— ✅ 已核实

**🟢 最强兜底(强烈推荐,改动约20-30行,价值极高)**:把 `renderResult()`(HTML 第3541行)改成:
```
async 先 try: fetch 后端 /parse(带 8 秒超时)→ 成功用后端返回的数组
          catch: 任何失败(后端挂/超时/没网/限流)→ 回退调本地 parseUtterance(text)
两条路都喂给同一个 paint()
```
效果:**后端在=真 AI 结果,后端不在=退回本地示例,界面几乎一样,永不白屏转圈。** 再加一个不显眼的 **"AI在线/离线"状态徽章**:既能当场向评委证明"这条是真调 AI 不是写死",又能让你自己第一时间知道有没有走了回退。

**提交四件套**:
| 提交物 | 作用 |
|---|---|
| **apk 安装包** | 评委能装能点的"真产品"实体(内置兜底,永不白屏) |
| **部署 URL**(挂个 `/health`) | 让评委不装 apk 也能验证后端真活着;被质疑"是不是假的"时当场自证 |
| **源码 zip(去 key)** | 附 `.env.example`;体现工程完整度。提交前全局 grep `sk-`/`deepseek`/`key` |
| **录屏视频 60-90秒** | 终极兜底:后端万一挂了/评委没网,视频证明链路真跑通过 |

**后端部署选型(§2 D8 待拍板)**:
- ① **HTTPS 隧道(cloudflared/ngrok)** —— 最省事、走 4G 也能演示、天然过 cleartext。缺点:免费档 URL 会变/偶尔不稳。**推荐做主方案。**
- ② **国内轻量服务器 IP+非标端口(8000)直连** —— 国内快、免备案。缺点:要在 apk 里配 cleartext 白名单。**做备选。**
- ③ 海外 Serverless(Render/Railway) —— 自带 https 子域名,但国内访问慢。
- ❌ **别买域名走 ICP 备案**(1-3 周,来不及)。

**演示路径(强烈建议)**:**主推 现场用你们自己的手机 + 自己的热点真跑 + 录屏**;apk 照给评委自测,但因内置本地兜底,评委那边不通也只看到示例数据、不白屏。**绝不要把"评委必须用自己手机、自己网、当场真调通 AI"设成唯一路径。**

---

## 11. 路线图 / 里程碑

- [ ] **阶段①(核心,浏览器里做最快)**: ①统一 §7 的 9 字段接口 → ②搭 FastAPI 接 DeepSeek(§8)→ ③`renderResult` 加 try/catch 兜底(§10)→ **"说一句话→真出日程"在浏览器里真跑**
- [ ] **阶段②(打包)**: Capacitor 打成 Android apk,离线字体,真机验证联后端(§9)
- [ ] **阶段③(交付)**: 部署后端 + 四件套 + 录视频(§10)
- [ ] (贯穿) 统一产品名、答辩稿、方案文档收尾

---

## 12. 待细化 & 待落实清单（P0/P1/P2）—— ✅ 已核实排序

**P0(必须做对,否则演示翻车):**
- [ ] **接口 9 字段对齐**(§7):后端输出严格同构 `parseUtterance`,`domain` 限 6 值,`time`用中文label非时间戳,`day`用0/1/2,`est`用分钟。【后端】
- [ ] **`renderResult` 降级链路**(§10):try 后端 / catch 回退本地,同一 `paint()`。【前端】
- [ ] **模型名用 `deepseek-v4-flash`**、设成配置项,全项目 grep 无旧名残留。【后端】
- [ ] **API Key 只放后端 .env** + `.gitignore`,前端/apk/git 绝不出现。【后端】
- [ ] **安卓明文流量**:后端 HTTPS 或配 cleartext + network_security_config;**真机验证**。【打包】
- [ ] **Google Fonts 离线内嵌**。【前端】
- [ ] **注入服务器当前时间**到 system 提示。【后端】
- [ ] **JSON 模式**:提示含"json"字 + 给示例 + `json.loads` try/except 重试。【后端】
- [ ] **真机验证核心链路** + "AI在线/离线"徽章。【打包】
- [ ] **改 HTML 后必 `npx cap sync android`** 再打包。【打包】

**P1(重要):**
- [ ] 提交四件套(apk + /health URL + 去key源码zip + 60-90秒视频)。【文档】
- [ ] DeepSeek 开通:一人实名注册 + 充 ¥10-20,Key 存后端。【决策】
- [ ] 演示当天 checklist:curl 测模型名、确认余额/进程、真机连自己热点跑+录新视频、断网测回退。【文档】
- [ ] 包名 appId 定死(如 `com.leimengmeng.lingjian`),全程同一电脑同一 debug keystore。【打包】
- [ ] 首次构建配阿里云 maven 镜像/挂代理,预留时间。【打包】
- [ ] demo 主链路用测过稳的那句话,temperature=0.2。【文档】
- [ ] 环境:Node22+/Android Studio 2025.2.1+/8GB电脑。【打包】

**P2(锦上添花):**
- [ ] WebAudio 声音绑用户手势 resume;图标/启动图/app名;单独录10秒"断网重放"展示兜底;不上 strict/pro/思考模式。

---

## 13. 待用户/团队拍板的决定

- [ ] **D1 产品名**:叫「心序」还是「灵笺」?
- [ ] **D8 后端部署**:主方案选 ①隧道 还是 ②国内IP直连?(推荐①做主②做备)
- [ ] 演示验收路径:确认"以自己手机+自己热点+录屏为准,评委自测只当加分"?(强烈建议是)
- [ ] 谁的实名账号注册 DeepSeek、首充多少(建议 ¥10-20)?
- [ ] appId 包名最终字符串?(一旦定不再改)
- [ ] 确认放弃 iOS + 域名/备案,只交安卓 apk?
- [ ] 谁偏前端、谁偏后端?(见 §14)

---

## 14. 分工（2 人,均新手）

- **第 1 阶段建议不分工**:两人结对把核心链路从头打通一次,建立全局认知。
- **之后分工**:
  - **人 A · 后端/AI**:FastAPI + 接 DeepSeek + 提示词(对齐9字段) + 部署。(重心)
  - **人 B · 前端/演示**:`renderResult` 加兜底 + Capacitor 打包 + 离线字体 + 录屏 + 答辩视觉 + 兼顾文档。
- **杠杆**:两人都重度用 AI 编程助手,让 AI 写初版,你们理解+调试+串起来。

---

## 15. 进度日志（Changelog,倒序,新的在上）

- **2026-07-21 (更新2)** — 联网核实 DeepSeek 接入 + Capacitor 安卓打包 + 提交兜底,结果全部回填(§8/§9/§10)。**修正 §7 接口契约**:经核对真实代码,后端必须输出 `parseUtterance` 的 9 字段(`domain` 限6值、`time`为中文label、`day`为0/1/2),而非 events/ISO8601。补齐 §12 P0/P1/P2 待落实清单与 §13 待决策。**两条紧急事项**记入 §0:DeepSeek 07-24 模型改名、字段对齐。
- **2026-07-21 (更新1)** — 创建本行动方案 / 交接文档。确定关键决策 D1–D7。完成前端原型现状盘点、功能前后端归属、核心链路定义。DeepSeek/Capacitor 细节标记待核实。
