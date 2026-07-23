"""
灵笺 Lingjian · 后端代理层 (FastAPI)

`/parse` 会自动判断:
  • 环境里有 DEEPSEEK_API_KEY  → 真调 DeepSeek(deepseek-v4-flash),按 §7 输出 9 字段
  • 没有 key                    → 假后端(返回 §7 写死示例),泳道1 用它就能把前端链路跑通

所以接真 AI = 把 key 写进 backend/.env 并重启,前端一个字都不用改。
API key 只从环境变量读,严禁硬编码、严禁进 git / apk / 前端(见 README §0/§10)。

本地跑:  pip install -r requirements.txt  &&  uvicorn main:app --reload --port 8000
自测:    curl http://localhost:8000/health      # mode=live 表示 key 已加载走真调;fake 表示假后端
         curl -X POST http://localhost:8000/parse -H 'Content-Type: application/json' \\
              -d '{"text":"明天上午写完实验部分,晚上八点陪我妈散步半小时,这周得去趟医院"}'
"""
import os
import json

# 从 backend/.env 自动加载 DEEPSEEK_API_KEY(该文件已被 .gitignore 忽略)。
# 用 try 包住:没装 python-dotenv 时(如纯假后端环境)也能正常启动。
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Lingjian Backend", version="0.2.0")

# 开发期放开跨域:前端 HTML(file:// 或 http://localhost)要能 fetch 到本后端,
# 不加这个,浏览器会因 CORS 拦掉请求 → 前端每次都走本地兜底,徽章永远"离线"。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 泳道3 上线时可收窄到具体来源
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模型设成配置项(README §8:最便宜、够用;别用已停用的 deepseek-chat/reasoner,别用更贵的 v4-pro)
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-flash")

# §7 约定:domain 只能是这 6 个之一,前端 paint() 只认它们,否则渲染崩
VALID_DOMAINS = {"work", "study", "life", "health", "social", "leisure"}
REQUIRED_FIELDS = {"title", "domain", "time", "deadline",
                   "est", "load", "restorative", "conf", "day"}
CN_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class ParseReq(BaseModel):
    text: str


def _has_key() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


@app.get("/health")
def health():
    """让评委/自己不装 apk 也能确认后端真活着(README §10)。
    mode=live 表示 key 已加载、走真调;fake 表示假后端。"""
    return {"ok": True, "mode": "live" if _has_key() else "fake", "model": MODEL}


# ---------------------------------------------------------------------------
# 泳道1:假后端(无 key 时用)
# ---------------------------------------------------------------------------
def fake_parse(text: str):
    """返回一条符合 §7 的示例数组(9 字段 + domain 合法),不依赖任何 key。"""
    return [
        {"title": "写完实验部分", "domain": "work",   "time": "上午", "deadline": "明天", "est": 90, "load": "deep",   "restorative": False, "conf": 93, "day": 1},
        {"title": "陪妈妈散步",   "domain": "social", "time": "晚上", "deadline": "今天", "est": 30, "load": "light",  "restorative": True,  "conf": 88, "day": 0},
        {"title": "去趟医院",     "domain": "health", "time": None,   "deadline": "本周", "est": 60, "load": "medium", "restorative": True,  "conf": 72, "day": 0},
    ]


# ---------------------------------------------------------------------------
# 泳道2:真调 DeepSeek(有 key 时用)
# ---------------------------------------------------------------------------
def _now_str() -> str:
    """服务器当前时间(北京时间),注入提示词,让"明天/下午三点"能换算成绝对日期/day。"""
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    return f"{now.strftime('%Y-%m-%d')} {CN_WEEKDAYS[now.weekday()]} {now.strftime('%H:%M')}"


