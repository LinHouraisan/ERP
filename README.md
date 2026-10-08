# 营业厅经营与 AI 服务工作台 · 阶段一至三

当前交付：**第三阶段异常处理、跨期结算和同主体两店联动已接通并填入演示数据**。新增组合交易、退货退款、通信冲正、施工受阻与退料、提成分批释放及后续抵扣、调拨盘点和统一待办。保留一二期服务、销售与收益历史；资金、客户和通信单据仍全部为模拟数据。

用户已授权使用本地 DeepSeek 密钥及全部模拟演示数据。现在有 33 条成功的真实 AI 运行；第三阶段新增一条通信质检，实际 678 tokens。正式人工标签核对与 V1/V2 比较尚未完成，不能据此宣称模型效果提升。先看 [三期操作指南](docs/阶段三操作指南.md)、[三期实际验收与数据记录](docs/实施记录/phase3.md)。[二期指南](docs/阶段二操作指南.md)、[二期记录](docs/实施记录/phase2.md) 和 [一期数据记录](docs/实施记录/phase1-demo-data.md) 保留历史证据。

## 在本机打开

工作台：http://127.0.0.1:5173 。取号页：`/take-number`；公共屏：`/public-board`。

账号为 `staff`、`manager`、`admin`、`warehouse`、`installer`、`finance`，分别对应店员、店长、管理员、仓库、装维、财务。初始口令来自本机私有 `.env` 的 `DEMO_PASSWORD`，不要复制到 Git、聊天或截图中。初始化不会覆盖已有用户口令。

第二店账号在上述名称后加 `2`，例如 `admin2`、`warehouse2`。账号固定属于自己的门店，调拨单只对相关两店开放；二店账号不能读取一店客户和财务。默认首页为统一待办。

已有环境在项目根目录启动：

```powershell
.\.venv\Scripts\python.exe scripts/start_local.py
```

保持终端打开；Ctrl+C 只停止本次启动的应用进程。PostgreSQL 保持运行。端口已占用时启动器直接退出，不停止已有进程；已经打开的工作台可直接使用。需后台运行时加 `--background`，记录输出的进程号，日志在 `.local/`。

## Windows 首次安装

已验证 Python 3.12.14、Node 24.21.0、npm 11.19.0、PostgreSQL 18.6。Python 和前端依赖分别由 `requirements.lock`、`package-lock.json` 锁定。

在项目根目录运行（机器需已安装 Python 3.12 和 Node 24）：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
npm --prefix frontend ci
.\.venv\Scripts\python.exe scripts/setup_local_postgres.py
.\.venv\Scripts\python.exe scripts/start_local.py
```

数据库安装脚本从 PostgreSQL 官方下载渠道获取固定版本并检查 SHA-256，约 367 MiB，只写项目 `.local/`。它生成 `.env` 中的随机本地口令，仅监听 `127.0.0.1:55432`，建立 `erp_demo`、`erp_phase1_test` 和分离的 `erp_app` / `erp_mock` 角色，不安装系统服务、不重置已有数据库。首次启动执行 Alembic 迁移和幂等种子。

本机服务：前端 5173、主 API 8000、独立 Mock 8001、数据库 55432。`/health/live` 检查进程，`/health/ready` 检查数据库及迁移版本。模型调用不参与健康检查。

## DeepSeek 本地配置

编辑根目录私有 `.env`，不改前端：

```dotenv
AI_MODE=deepseek
DEEPSEEK_API_KEY=在本地填写你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

重启主 API。页面横幅会显示当前模式。在“提示词与运行”检查实际运行的状态、模型标识、耗时、错误与提供方返回的 token 用量。模型名称可按自己账号的可用模型修改。恢复离线只需设 `AI_MODE=offline` 并重启。

适配集中在 `backend/app/integrations/ai.py`，使用锁定的 `langchain-deepseek`；单次请求 30 秒，整个流程 60 秒，格式修复至多一次，最多两次请求。没有自动启动付费评测。未返回用量时保存未知，失败时保留已知用量。AI 失败仍可人工填写需求、使用规则方案并复核办理。

