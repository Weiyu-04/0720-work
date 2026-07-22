# 灵笺后端 · FastAPI 代理层

当前是 **泳道1 假后端**:`/parse` 返回写死的 §7 九字段示例,用来把前端链路先跑通,
**不需要 DeepSeek key**。真调 DeepSeek 是泳道2(见文末)。

## 本地运行(Mac / 任意)

```bash
cd backend
pip install -r requirements.txt          # 建议先建 venv: python3 -m venv .venv && source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

自测:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/parse -H 'Content-Type: application/json' \
  -d '{"text":"明天上午写完实验部分,晚上八点陪我妈散步半小时,这周得去趟医院"}'
```

`/parse` 应返回一个含 3 个元素的 JSON 数组,每个元素严格 9 字段(见根 README §7)。

## 配合前端一起看效果

前端要用 **http 方式**打开(别用 `file://` 双击,否则浏览器会拦跨域请求):

```bash
# 在仓库根目录另开一个终端
python3 -m http.server 8080
# 浏览器打开 http://localhost:8080/lingjian-app%20(17).html
```

前端里的后端地址是 HTML 顶部的 `LJ_API_BASE`(默认 `http://127.0.0.1:8000`)。
说一句话后,结果顶部会出现徽章:**绿色"● AI 在线"= 走了后端**;
**琥珀"○ 离线示例"= 后端不可达、回退了本地兜底**(把后端停掉即可复现)。

## 泳道2:接真 DeepSeek(拿到 key 之后)—— 代码已就位,只需放 key

`real_parse()` 已按 §8 写好(system 提示词 + 注入服务器时间 + JSON 模式 + 空返回重试 + 后端校验)。
`/parse` 会**自动判断**:环境里有 `DEEPSEEK_API_KEY` 就走真调,没有就走假后端。所以你要做的只有:

```bash
cd backend
cp .env.example .env          # 然后编辑 .env,把 DEEPSEEK_API_KEY 填成你的真 key
# ⚠️ .env 已被根 .gitignore 忽略,绝不提交、绝不发聊天、绝不进 apk
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**怎么确认真调生效**:
```bash
curl http://localhost:8000/health
#  {"ok":true,"mode":"live","model":"deepseek-v4-flash"}   ← mode=live 就是走真调了(fake=还没读到 key)
```
再喂一句**跟示例不同的**话,看是否真解析了你说的内容(假后端只会永远返回那 3 条):
```bash
curl -X POST http://localhost:8000/parse -H 'Content-Type: application/json' \
  -d '{"text":"后天下午两点交课程作业，今晚十点前给导师回邮件"}'
```
前端里说/打这句话,顶部徽章应是绿色 **"● AI 在线 · 后端实时解析"**,且卡片内容就是你说的那两件事。

**前端一个字都不用改** —— 返回字段形状与假后端完全一致。若真调偶发失败,`/parse` 返回空数组,前端会自动回退本地兜底(琥珀"离线"徽章),不白屏。
