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
        "- est: 预计时长,分钟整数\n"
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


def validate(items):
    """后端再校验一遍(§7 硬要求):字段齐 + domain 合法 + day 是整数;不合格的项丢弃。"""
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
        clean.append(it)
    return clean


@app.post("/parse")
def parse(req: ParseReq):
    items = real_parse(req.text) if _has_key() else fake_parse(req.text)
    return validate(items)