def _build_system(now_str: str) -> str:
    # ⚠️ 必须出现字面词 "json",否则 DeepSeek 的 JSON 模式会静默失效(README §8)。
    return (
        "你是日程解析器,把用户的中文口语解析成结构化数据。只输出 json,不要任何解释文字。\n"
        f"当前时间:{now_str}。据此把\"明天/后天/下午三点\"等相对时间换算成绝对的 day 与时段。\n"
        "输出一个 JSON 对象,形如 {\"tasks\":[ ...每个元素严格含下面 9 个字段... ]}。\n"
        "9 个字段:\n"
        "- title: 动作本身,去掉时间词与口语词(如\"记得/帮我/提醒我/得/要\")\n"
        "- domain: 只能是 work|study|life|health|social|leisure 之一\n"
        "- time: 中文时段 上午|中午|下午|晚上,或具体如\"8点半\";没有则 null\n"
        "- deadline: 今天|明天|后天|本周;没有则 null\n"
        "- est: 预计时长,分钟整数;用户没明说时长时,按任务类型合理估计(一般 15-120 分钟),**不要返回 0**\n"
        "- load: deep(>=90 分钟)|medium(>=40)|light\n"
        "- restorative: 布尔;domain 为 health/social/leisure 时为 true,否则 false\n"
        "- conf: 置信度数字(0-100)\n"
        "- day: 整数,今天=0 明天=1 后天=2\n"
        "一句话包含多件事时要拆成多个元素。\n"
        "示例:{\"tasks\":[{\"title\":\"陪妈妈散步\",\"domain\":\"social\",\"time\":\"晚上\",\"deadline\":\"今天\",\"est\":30,\"load\":\"light\",\"restorative\":true,\"conf\":88,\"day\":0}]}"
    )


def _extract_items(content: str):
    """从模型返回里取出任务数组,兼容 {tasks:[...]} / 裸数组 / 单对象等几种形态。"""
    data = json.loads(content)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("tasks", "items", "events", "list", "data", "result"):
            if isinstance(data.get(k), list):
                return data[k]
        if REQUIRED_FIELDS.issubset(data.keys()):   # 模型把单条任务直接当对象返回
            return [data]
    return []


def real_parse(text: str):
    """真调 DeepSeek(v4-flash, JSON 模式, 注入服务器时间, 失败/空返回重试一次)。
    返回已校验的 9 字段数组;彻底失败返回 [](前端会自动回退本地兜底)。"""
    from openai import OpenAI   # 延迟导入:假后端环境没装 openai 也能启动
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                    base_url="https://api.deepseek.com")   # OpenAI 兼容,只改 base_url
    system = _build_system(_now_str())
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": text}],
                temperature=0.2,
            )
            items = validate(_extract_items(resp.choices[0].message.content or ""))
            if items:
                return items
        except Exception as e:
            print("real_parse error:", e)   # 打日志,不抛给前端
    return []


def _norm(it):
    """把一条任务规整成前端友好、字段自洽的样子(模型偶发的边角问题在此兜底)。"""
    est = it.get("est")
    if not isinstance(est, int) or est <= 0:      # 模型没给/给了 0 → 默认 30 分钟,别显示"0分钟"
        est = 30
    it["est"] = est
    it["load"] = "deep" if est >= 90 else "medium" if est >= 40 else "light"   # load 由 est 推(§7、与前端一致)
    it["restorative"] = it.get("domain") in ("health", "social", "leisure")     # restorative 完全由 domain 决定
    if not isinstance(it.get("conf"), (int, float)):
        it["conf"] = 80
    return it


def validate(items):
    """后端再校验一遍(§7 硬要求):字段齐 + domain 合法 + day 是整数;不合格的项丢弃,合格的规整。"""
    clean = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        if not REQUIRED_FIELDS.issubset(it.keys()):
            continue
        if it.get("domain") not in VALID_DOMAINS:
            continue
        if not isinstance(it.get("day"), int):
            continue
        clean.append(_norm(it))
    return clean


@app.post("/parse")
def parse(req: ParseReq):
    items = real_parse(req.text) if _has_key() else fake_parse(req.text)
    return validate(items)


