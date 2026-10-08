# 阶段一 Agent 完整执行细则 Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task when available. Default to one agent. Do not start subagents without explicit authorization. Track steps with `- [ ]`. Current user and environment instructions take precedence.

**Goal:** 目标是在现有项目中完成可独立运行的第一阶段：取号与叫号、客户业务查询、需求分析、套餐或服务建议、质检与人工确认、BOSS Mock 受理、客户评价、后台改进与版本评测。

**Architecture:** 一个 FastAPI 业务后端按模块组织，PostgreSQL 保存事实与历史；React 提供页面；固定 AI 流程辅助理解和解释；BOSS Mock 单独通过 HTTP 提供模拟查询和办理。

**Tech Stack:** React, TypeScript, Vite, Ant Design, React Router, TanStack Query, Python, FastAPI, Pydantic, PostgreSQL, SQLAlchemy, asyncpg, Alembic, LangChain.

**Spec:** [AGENTS.md](../../AGENTS.md)、[第一阶段规划](../项目规划/01_第一阶段独立规划书_营业厅AI服务与质检工作台.docx)、[01 详细施工报告](01_技术施工报告_第一阶段与后续扩展.docx)、[02 通用规则](02_Agent施工规则与交付规范.docx)、[03 架构说明](03_软件架构设计与技术选型说明.docx)。

**版本与状态:** V1.0；2026-10-02；步骤执行标记已更新至 2026-10-03；任务与验收结论以 docs/实施记录/phase1.md 为准。离线工程与真实模型接入通过，正式效果评测及完整阶段验收待完成。

默认由一个 Agent 顺序执行。获得用户的阶段一实施指令后，完成一个任务即推进下一项，不把每个任务都变成新的审批；环境、凭证或业务标注未就绪时，先完成不依赖它们的工作。

## Global Constraints

只实施第一阶段；默认单 Agent；使用模拟数据；遵守后端权限、版本绑定、短事务、幂等与未知结果核对；普通测试不调用收费模型；不扩建二三期空模块。详细值见第 2、4、5 章。

## Review Focus

- 缺字段不补零：T04、T05。
- 推荐改动导致旧确认失效：T07、T10。
- 外部成功后超时不重复办理：T09、T10。
- 双窗口并发不抢同一票：T08。
- 无评价、零分母及越权不产生误导结果：T02、T11、T12、T14。

## 1 执行入口与完成标准

### 先读这些文件

先读根目录 AGENTS.md，再读本细则。业务目标见第一阶段独立规划书；数据、状态和接口细节见 01 技术施工报告详细版；通用工作纪律见 02；设计理由见 03。简明版用于理解，不用于替代关键约束。

本细则将原 M0—M4 拆成 T00—T17 共 18 个任务。先按依赖完成任务，再核对阶段关口 G0—G4。任务编号用于续接，不代表工期。原 120—160 小时只是单人开发估算，实际以完成证据为准。

| 关口 | 对应任务 | 必须能展示的结果 |
| --- | --- | --- |
| G0 | T00—T04 | 应用可启动；登录后能查询模拟号码，并看到资料来源和更新时间。 |
| G1 | T05—T07 | 需求、规则推荐、AI 解释、质检和人工复核连通；资料不足和人工模式可用。 |
| G2 | T08—T11 | 取号到评价完整；并发叫号不重复；受理未知可核对；成功更新模拟业务资料。 |
| G3 | T12—T13 | 改进任务有证据；用例经过核对；有真实模型评测及一次实际问题的修复记录。 |
| G4 | T14—T17 | 必需页面可操作，关键验收通过；新环境能演示；交付、备份和恢复有证据。 |

### 什么才算阶段一完成

全部必需任务与 A01—A08 验收有可复查的通过证据；真实模型接入与版本比较已完成；交付物齐全；没有未处理的错价、越权、重复办理、错误成功状态或数据丢失问题。

若只有固定模型返回值的离线演示通过，应写“离线工程验收通过，真实模型验收待完成”。不得用页面齐全、构建成功或测试数量代替完整业务验收。

## 2 开工约定与 Agent 的自主范围

### 可以直接采用的实施默认值

采用 React、TypeScript、Vite、Ant Design、React Router、TanStack Query；后端为 Python、FastAPI、Pydantic、SQLAlchemy、Alembic、asyncpg 和 PostgreSQL；AI 集中使用 LangChain。具体兼容版本在 T01 验证并锁定。

单门店、3 类业务、3 个窗口，店员、店长、管理员三种角色。浏览器按中文展示，业务日期按 Asia/Shanghai 解释。开发端口建议前端 5173、后端 8000、Mock 8001；有占用时换空闲端口并更新启动说明，不停止无关服务。

一个业务后端，内部按功能分模块；BOSS Mock 是同仓库内独立 HTTP 服务。先完成当前任务需要的文件和数据表。二三期的采购、库存、收银、完整派工、财务结算及 GEO 不进入本期。

### 只把真正缺少的外部条件交给用户

| 事项 | Agent 的处理方式 |
| --- | --- |
| 模型调用 | 启动时核对已有授权，只询问尚缺的提供方、模型标识、安全凭证配置方式和调用预算。密钥不写入聊天、Git、页面或日志；调用只发送必要的模拟资料。 |
| 业务用例核对 | Agent 可以起草 30 条用例和预期；需要业务判断的标签集中交用户或指定业务人员核对一次。已确认的样本直接沿用，不能将 Agent 自拟标签声称为人工标注。 |
| 本地开发 | 在授权的工作区中创建代码、项目内依赖、测试、迁移和演示数据；读取现有配置时不输出密钥。需系统权限或额外安装时遵循当前环境审批。 |
| 超出开发范围 | 公网发布、真实系统接入、超预算付费、破坏性数据操作须有对应授权。普通可逆实现细节自行决定；已有明确授权不重复索要。 |

