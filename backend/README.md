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

## 泳道2:接真 DeepSeek(拿到 key 之后)

1. `cp .env.example .env`,填入 `DEEPSEEK_API_KEY`。⚠️ `.env` 已被根 `.gitignore` 忽略,**绝不提交**。
2. `main.py` 里 `/parse` 把 `fake_parse(req.text)` 换成 `real_parse(req.text)`,
   并按根 README §8 补全 system 提示词 + 注入服务器当前时间 + JSON 模式 + 空返回重试。
3. **前端一个字都不用改** —— 返回字段形状与假后端完全一致。