# ---------------------------------------------------------------------------
# L2-2:任务拆解 /decompose(有 key 走真调;无 key/失败返回空 → 前端回退本地模板)
# ---------------------------------------------------------------------------
class DecomposeReq(BaseModel):
    title: str
    mode: str = "steps"   # steps=拆成可执行小步(带 est,第一步~10min 破冰) | phases=大目标拆成阶段


def _decompose_system(mode: str) -> str:
    if mode == "phases":
        return (
            "你是任务拆解助手,把用户的一个大目标拆成 5-8 个有先后顺序的阶段。只输出 json。\n"
            "输出一个对象 {\"steps\":[{\"title\":\"阶段名\"}, ...]};title 简洁(不超过15字),按先后排列。\n"
            "示例:{\"steps\":[{\"title\":\"确定选题与研究问题\"},{\"title\":\"完成文献综述\"}]}"
        )
    return (
        "你是任务拆解助手,把用户的一件具体任务拆成 3-4 个可立刻执行的小步。只输出 json。\n"
        "关键:第一步必须是最小、最易起步的\"破冰\"动作(est 约 10 分钟),帮用户跨过启动的坎;"
        "每步以动词开头、结果可验收。\n"
        "输出一个对象 {\"steps\":[{\"title\":\"步骤\",\"est\":分钟整数}, ...]},按执行顺序。\n"
        "示例:{\"steps\":[{\"title\":\"打开文档,列出各小节标题\",\"est\":10},{\"title\":\"撰写正文第一部分\",\"est\":30},{\"title\":\"通读一遍、标出待补充\",\"est\":20}]}"
    )


def _norm_steps(steps, mode: str):
    """规整拆解结果:兼容 [{title,est}] / [\"字符串\"];steps 模式保证 est 为正整数(第一步默认10)。"""
    out = []
    if not isinstance(steps, list):
        return out
    for i, s in enumerate(steps):
        if isinstance(s, str):
            s = {"title": s}
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or "").strip()
        if not title:
            continue
        item = {"title": title}
        if mode != "phases":
            est = s.get("est")
            if not isinstance(est, int) or est <= 0:
                est = 10 if i == 0 else 25    # 第一步破冰默认 10 分钟
            item["est"] = est
        out.append(item)
    return out


def _decompose_real(title: str, mode: str):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    system = _decompose_system(mode)
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": title}],
                temperature=0.3,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            steps = data.get("steps") if isinstance(data, dict) else data
            steps = _norm_steps(steps, mode)
            if steps:
                return steps
        except Exception as e:
            print("decompose error:", e)
    return []


@app.post("/decompose")
def decompose(req: DecomposeReq):
    steps = _decompose_real(req.title, req.mode) if _has_key() else []
    return {"steps": steps}   # 空数组时前端回退本地模板


# ---------------------------------------------------------------------------
# L2-3:雷萌萌树洞对话 /chat(含危机词硬过滤;有 key 走真调,无 key/失败 → 前端本地兜底)
# ⚠️ 安全:危机词命中时绝不把内容送进模型,直接让前端切到"严肃关怀模式"(热线)。
# ---------------------------------------------------------------------------
CRISIS_WORDS = ["不想活", "活不下去", "结束一切", "自杀", "自残", "伤害自己", "撑不下去了",
                "没有意义", "消失算了", "想死", "轻生", "跳楼", "不想醒来"]


class ChatMsg(BaseModel):
    role: str        # user | assistant
    content: str


class ChatReq(BaseModel):
    text: str
    history: list[ChatMsg] = []


def _looks_crisis(text: str) -> bool:
    return any(w in (text or "") for w in CRISIS_WORDS)


def _chat_system() -> str:
    return (
        "你是「雷萌萌」,灵笺 app 里一只治愈系的小陪伴。用户来这个'树洞'是想倾诉、被接住,不是来听道理的。\n"
        "怎么回:\n"
        "- 先共情、不说教:先接住情绪,别急着给建议或讲大道理。\n"
        "- 温柔、口语、简短:像朋友一样,1-3 句话就好,别长篇。\n"
        "- 具体不敷衍:回应对方说的具体内容,别只会'加油'。\n"
        "- 可以偶尔轻轻提一个极小的行动(如'只做十分钟就好'),但绝不强迫、绝不评判、绝不施压。\n"
        "- 用'萌萌'自称,语气软一点、暖一点。\n"
        "只输出你要说的话本身,不要 json、不要加引号。"
    )