### 工作方式

用户只要求生成本细则时，交付文件即完成本次任务，不自动开始开发。用户发出实施指令后，默认由同一个 Agent 按顺序执行；本细则不授权并行子 Agent。需要子 Agent 时遵循用户与当前环境的明确授权。

执行阶段可使用 superpowers:executing-plans 逐项推进。技能不可用时仍按本文任务和当前环境规则执行，不自行安装插件或扩大权限。

## 3 每个任务怎样完成和续接

每个任务按“核对输入与直接调用方 → 写能暴露目标问题的检查 → 最小实现 → 局部验证 → 记录结果”推进。非平凡业务逻辑先观察测试因目标行为尚未实现而失败；配置、文档和纯布局不强行写无意义测试。

依赖优先完成。若上游仅联网调用或人工核对受阻，且后续所需的离线接口已实现并验证，可先做后续独立步骤；受影响的通过标记继续保留阻塞。T13 未取得真实评测时，可先做 T14—T16 的页面、部署和浏览器验证。

任务中的文件为相对仓库根目录的拟定路径。已有实现存在时优先复用；路径需要调整就在进度记录中说明，并同步本细则的 Markdown 执行版。修改 HTTP 合同或状态含义时必须检查直接消费者，不能只改当前页面。

### 只维护一份施工进度记录

T00 创建 docs/实施记录/phase1.md。每项任务状态仅使用未开始、进行中、通过、依赖阻塞。测试失败的任务保持进行中；有未完成步骤不能勾选通过。

```text
任务 Txx | 状态 | 本次目标
已改文件及接口或迁移
验证命令 | 工作目录 | 实际退出码 | 关键断言
未通过项或外部依赖 | 对完成标准的影响
下一步具体动作 | 当前分支及最近提交或工作区状态
```

命令涉及凭证时仅记录脱敏形式。没有执行的检查写明原因。任务通过后按当前授权决定是否本地提交；若提交，只暂存本任务明确文件，不使用 git add . 混入原有文档或他人修改，不自动推送或发布。

### 中断后从哪里继续

先读 AGENTS.md、本细则和 phase1.md，再核对当前文件与最近改动。找到第一个未通过且依赖已满足的任务继续。已有通过证据且未被后续改动影响的检查不重复运行。

同一阻碍经过两次有明确原因的修复仍未解决，就记录报错、已试方法和需要的条件，推进独立任务；不要无限重试收费请求、重装环境或改用另一套基础架构。全部剩余工作都依赖外部条件时，如实报告阻塞，不能宣布完成。

### 五项重点复核

测试必须覆盖：查询缺字段不能变成零费用；推荐改动后旧确认失效；外部成功但响应超时不能重复办理；不同窗口并发不能抢到同一张票；无评价、零分母和越权访问不能产生误导结果。分别由 T04—T05、T07与T10、T09—T10、T08、T02与T11—T12负责。

## 4 文件职责与公共数据约定

| 拟定位置 | 负责什么 |
| --- | --- |
| frontend/src/app | 路由和应用入口。lib/api.ts 处理请求；features 下放具体业务页面。 |
| backend/app/core | 配置、数据库连接、登录依赖和统一错误；main.py 注册模块。 |
| backend/app/modules/<业务> | router.py 管接口，schemas.py 管输入输出，models.py 管数据结构，service.py 管业务动作；复杂计算才拆 rules.py。 |
| backend/app/integrations | ai.py 集中模型调用；boss.py 集中 Mock 协议。业务层不得直接读取 Mock 表。 |
| mock_boss/app | main.py、schemas.py、models.py、service.py、scenarios.py；独立进程、独立数据库角色与 schema。 |
| backend/tests 与 mock_boss/tests | 规则、数据库、权限与协议测试；使用专用测试 PostgreSQL。 |
| frontend/tests/e2e | 三条关键浏览器流程；实际调用测试后端。 |
| docs/实施记录 | 施工进度、评测报告和阶段验收证据。 |

模块按 auth、catalog、services、accounts、recommendations、quality、queue、acceptances、feedback、improvements、evaluations 逐项建立。提示词和 AI 运行归入 recommendations；服务任务归入 services，先不增加独立流程平台。

### 所有模块共同遵守

统一 UUID 标识和 store_id；时间存 UTC，业务日期显式转换；金额用 Decimal 与 NUMERIC(12,2)，API 传十进制字符串，未知为 null。API 前缀 /api/v1；错误返回 code、message、request_id、details，状态冲突返回 409。

政策、账号快照、推荐和提示词发布后保留不可变版本。推荐引用 snapshot_id、policy_version_id、prompt_version_id 和 rule_version；人工确认绑定推荐版本和质检输入摘要。

核心表及约束按 01 详细版第 4—5 章实施；一张表只由所属业务模块推进写入。每个并发任务独立 AsyncSession；网络调用期间不持数据库锁。数据库唯一约束与外键负责最终保护，不能只靠页面检查。

授权由后端检查用户、门店、资源和动作。测试可建第二门店验证隔离，但第一阶段不因此扩展完整多店运营。公开接口使用专门返回结构，不把完整客户对象发送后再隐藏。

## 5 接口与确定性样本

以 FastAPI 的 OpenAPI 为接口合同。下列字段名在任务间保持一致；可选字段必须区分未填写与已知为空。前端读取后端计算结果，不另算资费。

```text
AccountSnapshot: snapshot_id, account_id, source,
  source_time, fetched_at, completeness, payload
DemandProfile: intent, budget, must_keep, issues,
  missing_fields
Candidate: candidate_id, product_id, policy_version_id,
  monthly_fee, one_time_fee, contract_months,
  eligibility, evidence_ids, unresolved_needs
Recommendation: recommendation_id, service_id,
  snapshot_id, revision, candidates, outcome
QualityReport: quality_check_id, input_hash, status,
  findings[{rule_id, field_or_excerpt, evidence_ids,
  explanation, suggested_revision}]
Acceptance: acceptance_id, recommendation_id,
  candidate_id, external_request_id, status,
  external_order_id, expected_version
```