真实模型辅助需求、解释、质检、改进、销售选品和经营摘要，六类场景均有实际成功调用。价格、资格、权限与业务终态仍由服务端决定；经营数字和引用核对快照，文字解释需要人工复核。当前明确关闭 thinking，以限定结构化输出的延迟与用量。适配资料：[DeepSeek API](https://api-docs.deepseek.com/)、[LangChain DeepSeek](https://docs.langchain.com/oss/python/integrations/chat/deepseek)。

## 数据与结构

```text
backend/        FastAPI 模块化业务后端、Alembic 001—021、测试、评测用例
frontend/       React 工作台、公共页面、Playwright 场景
mock_boss/      独立 HTTP 模拟系统、Alembic 001—005、合同测试
scripts/        本机启动、测试准备、迁移检查、备份恢复和受限重置
docs/实施记录/  当前进度、实际证据及评测说明
```

Mock 种子提供 14 个模拟账号；主应用客户按查询或人工登记形成。资料包括原 8 个套餐/服务、一店及二店各 7 项实物/服务/款项政策、3 类业务、3 个窗口、20 条预置已结束服务和 6 类 V1 提示词。实名、新客、在网时长、优惠互斥、在约限制、宽带保留和适用区域使用明确规则；固定折扣由后端计算。业务时区为 Asia/Shanghai；历史样本日为 2026-10-02；种子政策有效期为 2026-01-01 至 2027-12-31，首尾日包含。

模拟号码 `19900000001` 至 `19900000013`。初始 01 为 129 元含宽带账号；02 仍在约；03 合约到期日为 2026-10-02；04 月费未知；05 实名未知；06 不含宽带；07 有互斥优惠；08 新客；09 有欠费限制；10 在网时长未知；12 查询超时；13 合约于 2026-10-15 到期。目前 01、07、11 已在演示中由 Mock 更新为 89 元；07 在主应用中保留 UNKNOWN，供按原请求号核对。新演示可查询尚未变更的 03。初始化不会还原已办理事实。

补齐整套业务演示数据的入口（默认需显式允许付费，保留既有数据）：

```powershell
.\.venv\Scripts\python.exe scripts/populate_demo.py --live --max-spend-cny 2
```

一期步骤保存在私有 `.local/demo-data-ledger.json`，重复运行跳过已完成步骤和付费调用；当时形成 30 条服务、6 张票、4 笔受理、7 个服务任务、16 份评价和 2 个改进任务。二期已追加为 31 条服务、8 个任务，以及 3 张采购单、4 张销售单、2 张安装单等经营数据。二期入口为：

```powershell
.\.venv\Scripts\python.exe scripts/populate_phase2.py --demo --live --max-spend-cny 0.50
```

二期进度在 `.local/phase2-data-ledger.json`，不带 `--live` 不调用模型。两个脚本都只面向本项目演示库和本机 API；本机已填充，不需要重复执行。不要删除进度文件来重复造单，重建环境后先核对进度与业务状态。

三期入口为 `scripts/populate_phase3.py`，进度保存在 `.local/phase3-data-ledger.json`。它通过本机接口追加两店销售、售后、冲正、分期结算、调拨和盘点，不清空原数据；包含一笔依当前 AI 模式执行的通信质检。当前已运行完成，重复运行跳过已记录步骤。新号码 `19900000014` 已演示先办理 89 元套餐、再冲正恢复到 129 元，原成功办理仍可追溯。

金额存 NUMERIC / Decimal，接口传十进制字符串；发布政策、查询快照、推荐、质检和统计快照保留历史。排队、接待、受理和服务任务分别保存状态。提交超时先记 UNKNOWN，核对必须使用原 `external_request_id`。主应用数据库角色不能读取 Mock 的表。

## 必要验证

先准备专用测试库；脚本只接受 `erp_phase1_test`：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_tests.py
npm --prefix frontend run e2e -- service-flow.spec.ts ai-fallback.spec.ts unknown-result.spec.ts admin-pages.spec.ts
npm --prefix frontend run e2e -- phase2-flow.spec.ts
npm --prefix frontend run e2e -- phase3-flow.spec.ts
npm --prefix frontend run build
```

Playwright 使用 8002—8004、5174—5175，自动启动测试 API 和网页；已存在的 8002 Mock 可复用，必须确认它指向测试库。Windows 检测本机 Edge；其他环境需先在 frontend 安装 Playwright Chromium。测试固定模型返回，故障场景故意不给模型密钥，不访问付费 API。

后端局部测试需要测试 Mock。在另一个终端运行 `scripts/prepare_tests.py --serve-mock`（8002 已运行则不用重复启动），然后：

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py tests/test_quality.py tests/test_authz.py -q
Set-Location ../mock_boss
..\.venv\Scripts\python.exe -m pytest tests/test_contract.py -q
```

检查按变更选择相关场景，不默认反复全量运行。实际结果见 [三期记录](docs/实施记录/phase3.md)；三期后端局部检查在 `tests/test_phase3_*.py`。测试与演示数据库隔离。

评测默认离线；在 backend 运行：

```powershell
..\.venv\Scripts\python.exe -m app.modules.evaluations.cli --cases evaluation/cases.jsonl --split dev --prompt-version V1
```

30 条用例目前均为待人工核对草稿。真实执行必须填写 `review_status=CONFIRMED` 和 `reviewer`，明确调用预算，再显式加 `--live --max-calls 40`（20 例、每例最多两次；调用次数不是金额预算）。保留集不得拿来逐题调参；冻结流程和未执行项见 [评测记录](docs/实施记录/phase1-evaluation.md)。

仅验证真实调用而不评价模型质量时，可以使用 `--live --smoke --max-calls 40`。该模式只接受开发集，保留待核对标签，不生成 TP/FP/FN、精确率或召回率。当前已有一次 20 条全成功的试跑，不必重复消耗额度。

## 迁移、备份、恢复与重置

启动器迁移现有库，不使用运行时 `create_all`。独立验证空库及上一版本升级：

```powershell
.\.venv\Scripts\python.exe scripts/check_migrations.py
.\.venv\Scripts\python.exe scripts/database.py backup
.\.venv\Scripts\python.exe scripts/database.py restore-check --backup .local/backups/替换为实际备份目录
```

备份通过同一 PostgreSQL 快照分别导出 app / boss，保存在私有 `.local/backups/`。恢复只创建新的 `erp_restore_时间_test`，核对业务表和 Mock 回执摘要，不覆盖源库。三期备份 `.local/backups/20261003T050007516083Z` 已完成隔离恢复，26 组业务数据及 5 组 Mock 数据摘要一致；未知受理、付款和退款的原请求号保留。涉及真实外部系统时不得用本演示恢复流程直接覆盖其状态。

确需清空本项目演示数据时，先停止所有演示 API / Mock 写入，再运行：

```powershell
.\.venv\Scripts\python.exe scripts/database.py reset --reset-demo --confirm-database erp_demo
```

此命令检查环境、库名、角色和本项目种子标识，拒绝存在未决受理、付款、退款或冲正的库；先备份，再清空业务表并重新种子，不删除迁移记录。**本次验证了拒绝误用保护，未在现有演示库实际执行重置。** 专用测试清理由测试夹具管理。

## 容器入口

已提供 Compose、三份 Dockerfile、Nginx 配置及固定镜像标签。环境准备后执行：

```powershell
.\.venv\Scripts\python.exe scripts/init_env.py
docker compose config --quiet
docker compose up --build -d
```

网页仍为 5173，容器数据库默认映射本机 55433；容器内使用分离角色，各自迁移完成后启动。不要与本机版同时占用 5173。`.env` 中的数据库 URL 默认对应本机版，容器服务由 Compose 注入容器内 URL；宿主机备份脚本不会自动切换目标。

本机缺少 Docker 引擎：Compose 配置解析通过，`up --build` 已尝试但在连接引擎时失败，镜像构建与容器运行未验证。本次可运行交付采用上述本机路径。

## 交付范围与限制

- [一页操作指南](docs/阶段一操作指南.md)、[十分钟演示脚本](docs/阶段一演示脚本.md)、[任务与验收证据](docs/实施记录/phase1.md)。
- [二期操作与演示指南](docs/阶段二操作指南.md)、[经营演示数据](docs/实施记录/phase2-demo-data.md)、[二期施工与验收](docs/实施记录/phase2.md)。二期完整浏览器正常链、角色页面、局部后端检查、构建、升级和恢复通过。
- 离线三个核心浏览器场景及后台审核/修订场景通过；备份恢复、原号核对和上一版本升级已实测。真实 DeepSeek 四类调用及开发集试跑通过；标签确认和正式 V1/V2 结论仍待完成。
- 自由文本只对明确标注的月费及合约等做确定性检查，歧义文本必须人工复核；不能把没有报错理解为全面语义合格。
- 三期提供同主体两家门店、组合交易、售后冲正、跨期结算、调拨盘点和待办；详见 [技术落点](docs/技术施工/06_阶段三Agent执行计划.md)。没有生产部署、真实资金收付或真实提成发放。
- 每张调拨单对应一个商品编码；跨主体调拨未开放。旧受理没有办理前快照时只允许人工核查；结果未知不能人工伪造为成功。部分列表显示最近 100/300 条；前端主包约 1.23 MB，构建保留体积提示。
- 本地私有口令、数据库、日志和截图均在忽略目录。没有提交、推送或公网发布。