def _chat_real(text: str, history):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    msgs = [{"role": "system", "content": _chat_system()}]
    for m in (history or [])[-6:]:              # 只带最近几轮,省 token
        if m.role in ("user", "assistant") and m.content:
            msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": text})
    try:
        resp = client.chat.completions.create(
            model=MODEL, messages=msgs, temperature=0.8, max_tokens=220)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("chat error:", e)
        return ""


@app.post("/chat")
def chat(req: ChatReq):
    if _looks_crisis(req.text):                       # 安全第一:危机词命中 → 绝不进模型
        return {"crisis": True, "reply": ""}
    reply = _chat_real(req.text, req.history) if _has_key() else ""
    return {"crisis": False, "reply": reply}          # reply 为空时前端回退本地 BOT_REPLIES


# ---------------------------------------------------------------------------
# L2-5:洞察归因文案 /insights(数字由前端算法算好传入,文案由 AI 写;无 key/失败 → 前端保留写死默认)
# ---------------------------------------------------------------------------
class InsightReq(BaseModel):
    stats: dict


def _insights_system() -> str:
    return (
        "你是灵笺的心理·效率洞察分析师。根据给你的本周真实数据(JSON),写一段温柔而有洞察的归因分析。只输出 json。\n"
        "要点:先看见状态、不审判自己;要用到数据里的具体数字;可以做有洞察的归因(如把拖延归到焦虑、把疲惫归到没休息够),但别编造数据里没有的结论。\n"
        "输出一个对象 {\"headline\":\"一句话核心洞察\",\"analysis\":[\"1-2 段解读,每段是一个字符串\"],\"suggestions\":[\"给下周的第1条具体可执行建议\",\"第2条\"]}。\n"
        "示例:{\"headline\":\"你的疲惫,更多来自没休息够,而不是不够努力\",\"analysis\":[\"本周恢复性活动只占 8%,而平均压力到了 78…\"],\"suggestions\":[\"下午高压时段只排轻量事务\",\"每周锁定两次 30 分钟运动、不可移动\"]}"
    )


def _insights_real(stats):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _insights_system()},
                          {"role": "user", "content": json.dumps(stats, ensure_ascii=False)}],
                temperature=0.6)
            d = json.loads(resp.choices[0].message.content or "{}")
            head = str(d.get("headline") or "").strip()
            analysis = [str(x).strip() for x in (d.get("analysis") or []) if str(x).strip()]
            sug = [str(x).strip() for x in (d.get("suggestions") or []) if str(x).strip()]
            if head and analysis:
                return {"headline": head, "analysis": analysis, "suggestions": sug}
        except Exception as e:
            print("insights error:", e)
    return None


@app.post("/insights")
def insights(req: InsightReq):
    r = _insights_real(req.stats) if _has_key() else None
    return r or {}   # 空对象时前端保留写死默认文案


# ---------------------------------------------------------------------------
# L2-4:意图补全 /suggest(把用户正在输入的任务名改写成更具体可执行的 2-3 个;无 key/失败 → 前端本地模板)
# ---------------------------------------------------------------------------
class SuggestReq(BaseModel):
    text: str


def _suggest_system() -> str:
    return (
        "你是任务输入助手。用户正在输入一个任务名(可能很简略),帮他改写成 2-3 个更具体、可立刻执行、结果可验收的任务名。只输出 json。\n"
        "要求:保持用户原意;每个建议是一句简短任务名(不超过 20 字)、动词开头;不要解释。\n"
        "输出对象 {\"suggestions\":[\"写法1\",\"写法2\",\"写法3\"]}。\n"
        "示例:输入'写论文' → {\"suggestions\":[\"列出论文各小节标题,先起个头\",\"撰写实验分析,不少于800字\",\"通读全文、标出待补充的引用\"]}"
    )