eligibility 仅为 eligible、ineligible、unknown。推荐 outcome 支持 OPTIONS、KEEP_CURRENT、NO_MATCH、NEEDS_INFO、SERVICE_TASK；复合需求允许候选方案与服务任务建议同时存在。质检 status 为 PASS、BLOCKED、NEEDS_REVIEW。

### 统一演示样本

准备 12 个模拟客户、8 个套餐或服务、6 条活动或限制规则、3 类业务、3 个窗口、20 条标为预置数据的历史服务，以及 T13 的 30 条评测用例。具体生成标识与固定样本日期写入种子文件，不能冒充真实服务或实际模型运行。

固定规则测试日期为 2026-10-02。演示约定：政策起止日均包含当天；合约到期日当天仍在约，次日才结束。此约定仅用于 Mock，不代表真实运营商规则。

| 必须有的输入 | 可检验的预期 |
| --- | --- |
| 当前月费 129 元且保留宽带；候选 89 元也保留宽带、一次费 0、资格满足 | 已知月费差为 40.00；另列新合约和优惠期限，不把它称为无条件总节省。 |
| 79 元候选不保留宽带；客户要求必须保留 | 筛除该候选或明确不可办理，不仅因月费低就推荐。 |
| 合约未到期、一次费未知、账号不存在、政策过期 | 分别阻断或转待核查；未知金额不补零。 |
| 网络故障兼降费、已是合适方案、所有候选不适用 | 分别支持服务任务、保留当前套餐和无合适方案。 |

演示时钟与测试时钟可固定；正常服务按系统业务日期运行。不得把固定日期写死在生产业务规则中。

## 6 至 14 按顺序实施任务

### T00 核对现状并建立进度记录

**依赖:** 无

**Files:** docs/实施记录/phase1.md；仅阅读已有 AGENTS.md、规划文档和仓库状态。

**Interfaces:** 输出实际环境、当前文件基线、用户已授权范围、仍缺的外部条件和下一任务。

- [x] **步骤 1** 核对当前分支、未提交文件和现有实现；记录需保留的用户改动，不重置工作区。

- [x] **步骤 2** 检查可用 Python、Node、PostgreSQL 和容器工具；选择项目内环境，不因端口或版本不符覆盖现有服务。

- [x] **步骤 3** 一次性汇总尚缺的模型配置、预算和用例核对安排；不等待这些条件才开始普通工程工作。

- [x] **步骤 4** 建立 T00—T17 状态表和 G0—G4 验收栏；下一任务明确写 T01。

**验证命令与范围:** 只执行只读环境检查；将实际命令与结果写入 phase1.md。

**通过条件:** 工作区基线与阻塞项有记录；没有把未检查的依赖、凭证或脚本标为可用。

### T01 建立可启动工程和测试环境

**依赖:** T00

**Files:** frontend/package.json、frontend/src/app、frontend/src/lib/api.ts；backend/pyproject.toml、backend/app/main.py、backend/app/core/{config,db,errors}.py、backend/alembic/、backend/tests/conftest.py、backend/tests/test_bootstrap.py；mock_boss/pyproject.toml、mock_boss/app/main.py；compose.yaml、.env.example。

**Interfaces:** GET /health/live 表示进程可用；GET /health/ready 检查数据库和迁移就绪。环境区分开发、测试和演示，测试数据库名称必须明确。

- [x] **步骤 1** 建立后端连库、空库迁移和健康检查；写 test_ready_requires_database 与 test_empty_database_migrates，观察目标失败后实现。

- [x] **步骤 2** 建立 React 页面入口和代理 /api；定义 npm 脚本 dev、typecheck、build、e2e；Python 和前端各提交可复现锁文件。

- [x] **步骤 3** 建立独立测试 PostgreSQL 和清理约束；测试启动时拒绝连接演示或非测试数据库，不用 SQLite 替代锁与约束测试。

- [x] **步骤 4** 给 Mock 留独立启动入口和数据库角色；配置值从环境读取，.env.example 只有变量名与安全示例。

**验证命令与范围:** backend：python -m pytest tests/test_bootstrap.py -q；frontend：npm run typecheck 与 npm run build。

**通过条件:** 命令退出 0；新环境能启动空应用；数据库失败时 readiness 如实失败；密钥未出现在前端产物或示例配置。

### T02 实现登录和门店权限

**依赖:** T01

**Files:** backend/app/modules/auth/{router,schemas,models,service}.py；backend/app/core/security.py；frontend/src/features/auth/LoginPage.tsx；backend/tests/test_authz.py。

**Interfaces:** POST /auth/login、POST /auth/logout、GET /auth/me；CurrentUser 含 user_id、store_id、role。角色为 STAFF、MANAGER、ADMIN。

- [x] **步骤 1** 用测试钉住未登录 401、跨店不可访问、店员不能发布政策或审核改进；test_logout_revokes_session 必须通过。

- [x] **步骤 2** 实现数据库会话，令牌只保存摘要；浏览器用 HttpOnly Cookie，HTTPS 下 Secure；密码用成熟 Argon2 实现。

- [x] **步骤 3** 写动作检查 CSRF 和来源；登出、过期或用户停用立即失效。默认会话 8 小时。

- [x] **步骤 4** 实现登录页、当前身份与退出；权限由后端执行，前端隐藏按钮只是界面提示。

**验证命令与范围:** backend：python -m pytest tests/test_authz.py -q；检查一次跨店资源请求与实际响应体。

