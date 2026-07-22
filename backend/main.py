"""
灵笺 Lingjian · 后端代理层 (FastAPI)

当前 = 泳道1「假后端」:`/parse` 直接返回 §7 约定的 9 字段示例数组,
用来把「前端 fetch 链路 + 降级兜底 + AI在线/离线徽章」先跑通,**不需要 DeepSeek key**。

泳道2(key 到手后):把 `/parse` 里的 `fake_parse()` 换成 `real_parse()`(真调 DeepSeek)。
前端一个字都不用改 —— 因为两者返回的字段形状完全一致(见 README §7)。
API key 只在 `real_parse()` 里从环境变量读,严禁硬编码、严禁进 git / apk / 前端。

本地跑:  pip install -r requirements.txt  &&  uvicorn main:app --reload --port 8000
自测:    curl http://localhost:8000/health
         curl -X POST http://localhost:8000/parse -H 'Content-Type: application/json' \\
              -d '{"text":"明天上午写完实验部分,晚上八点陪我妈散步半小时,这周得去趟医院"}'
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Lingjian Backend", version="0.1.0-fake")

# 开发期放开跨域:前端 HTML(file:// 或 http://localhost)要能 fetch 到本后端,
# 不加这个,浏览器会因 CORS 拦掉请求 → 前端每次都走本地兜底,徽章永远"离线"。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 泳道3 上线时可收窄到具体来源
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模型设成配置项,别硬编码(README §8:别用已停用的 deepseek-chat/reasoner)
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-flash")

# §7 约定:domain 只能是这 6 个之一,前端 paint() 只认它们,否则渲染崩
VALID_DOMAINS = {"work", "study", "life", "health", "social", "leisure"}
REQUIRED_FIELDS = {"title", "domain", "time", "deadline",
                   "est", "load", "restorative", "conf", "day"}


class ParseReq(BaseModel):
    text: str


@app.get("/health")
def health():
    """让评委/自己不装 apk 也能确认后端真活着(README §10)。"""
    return {"ok": True, "mode": "fake", "model": MODEL}


def fake_parse(text: str):
    """泳道1 假后端:返回一条符合 §7 的示例数组(9 字段 + domain 合法)。
    形状与真后端完全一致,专门用来先把前端链路跑通,不依赖任何 key。
    """
    return [
        {"title": "写完实验部分", "domain": "work",   "time": "上午", "deadline": "明天", "est": 90, "load": "deep",   "restorative": False, "conf": 93, "day": 1},
        {"title": "陪妈妈散步",   "domain": "social", "time": "晚上", "deadline": "今天", "est": 30, "load": "light",  "restorative": True,  "conf": 88, "day": 0},
        {"title": "去趟医院",     "domain": "health", "time": None,   "deadline": "本周", "est": 60, "load": "medium", "restorative": True,  "conf": 72, "day": 0},
    ]


def real_parse(text: str):
    """泳道2 占位:key 到手后启用。真调 DeepSeek(v4-flash, JSON 模式, 注入服务器时间)。
    现在不被调用 —— 切换只需把 `/parse` 里的 fake_parse 改成 real_parse。
    完整写法见 README §8(此处保留骨架,提示词/时间注入到时补全)。
    """
    from openai import OpenAI  # 延迟导入:泳道1 没装 openai 也不影响后端启动
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],       # ← key 只在这里,从环境变量读
        base_url="https://api.deepseek.com",           # ← OpenAI 兼容,只改 base_url
    )
    raise NotImplementedError("泳道2 待接入:见 README §8 的最小可用写法")


def validate(items):
    """后端再校验一遍(§7 硬要求):字段齐 + domain 合法 + day 是整数;不合格的项丢弃。
    假后端已保证合格;真后端接 DeepSeek 后,这层负责兜住模型偶发的脏输出。
    """
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
    # ▼▼▼ 泳道2 唯一切换点:把 fake_parse 换成 real_parse 即接真 DeepSeek,前端不用改 ▼▼▼
    items = fake_parse(req.text)
    # ▲▲▲
    return validate(items)