def _suggest_real(text: str):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    try:
        resp = client.chat.completions.create(
            model=MODEL, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _suggest_system()},
                      {"role": "user", "content": text}],
            temperature=0.5, max_tokens=200)
        d = json.loads(resp.choices[0].message.content or "{}")
        return [str(x).strip() for x in (d.get("suggestions") or []) if str(x).strip()][:3]
    except Exception as e:
        print("suggest error:", e)
        return []


@app.post("/suggest")
def suggest(req: SuggestReq):
    text = (req.text or "").strip()
    if not text or not _has_key():
        return {"suggestions": []}
    return {"suggestions": _suggest_real(text)}


# ---------------------------------------------------------------------------
# L2-5 延伸:双重报告文案 /report(输入某区间真实数字,输出效率摘要+心理摘要+归因+建议;无 key/失败 → 前端保留写死)
# ---------------------------------------------------------------------------
class ReportReq(BaseModel):
    range: str = "week"
    stats: dict


def _report_system() -> str:
    return (
        "你是灵笺的双重报告撰写助手。根据给你的一段时间的真实数据(JSON),写这份报告的叙事文案。只输出 json。\n"
        "输出一个对象:{\n"
        " \"sumA\": \"效率报告(对外·可提交导师)的执行摘要,客观专业,2-4 句,要用到数据里的数字\",\n"
        " \"sumB\": \"心理诊断(对内·仅本地)写给用户自己的话,温柔共情、不审判,2-4 句\",\n"
        " \"attr\": [\"1-2 条核心归因,把现象与数据联系起来\"],\n"
        " \"suggest\": [\"给下一阶段的第1条温柔建议\",\"第2条\"]}\n"
        "别编造数据里没有的数字;sumA/sumB 可用少量 <b></b> 强调关键处。"
    )


def _report_real(rng, stats):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    payload = {"range": rng, "data": stats}
    try:
        resp = client.chat.completions.create(
            model=MODEL, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _report_system()},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            temperature=0.6, max_tokens=700)
        d = json.loads(resp.choices[0].message.content or "{}")
        sumA = str(d.get("sumA") or "").strip()
        sumB = str(d.get("sumB") or "").strip()
        attr = [str(x).strip() for x in (d.get("attr") or []) if str(x).strip()]
        sug = [str(x).strip() for x in (d.get("suggest") or []) if str(x).strip()]
        if sumA and sumB:
            return {"sumA": sumA, "sumB": sumB, "attr": attr, "suggest": sug}
    except Exception as e:
        print("report error:", e)
    return None


@app.post("/report")
def report(req: ReportReq):
    r = _report_real(req.range, req.stats) if _has_key() else None
    return r or {}


# ---------------------------------------------------------------------------
# L2-5 尾:心力温度计结果解读 /thermo(3 维自测分数 → AI 个性化解读;无 key/失败 → 前端保留预设)
# ---------------------------------------------------------------------------
class ThermoReq(BaseModel):
    zone: str
    scores: dict


def _thermo_system() -> str:
    return (
        "你是「雷萌萌」,灵笺里治愈系的小陪伴。用户刚做完'心力温度计'自测,给你 3 个维度的百分比"
        "(越高越糟:心理负荷/焦虑度/职业疲劳)和总体区间(green从容 / yellow略紧 / orange偏紧 / red需休息)。\n"
        "根据这些数,写 1-2 句温柔、具体、不审判的状态解读:点出最突出的那个维度,给一句极轻的建议或安抚。"
        "像朋友说话、不像医生。只输出这句话本身,不要 json、不要加引号。"
    )


def _thermo_real(zone, scores):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    payload = {"zone": zone, "scores": scores}
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": _thermo_system()},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            temperature=0.7, max_tokens=140)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("thermo error:", e)
        return ""


@app.post("/thermo")
def thermo(req: ThermoReq):
    return {"text": _thermo_real(req.zone, req.scores) if _has_key() else ""}