**通过条件:** 用户不能通过更换资源 ID 越权；登出后旧 Cookie 无效；错误信息不包含口令或令牌。

### T03 建立产品政策与固定演示资料

**依赖:** T01、T02

**Files:** backend/app/modules/catalog/{router,schemas,models,service}.py；backend/app/seed.py；backend/tests/test_catalog_versions.py；frontend/src/features/catalog/CatalogPage.tsx。

**Interfaces:** GET/POST /products；GET/POST /products/{id}/policy-versions；POST /policy-versions/{id}/publish。只允许管理员发布，已发布版本不可覆盖。

- [x] **步骤 1** 按第 5 章建立套餐、费用、合约、适用条件、有效期和来源；写 test_published_policy_is_immutable 与日期边界检查。

- [x] **步骤 2** 实现草稿维护和发布；修改已发布规则时新增版本，历史引用仍能打开当时资料。

- [x] **步骤 3** 提供 python -m app.seed --demo 幂等初始化；维护统一种子清单，当前只写已落表的身份与目录数据，后续任务补入对应实体，T15 核对总量。复跑不重复插入或重置已有服务。

- [x] **步骤 4** 建资料管理页和列表筛选；演示账号配置由本地安全输入生成，不在仓库中硬编码真实密码。

**验证命令与范围:** backend：python -m pytest tests/test_catalog_versions.py -q；专用演示库执行两次初始化并核对数量。

**通过条件:** 已发布资料只能新增版本；同一演示种子复跑不重复；样本有模拟标识、来源和日期。

### T04 接通服务记录和号码查询

**依赖:** T01、T02、T03

**Files:** backend/app/modules/services/{router,schemas,models,service}.py；backend/app/modules/accounts/{router,schemas,models,service}.py；backend/app/integrations/boss.py；mock_boss/app/{schemas,models,service,scenarios}.py；frontend/src/features/services/ServicePage.tsx；backend/tests/test_account_queries.py。

**Interfaces:** POST /service-sessions、GET /service-sessions/{id}、GET /service-sessions；POST /service-sessions/{id}/finish；POST /service-sessions/{id}/account-query。Mock：POST /mock/v1/account-query。

- [x] **步骤 1** 建立服务记录与客户、账号关联；没有账号也能接待，查询成功再关联。同一 queue_ticket 只关联一条服务；finish 将 ACTIVE 变为 ENDED，未决受理继续独立跟踪。

- [x] **步骤 2** 实现 HTTP Mock 查询，覆盖存在、未找到、字段缺失和超时；主应用保存不可变 AccountSnapshot，不直接读 Mock 表。

- [x] **步骤 3** test_missing_fee_stays_unknown 断言缺失费用为 null；test_query_history_keeps_snapshot 断言新查询不覆盖旧快照。

- [x] **步骤 4** 页面展示套餐、宽带、月费、优惠、合约、限制、来源时间和查询时间；区分未找到、失败与部分资料缺失。

**验证命令与范围:** backend：python -m pytest tests/test_account_queries.py -q；登录后操作四种查询情景，核对 G0。

**通过条件:** 来源与时间可见；未知字段不填零；号码不是客户唯一身份；服务历史可查且按门店隔离。

### T05 完成确定性推荐和人工处理路径

**依赖:** T03、T04

**Files:** backend/app/modules/recommendations/{router,schemas,models,service,rules}.py；backend/app/modules/services/service.py；frontend/src/features/recommendations/RecommendationPanel.tsx；backend/tests/test_recommendation_rules.py。

**Interfaces:** POST /service-sessions/{id}/recommendations 接收需求与 snapshot_id；GET /recommendations/{id}。GET/POST /service-tasks、POST /service-tasks/{id}/transition 维护服务任务。

- [x] **步骤 1** 实现 DemandProfile、Candidate、Recommendation 合同；先支持人工填写预算、必保服务和诉求，模型未接入也能选方案。

- [x] **步骤 2** 按政策、门店、账号条件、合约、互斥和必保服务筛候选，再算费用；用固定日期验证 129.00−89.00=40.00、79 元丢宽带被筛除、未知一次费不宣称总价。

- [x] **步骤 3** 最多展示三个可用方案；支持保留当前套餐、无合适方案、待补充资料与服务任务；网络故障可以与套餐建议并存。

- [x] **步骤 4** 草稿显示费用、合约、影响、依据和未解决诉求；服务任务保存来源、责任角色、OPEN/IN_PROGRESS/CLOSED/CANCELLED 与处理说明。关闭任务不冒充安装验收。

**验证命令与范围:** backend：python -m pytest tests/test_recommendation_rules.py -q；关闭模型后人工完成一次查询与方案选择。

**通过条件:** 硬条件不符不能成为可受理候选；修改需求产生新推荐 revision；服务任务可查看和记录处理结果，完整派工留到二期。

### T06 接入 AI 并保存提示词和运行记录

**依赖:** T04、T05

**Files:** backend/app/integrations/ai.py；backend/app/modules/recommendations/{schemas,models,service,router}.py；frontend/src/features/prompts/PromptPage.tsx；backend/tests/test_ai_boundary.py。

**Interfaces:** GET/POST /prompt-versions、POST /prompt-versions/{id}/publish；GET /ai-runs/{id}。统一异步调用返回校验后的需求或解释，request_key 识别一次辅助操作。

- [x] **步骤 1** 先用固定模型返回写 test_unknown_candidate_rejected、test_prompt_injection_cannot_write、test_ai_failure_keeps_manual_flow；普通测试默认不调用收费模型。

- [x] **步骤 2** 通过 LangChain 组织固定流程和结构化输出；先过 Pydantic，再核对候选、证据、金额和权限。业务 AI 不执行任意 SQL、受理或权限修改。

