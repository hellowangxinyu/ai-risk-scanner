# AI 财务风控系统

面向企业内部使用的客户风险扫描系统：**客户维护 → AI 风险扫描 → 风险台账表**。
单并发使用（uvicorn 单进程 + SQLite），部署于 Linux 服务器（venv + systemd，无需 Docker）。

开源协议：[MIT](LICENSE) —— 欢迎使用、修改与二次开发，请保留版权声明。

## 功能

| 页面 | 说明 |
|---|---|
| 客户管理 | 客户增删改查、搜索分页；Excel 模板导入 + 粘贴文本导入，重复跳过、失败行出报告（行号+原因）；同机构下客户名称唯一，默认机构可在系统配置修改 |
| 风险扫描 | 勾选客户（一键勾选到期客户）→ 后台逐客户串行调用大模型 → 实时进度（Token/估算费用）；批次按日存储、永不覆盖；中断/失败批次可删除或"按原客户清单重扫" |
| 风险台账 | **只显示有风险的记录**；默认"最新批次"视图，可切"每客户最新状态"（最近批次扫干净的客户自动消失）与历史批次；按等级/类型/客户筛选；高风险置顶；导出 Excel |
| 系统配置 | AI 接口（Base URL / API Key / 模型名，默认 DeepSeek，任意 OpenAI 兼容服务可换）、**账户余额查询、模型列表一键获取**、联网搜索开关（**DeepSeek 原生搜索**或博查）、分级扫描周期、每日自动扫描、成本单价、累计用量 |

## 风险数据来源与免责

- 默认数据源：**DeepSeek 原生搜索（复用 AI API Key）或博查搜索（可选）+ DeepSeek 归纳**。
  - DeepSeek 原生搜索：走 Anthropic 兼容 Messages 端点（`/anthropic/v1/messages`）的 `web_search` 服务端工具，每次搜索消耗一个完整模型轮次（按 Token 计费，无单次搜索费），单次请求最多 5 次服务端搜索
  - 博查搜索：约 ¥0.036/次，需单独申请博查 API Key
  - 任一提供方搜索失败自动降级为纯模型知识，并在"来源"中注明
- 所有风险记录的来源均标注"AI 检索/分析，**仅供参考**"，不构成权威工商、司法数据；重要决策请以企查查/天眼查等官方渠道为准。
- 已预留 MCP 权威数据源接口（`backend/datasource.py`）：购买企查查（官方 MCP，API 套餐起步几百元）或天眼查（开放平台 Token，有免费额度）后可接入。

## 核心机制

1. **到期判定**：从未扫描 → 到期；否则 `上次扫描时间 + 间隔(上次风险等级) ≤ 今天` → 到期（高3天/中7天/低·无30天，可配）。
2. **中断恢复**：进程重启时自动把遗留"运行中"批次标记为"中断"，可在扫描页删除或重扫。
3. **自动扫描护栏**（可选启用，默认 02:00，建议放在 DeepSeek 空闲折扣时段 00:30–08:30）：已有运行中批次则跳过；错过时刻（宕机）启动后补跑。
4. **成本可视化**：每次调用记录 Token 用量与搜索次数；批次写入当时单价快照，金额一律为"估算"，单价可在设置页更新。
5. **AI 返回容错**：`response_format=json_object` 优先（不支持自动回退）；剥 ```json 围栏后按"首 { 至末 }"截取解析；失败重试一次，原因入库。

## 本机开发运行（Windows）

```
1. 双击 build_and_package.bat      （构建前端 + 打包；或手动：frontend 下 npm install && npm run build）
2. 双击 start.bat                  （创建 venv、装依赖、启动 http://127.0.0.1:8000）
```

默认口令 `admin123`（本机调试用；正式部署务必设置 APP_PASSWORD）。

## 服务器部署（Linux，无需 Docker / 无需 Node）

```
1. 本机双击 build_and_package.bat → 得到 fengkong-dist.tar.gz
2. 上传服务器：  scp fengkong-dist.tar.gz user@server:/opt/
3. 解压：        cd /opt && tar -xzf fengkong-dist.tar.gz -C fengkong --strip-components=0
   （得到 /opt/fengkong/backend、/opt/fengkong/deploy 等）
4. 装依赖：      cd /opt/fengkong && bash deploy/deploy.sh        （服务器需 Python 3.10+）
5. 配置口令：    编辑 deploy/fengkong.service 的 Environment=APP_PASSWORD=你的口令
6. 启动：        sudo cp deploy/fengkong.service /etc/systemd/system/
                 sudo systemctl daemon-reload && sudo systemctl enable --now fengkong
7. 访问：        http://服务器IP:8000
```

> 前端 dist 已随包含入，服务器不需要 Node；数据落在 `backend/data/app.db`。

## AI 配置

在"系统配置"页填写：

| 配置 | 默认值 | 说明 |
|---|---|---|
| Base URL | `https://api.deepseek.com/v1` | 任意 OpenAI 兼容接口 |
| API Key | 空 | DeepSeek 平台申请；配置后可在页面一键查询账户余额、获取模型列表 |
| 模型名称 | `deepseek-flash` | 当前主力模型（高峰输入 ¥2/M、输出 ¥8/M，空闲时段减半）；可改 deepseek-v4-pro 等 |
| 搜索提供方 | DeepSeek 原生搜索 | 复用 AI Key；也可选博查（约 ¥0.036/次，需单独申请 Key） |

填好后点"测试 AI 连接 / 测试搜索连接"验证。

## 成本量级（按可配单价估算）

deepseek-flash 牌价（2026-09）：高峰时段输入 ¥2/M、输出 ¥8/M，空闲时段（工作日 18:00–次日 9:00 及周末）减半，缓存命中输入 ¥0.02–0.04/M。

- 单客户单次扫描：纯模型知识约 ¥0.005–0.01；联网搜索（原生搜索多消耗一个模型轮次）约 ¥0.02–0.05
- 100 家客户、分级周期（高 3 天/中 7 天/低·无 30 天）+ 联网搜索：约 ¥10–25/月
- 实际以 DeepSeek 账单为准，系统内单价可随时更新，金额一律为估算值

## 备份

所有业务数据在 `backend/data/`（含 app.db 与 WAL 文件），定期拷贝该目录即可；恢复 = 停服务 → 覆盖目录 → 起服务。

## 单测

```
cd backend && .venv/Scripts/python -m pytest tests -q     (Windows)
cd backend && .venv/bin/python -m pytest tests -q         (Linux)
```

覆盖：宕机补跑判定、到期判定、JSON 首{至末}容错、response_format 400 回退、失败重试、搜索降级、导入行校验。