- [x] **步骤 3** 调用前保存 RUNNING，结束保存结果或失败；初始单次 30 秒、全流程 60 秒，格式修复最多一次并共用总时限。超期运行可标 INTERRUPTED，迟到结果不覆盖终态。

- [x] **步骤 4** 做提示词版本发布和运行查看页。获得既定配置与预算后进行最小真实模型探针，记录实际模型标识、耗时和格式兼容性；无授权时仅该联网步骤依赖阻塞。

**验证命令与范围:** backend：python -m pytest tests/test_ai_boundary.py -q；在授权范围内运行一次真实模型探针并保存脱敏证据。

**通过条件:** 固定流程可追溯；刷新后能查运行状态；真实探针未做则如实单列，不能把固定输出模式宣称为真实模型接入。

### T07 实现三类质检和人工复核

**依赖:** T03、T05、T06

**Files:** backend/app/modules/quality/{router,schemas,models,service,rules}.py；frontend/src/features/quality/QualityPage.tsx；backend/tests/test_quality.py。

**Interfaces:** GET/POST /quality-checks、GET /quality-checks/{id}；提交 target_type、target_id 或文本、policy_version_ids；POST /quality-checks/{id}/reviews；POST /recommendations/{id}/quality-checks。覆盖推荐、推广文案、客服答复。

- [x] **步骤 1** 用 test_price_mismatch_blocked、test_contract_omission_found、test_incomplete_extraction_needs_review 验证错价、合约遗漏和无法确定的自由文本。

- [x] **步骤 2** 先做确定性检查，再做独立 AI 辅助质检；报告含原文或字段、证据版本、问题和修订建议，不能由推荐那次回答自行宣布合格。

- [x] **步骤 3** 实现确认、驳回、修改与原因记录；修改后保留原输入和修订稿，并重新质检。硬规则阻断不能被人工勾选绕过。

- [x] **步骤 4** 用 test_revision_invalidates_confirmation 证明修改需求、方案或金额后旧检查与确认失效；独立文本也可从后台发起与追溯。

**验证命令与范围:** backend：python -m pytest tests/test_quality.py -q；各检查一条推广文案、推荐和答复，再核对 G1。

**通过条件:** PASS、BLOCKED、NEEDS_REVIEW 清楚区分；证据打开对应版本；缺信息不判通过；人工复核不是覆盖原结果。

### T08 完成分流取号和并发叫号

**依赖:** T02、T04、T06

**Files:** backend/app/modules/queue/{router,schemas,models,service}.py；frontend/src/features/queue/{CustomerQueuePage,QueueBoardPage,WindowPanel}.tsx；backend/tests/test_queue.py。

**Interfaces:** POST /public/queue-tickets；GET /public/queue-board；POST /windows/{id}/call-next；POST /queue-tickets/{id}/{start,finish,miss,cancel,requeue,adjust}。公共取号不返回客户资料，调整需管理权限与理由。

- [x] **步骤 1** 实现选择类别或 AI 建议分类、确认取号；默认三个窗口按支持类别和 queued_at、id 顺序叫号，AI 不决定先后。

- [x] **步骤 2** 实现 WAITING、CALLED、SERVING、DONE、MISSED、CANCELLED。过号重排保留原票并更新本轮排队时间；开始接待关联同一 service_id。

- [x] **步骤 3** 按门店短事务先锁门店再锁窗口；当前有有效票则返回原票。用唯一索引及条件更新避免同窗口多票或同票多窗口，锁内不调用网络。

- [x] **步骤 4** 用两个独立数据库连接测试 test_same_window_call_is_idempotent 与 test_two_windows_do_not_share_ticket；验证取消、过号、重排、调整理由和重复结束。

**验证命令与范围:** backend：python -m pytest tests/test_queue.py -q；在两个窗口同时操作叫号，检查公共响应仅含票号、类别、窗口、状态和更新时间。

**通过条件:** 排队与接待状态可追溯；本轮等待从最近排队时间计算，累计等待单独汇总；公共屏断线显示更新时间，不伪装实时。

### T09 让 BOSS Mock 真正支持重复安全办理

**依赖:** T03、T04

**Files:** mock_boss/app/{router,schemas,models,service,scenarios}.py；mock_boss/alembic/；mock_boss/tests/test_contract.py；backend/app/integrations/boss.py。

**Interfaces:** POST /mock/v1/acceptances 接收 external_request_id、账号、政策和内容摘要；GET /mock/v1/acceptances/by-request/{id} 返回原单或 NOT_FOUND。

- [x] **步骤 1** 写 test_same_key_same_payload_one_order 与 test_same_key_different_payload_conflict；以数据库唯一键和事务保护请求，不能只用内存字典。

- [x] **步骤 2** 实现成功、处理中、业务拒绝、提交成功后响应超时、查询暂时失败等受控情景；成功返回模拟外部业务单号。

- [x] **步骤 3** 写 test_timeout_after_commit_still_queryable，模拟已保存结果但调用方未收到响应；相同键与内容重试仍返回原单。

- [x] **步骤 4** 成功时一次性更新 Mock 中的当前套餐和业务台账，处理中或失败不更新；旧查询快照保持不变。情景控制仅测试或受限演示管理可用。

**验证命令与范围:** mock_boss：python -m pytest tests/test_contract.py -q；核对成功后查询返回新套餐且业务单数量仍为一。

**通过条件:** Mock 具有持久请求与结果；重启可查询；主应用没有读取 Mock 表的权限；NOT_FOUND 不被当作可任意换请求号的依据。

### T10 实现受理确认和未知结果恢复

**依赖:** T05、T07、T09

**Files:** backend/app/modules/acceptances/{router,schemas,models,service}.py；frontend/src/features/acceptances/AcceptancePanel.tsx；backend/tests/test_acceptance.py。

**Interfaces:** POST /acceptances 带 Idempotency-Key 创建草稿；POST /acceptances/{id}/confirm 带 expected_version 与质检标识；POST /acceptances/{id}/reconcile；GET /acceptances/{id}。

- [x] **步骤 1** 实现 DRAFT、READY、SUBMITTING、SUBMITTED、SUCCESS、FAILED、UNKNOWN、CANCELLED。只有提交前草稿可取消，取消本地草稿不代表外部撤单。

- [x] **步骤 2** 确认前重新查必要外部事实，再用短事务核对权限、版本、政策和质检，保存人工确认与稳定 external_request_id；事务提交后才调用 Mock。

- [x] **步骤 3** 明确成功或拒绝写对应结果；超时先 UNKNOWN，按原请求号核对；仅依赖 Mock 的幂等合同沿用原键原内容重试，迟到返回不能覆盖终态。

- [x] **步骤 4** 写 test_success_timeout_reconcile_one_order、test_stale_confirmation_rejected、test_late_failure_cannot_overwrite_success；再模拟保存 SUBMITTING 后进程退出并恢复查询。

**验证命令与范围:** backend：python -m pytest tests/test_acceptance.py -q；成功后重新查询账号，确认新资料、旧快照和外部单号同时可追溯。

**通过条件:** 重复确认不多建单；改价格必须重新确认；页面分别显示接待结束与外部办理状态；未查明结果不显示成功。

### T11 接入一次服务一次评价

**依赖:** T04、T08

**Files:** backend/app/modules/feedback/{router,schemas,models,service}.py；frontend/src/features/feedback/FeedbackPage.tsx；backend/tests/test_feedback.py。

**Interfaces:** POST /service-sessions/{id}/feedback-link；POST /public/feedback 接收专属令牌、score、tags、comment。服务结束后生成令牌，默认有效 24 小时。

- [x] **步骤 1** 写 test_feedback_is_once_per_service、test_expired_token_rejected、test_unrated_service_is_not_zero；同一次提交重试返回已有结果，不同内容重复提交报冲突。

- [x] **步骤 2** 令牌只保存摘要；评分限定 1—5 分；标签为等待时间、解释清晰度、问题解决、办理体验，意见可选。

- [x] **步骤 3** 专属评价页不要求输入客户号码、不返回完整账号资料；客户不评价时保留未评价。

- [x] **步骤 4** 把评价关联到 service_id，并在服务详情展示有权限查看的结果；客户评分和系统质检结果分栏。

**验证命令与范围:** backend：python -m pytest tests/test_feedback.py -q；完成一次取号、接待、模拟办理和评价，核对 G2。

**通过条件:** 一次服务仅一份有效评价；无评价不补零；过期、重复和越权有明确结果；G2 同时核对 T10 恢复证据。

### T12 完成统计和改进任务

**依赖:** T07、T08、T11

**Files:** backend/app/modules/improvements/{router,schemas,models,service}.py；frontend/src/features/improvements/ImprovementPage.tsx；backend/tests/test_improvements.py。

**Interfaces:** GET /service-metrics；POST /improvement-proposals；GET/POST /improvement-tasks；POST /improvement-tasks/{id}/transition。指标包含时间范围、门店、类别、样本量和证据记录。

- [x] **步骤 1** 用确定性查询计算等待、服务时长、满意度、参与率和质检问题率，保留统计快照；评价参与率分母为已完成且符合评价条件的服务数。

- [x] **步骤 2** test_empty_feedback_has_no_average 验证无评价时均分为 null；test_metrics_show_denominators 验证每个比例可回查分子分母，取消和过号单列。

- [x] **步骤 3** AI 根据快照提出现象、可能原因、建议和验证办法；不得编造数量或直接归责员工。店长审核后设置负责人、计划和目标。

- [x] **步骤 4** 实现 PROPOSED、APPROVED、IN_PROGRESS、VERIFIED、CLOSED、REJECTED；test_close_requires_verification 阻止没有验证记录就关闭。记录前后样本及同期条件变化。

**验证命令与范围:** backend：python -m pytest tests/test_improvements.py -q；在页面完成建议、审核、处理、验证和关闭。

**通过条件:** 统计能定位原记录；AI 只有建议权限；缺数据提示核查；结果未改善也如实保留。

### T13 完成评测和一次真实问题改进

**依赖:** T06、T07、T12

**Files:** backend/app/modules/evaluations/{models,schemas,router,cli,metrics}.py；backend/tests/test_evaluation_metrics.py；backend/evaluation/cases.jsonl；frontend/src/features/evaluations/EvaluationPage.tsx；docs/实施记录/phase1-evaluation.md。

**Interfaces:** GET /evaluation-runs、GET /evaluation-runs/{id}；CLI 执行批次并逐条保存状态、输出、耗时和错误。Web 只查看；重启不宣称自动续跑。

- [x] **步骤 1** 建立 30 条用例，20 条开发集、10 条保留集；覆盖正确、错价过期、条件遗漏、合约冲突、资料不足和复合需求。写清快照、版本、预期和核对人或核对状态。

- [x] **步骤 2** test_metrics_handle_zero_denominator 验证零分母为空；默认报告问题级 TP、FP、FN、精确率、召回率及误报条数，缺少可数 TN 时不报假误报率。

- [ ] **步骤 3** 在已确认用例与真实模型预算内冻结 V1，保存开发集及保留集结果；调试时不读取保留集结果。针对开发集实际问题修改提示词形成 V2，固定规则、输入和运行设置，冻结后再比较两版保留集结果。

- [ ] **步骤 4** 保存模型与数据版本、原始计数、耗时和失败案例，检查新增误报。未发现真实问题则补足合理覆盖，不故意造错。若先修程序规则，重新建立比较基线，不能把规则改变冒充提示词效果。

**验证命令与范围:** backend：python -m pytest tests/test_evaluation_metrics.py -q；python -m app.modules.evaluations.cli --cases evaluation/cases.jsonl --split dev --prompt-version V1；其他批次只改明确的 split 与版本参数。

**通过条件:** G3 需真实运行、已核对标签和至少一项实际问题的修复证据。保留集不得逐题调参；看过后继续调试须补新的保留样本。凭证、预算或人工核对未就绪则该项依赖阻塞。

### T14 把所有页面连成可操作的应用

**依赖:** T02、T04、T05、T07、T08、T10、T11、T12

**Files:** frontend/src/app/routes.tsx、frontend/src/lib/api.ts；各 features 页面；frontend/tests/e2e/{service-flow,ai-fallback,unknown-result}.spec.ts；frontend/playwright.config.ts。

**Interfaces:** 页面入口包括客户取号、公共叫号屏、店员工作台、资料管理、质检与服务记录、复盘改进、提示词与评测、客户评价；评测数据读取依赖 T13 的接口实现。

- [x] **步骤 1** 工作台放入账号事实、需求、最多三张方案卡、依据、质检、确认、受理状态和服务时间线；服务详情能打开旧版本。

- [x] **步骤 2** 用 Query 管服务端数据；变更后只刷新相关查询；退出或切店清理缓存。写请求不自动盲目重试，按钮显示禁用原因和结果未知状态。

- [x] **步骤 3** 统一表单标签、键盘操作和错误提示，状态不只靠颜色；空数据、超时、无权限、模型失败均有可操作提示，不能用静态成功提示冒充联调。

- [x] **步骤 4** 检查真实资源的未登录、跨店、无管理权限和公共响应体；已实现评测页则接入 T13 数据，联网评测受阻也可显示真实的待运行状态。

**验证命令与范围:** frontend：npm run typecheck；npm run e2e -- service-flow.spec.ts；此处先建立三个场景，T16 统一执行最终版本。

**通过条件:** 每个必需页面使用真实后端数据或清楚标识的演示数据；没有空菜单、假成功按钮或前端复制的资费规则。

### T15 整理部署迁移和演示恢复

**依赖:** T01、T03、T04、T09、T14

**Files:** compose.yaml、frontend/Dockerfile、backend/Dockerfile、mock_boss/Dockerfile；backend/app/seed.py；backend/alembic/、mock_boss/alembic/；README.md；docs/实施记录/phase1.md。

**Interfaces:** 根目录 docker compose up --build 启动 db、migrate、api、mock、web；迁移成功后再启动业务。演示默认使用离线模型模式，联网需显式配置；两种模式在页面可辨认。

- [ ] **步骤 1** 固定镜像与依赖版本，数据库健康检查后执行各自迁移；健康检查不调用模型，主应用与 Mock 使用受限角色和分离的 schema。

- [x] **步骤 2** 在专用空库验证初始化，再用上一迁移版本数据验证升级，不能以删库重建代替迁移；核对 T03 的种子总量和预置标识。

- [x] **步骤 3** 初始化复跑不改变已有业务；重置需显式 --reset-demo 与专用演示库确认，仅允许已验证的本项目专用演示库，拒绝其他库名和未知环境。测试清理由测试夹具另行管理。

- [x] **步骤 4** 用标准 pg_dump 备份到项目私有演示目录，再恢复到单独临时恢复库；核对服务、旧快照和请求号。恢复后未知受理仍按原号查询，不用旧本地快照认定外部成功。

**验证命令与范围:** 根目录：docker compose config、docker compose up --build；backend：python -m alembic upgrade head；Mock 在其目录执行迁移；记录实际备份恢复命令并脱敏。

**通过条件:** 新环境启动和升级均有证据；演示数据可明确重置；恢复库能查历史记录；没有破坏已有用户数据库或把密钥打入镜像。

### T16 按业务场景做最终验收

**依赖:** T10、T11、T12、T14、T15

**Files:** frontend/tests/e2e/{service-flow,ai-fallback,unknown-result}.spec.ts；backend/tests 中已有相关检查；docs/实施记录/phase1.md 的 A01—A08 栏。

**Interfaces:** 使用第 15 章的验收矩阵。正常自动检查使用固定模型返回，真实模型质量证据来自 T13，二者分别报告。

- [x] **步骤 1** 执行完整服务流程、AI 故障人工处理、外部成功但响应超时三条浏览器情景；检查数据库中关联记录与单据数量。

- [x] **步骤 2** 核对 A01—A08 的实际输入、预期、结果和证据位置；旧证据仅在对应实现未变化时复用，受公共层改动影响的检查重跑。

- [x] **步骤 3** 发现失败时回到负责该行为的任务修复，再跑最小相关检查和受影响流程；不删测试、不降低断言、不把 skip 当通过。

- [x] **步骤 4** 检查数据升级和恢复证据、已知限制以及完整演示步骤；真实模型或用例核对受阻时只能给出分项结果。

**验证命令与范围:** frontend：npm run e2e -- service-flow.spec.ts ai-fallback.spec.ts unknown-result.spec.ts；npm run build；另执行被改动影响的后端或 Mock 检查。

**通过条件:** A01—A08 有通过证据，G0—G3 已核实；T13 的真实评测未完成时本任务不能整体通过，但继续完成独立的浏览器与环境验收。G4 在 T17 交付后最终核对。

### T17 形成交付包并停止在阶段一

**依赖:** T16

**Files:** README.md；docs/实施记录/phase1.md；docs/实施记录/phase1-evaluation.md；docs/阶段一操作指南.md；docs/阶段一演示脚本.md；必要时同步本细则与原技术文档的受影响约定。

**Interfaces:** 交付可运行工程、版本锁、迁移、模拟种子、测试和实际证据、30 条用例、V1/V2 报告、一页操作指南、约十分钟演示步骤、已知限制。

- [ ] **步骤 1** 用操作指南在干净演示环境走一次启动和访问；账号由安全配置提供，指南不公布真实口令。

- [x] **步骤 2** 检查测试报告能回到实际输入、数据版本、模型版本和运行结果；预置样本与真实运行结果分开。

- [x] **步骤 3** 更新任务状态和验收结论，列出最终实现范围、实际验证、限制及二三期接续位置；只报告已有证据。

- [x] **步骤 4** 完成阶段一后停止，不继续采购、库存、支付、完整派工和结算；本地提交、推送或发布按已有授权分别处理。

**验证命令与范围:** 核对最终交付清单与 G4；使用已验证且未再变化的证据，不另跑无关全库扫描。

**通过条件:** 用户可以按文档启动、演示和查看证据；阶段一所有必需结果成立。若依赖尚未完成，不执行最终完成标记，而是交付可用部分及精确阻塞清单。

## 15 A01 至 A08 验收矩阵

每条验收记录写实际输入、预期、结果、运行环境与证据路径。表中是必须验证的行为，不是已经取得的结果。

| 编号 | 必须通过的行为 | 负责任务与证据 |
| --- | --- | --- |
| A01 | 号码、套餐、费用、合约与 Mock 一致；未找到、失败、缺字段不同处理；旧快照可查。 | T04；test_account_queries 与查询页面记录。 |
| A02 | 89 元候选费用可解释；丢宽带、在约限制和未知资格按规则处理；支持保留套餐、无方案和服务任务。 | T05—T06；规则检查、人工模式和真实模型探针。 |
| A03 | 错价、过期、合约遗漏能定位依据；三类文本可复核；修改后旧确认失效。 | T07、T10；test_quality、陈旧确认检查与修订历史。 |
| A04 | 等待、叫号、服务、取消、过号与重排可追溯；双连接并发不重票；重复受理不多建单。 | T08—T10；并发检查、Mock 唯一单据和服务时间线。 |
| A05 | 外部成功但响应超时先未知，按原号核对后成功；重启可查；AI 失败仍能人工服务。 | T06、T09—T10；unknown-result 和 ai-fallback 浏览器场景。 |
| A06 | 一次服务一次评价；未评不补分，零分母为空；建议有证据，经审核与验证后关闭。 | T11—T12；统计断言、反馈记录和改进任务历史。 |
| A07 | 未登录、跨店、无管理权限均被后端拦截；公共屏与评价页不泄漏账号和密钥。 | T02、T14；实际接口响应体与授权检查。 |
| A08 | 30 条核对用例、固定版本设置、开发与保留集；一次实际问题修复；真实 V1/V2 结果和失败案例。 | T13；原始评测运行、核对记录和 phase1-evaluation.md。 |

### 三个浏览器场景的结束点

service-flow：取号 → 叫号 → 查询 → 推荐 → 质检 → 人工确认 → 模拟办理成功 → 结束接待 → 评价 → 后台关联记录。ai-fallback：关闭模型后完成查询、手选方案和后续服务。unknown-result：Mock 成功后超时，页面先显示未知，核对后显示成功，外部单据仍为一。

A08 的真实评测不能由这三条浏览器测试代替。预置历史记录可以验证统计与页面，但不能成为“模型效果提升”或“实际经营改善”的证据。

## 16 交付与给 Agent 的启动指令

### 交付时逐项核对

- 运行：前端、后端、PostgreSQL、Mock、锁定依赖、环境示例、数据库迁移和健康检查。

- 数据：模拟账号和目录、初始化与重置方法、历史版本、业务请求号、备份和恢复证据。

- 质量：相关测试、A01—A08 记录、30 条核对用例、真实模型运行、V1/V2 对比和实际问题台账。

- 使用：README、一页操作指南、约十分钟演示脚本、已知限制，以及下一位 Agent 可以接续的施工记录。

### 完成结论只能选符合事实的一种

阶段一完成：T00—T17 和 G0—G4 均满足，必要证据可查。部分完成：列出已可用的业务，以及仍未完成的任务。外部依赖阻塞：列出具体缺少条件、受影响任务和已完成的独立工作；不要笼统写“等用户”。

没有真实模型额度或凭证时，可交付清楚标识的离线版本；没有人工核对的标签时，可交付待核对用例草稿。这两种情况均不能标记阶段一完整验收通过。

### 可直接交给施工 Agent 的指令

```text
请在当前仓库实施第一阶段。先读取 AGENTS.md 和
《04_阶段一Agent完整执行细则.md》，核对实际文件。
按 T00—T17 顺序执行，默认由单个 Agent 完成；
任务通过后继续下一项，直至 G0—G4 与 A01—A08 满足。
仅在真实外部依赖、关键业务歧义或超出授权时请求决定；
其余可逆开发与必要验证自行推进。用 phase1.md 记录
进度、实际检查、阻塞和下一步，方便中断后续接。
保持二三期所需标识、版本与迁移，不提前开发二三期。
外部条件不足时完成独立工作，如实报告，不虚报通过。
```

### 与原有文档的关系

本细则沿用 01 详细施工方案与 02 通用规则，增加任务编号、默认演示样本和验收归属。技术方案仍保持模块化单体、固定 AI 流程及独立 HTTP Mock。Markdown 和 Word 从同一份内容生成；执行时更新 Markdown 与进度记录，若修改合同或范围，再同步对应 Word 和原技术文档。

- [AGENTS.md](../../AGENTS.md)
- [第一阶段独立项目规划书](../项目规划/01_第一阶段独立规划书_营业厅AI服务与质检工作台.docx)
- [01 技术施工报告详细版](01_技术施工报告_第一阶段与后续扩展.docx)
- [02 Agent 施工规则与交付规范](02_Agent施工规则与交付规范.docx)
- [03 软件架构设计与技术选型说明](03_软件架构设计与技术选型说明.docx)
