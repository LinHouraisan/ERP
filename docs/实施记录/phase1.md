# 阶段一施工与验收记录

依据：docs/技术施工/04_阶段一Agent完整执行细则.md。更新：2026-10-03，Asia/Shanghai。

**结论：演示业务已填充，真实 DeepSeek 接入验证通过；正式效果评测待人工标签核对。** 用户从最初离线授权追加为允许使用已填密钥、补齐全部演示数据。30 条真实 AI 运行成功（含 20 条开发集试跑），详细记录见 [演示数据与用量](phase1-demo-data.md)。未以试跑替代正式 V1/V2 验收。

## 基线与环境

- 开工基线 9a7ec44，原 main 分支，原有未跟踪 AGENTS.md 与规划 docs/ 保留；施工分支 codex/phase1。没有提交、推送或公网发布。
- 从仅有规划文档的仓库建立工程，单 Agent 顺序实施；没有二三期空表、采购、库存、支付、完整派工或结算。
- 实际运行：Windows、Python 3.12.14 隔离环境、Node 24.21.0 / npm 11.19.0、PostgreSQL 18.6。系统 Python 3.14.7 未用于应用。
- PostgreSQL 在项目 .local/pgsql 与 .local/pgdata，仅监听 127.0.0.1:55432。库 erp_demo / erp_phase1_test，角色 erp_app / erp_mock 分别拥有 app / boss；主应用角色不能读 Mock 表。随机口令只存私有 .env / .local/pg-password。
- 原环境无 Docker / WSL。Compose v2.39.4 配置解析通过，但连接 Docker 引擎失败；本次使用已验证的本机路径。

## 任务状态

| 任务 | 状态 | 已交付 / 剩余条件 |
| --- | --- | --- |
| T00 现状 | 通过 | 基线、依赖和用户离线决定 |
| T01 工程 | 通过 | 两个 HTTP 进程、前端代理、锁文件、迁移、健康及测试入口 |
| T02 身份权限 | 通过 | 会话摘要、Argon2、CSRF/来源、门店与动作权限、登出 |
| T03 目录种子 | 通过 | 8 产品、版本草稿/发布、不可变政策、固定样本及管理页 |
| T04 查询服务 | 通过 | HTTP 查询、来源时间、未知值、不可变快照和服务历史 |
| T05 规则人工 | 通过 | Decimal、最多三候选、保留/无方案/补资料、可追溯服务任务 |
| T06 AI | 通过 | 用户已授权，真实探针及需求/解释/质检/改进四类调用成功，模型与用量入库 |
| T07 质检复核 | 通过 | 三类质检、硬阻断、修订历史和旧确认失效，离线验证 |
| T08 排队接待 | 通过 | 状态、理由、独立连接并发、公开字段、最后更新时间 |
| T09 HTTP Mock | 通过 | 持久幂等/冲突、受控情景、成功更新资料和原号查询 |
| T10 受理恢复 | 通过 | 重新核对、短事务、UNKNOWN、原号恢复及迟到终态保护 |
| T11 评价 | 通过 | 一次服务一次评价、24 小时摘要令牌、未评价为空 |
| T12 统计改进 | 通过 | 分母、样本、证据、审核/处理/验证/关闭，离线建议 |
| T13 真实评测 | 依赖阻塞 | 30 条草稿；20 条开发集联网试跑成功且不计效果分；人工标签和正式 V1/V2 待完成 |
| T14 页面 | 通过 | 必需页面连接真实本地 API，错误可操作，类型与构建通过 |
| T15 部署恢复 | 依赖阻塞 | 本机启动、空库升级、备份恢复通过；缺 Docker 引擎，容器未运行；重置仅验证保护 |
| T16 最终验收 | 依赖阻塞 | 三条核心及后台情景、A02 真实探针通过；A08 正式质量比较未完成 |
| T17 交付 | 依赖阻塞 | 工程及指南报告已交付；未在另一台干净机器按成文指南复装，保留完整验收标记 |

## 关口

| 关口 | 结论 | 证据 / 缺项 |
| --- | --- | --- |
| G0 | 通过 | 本机登录、带来源和时间的 HTTP 查询、迁移健康 |
| G1 | 通过 | 需求、规则、真实解释、独立质检和模拟人工复核联通 |
| G2 | 通过 | 取号到评价，真实并发，UNKNOWN 原号恢复 |
| G3 | 依赖阻塞 | 改进闭环通过；标签与真实 V1/V2 无数据 |
| G4 | 分项通过 | 页面、本机启动、升级与恢复通过；容器/另一台机器未验证，G3 未通过 |

## A01—A08

环境为 Windows + PostgreSQL + 独立 HTTP Mock，普通模型固定输出。浏览器为 Edge / Playwright；测试只用 erp_phase1_test；恢复验证使用本项目 erp_demo 的模拟记录。

| 编号 | 实际输入和预期 | 结果与证据 |
| --- | --- | --- |
| A01 | 129 元账号、缺月费、未找到和超时；来源明确，null 保留，新查询不盖旧快照 | 通过；test_account_queries.py 2 项、service-flow，实际 129→89 双快照 |
| A02 | 129→89 保宽带；79 丢宽带；未知一次费；合约首尾；无方案/保留/故障 | 通过；规则 4 项、AI 边界检查、真实需求提取及89元说明成功并有模拟业务记录 |
| A03 | 错价、过期、合约遗漏；营销/答复修订；更新推荐重用旧确认 | 通过；test_quality.py 6 项、陈旧确认受理检查、admin-pages 两版历史 |
| A04 | 同窗口及双窗口独立连接并发；取消、过号重排、调整理由、重复结束；重复受理 | 通过；test_queue.py 3 项、Mock test_contract.py 2 项、受理恢复 |
| A05 | 外部成功后超时；保存 SUBMITTING 后新会话恢复；模型无密钥 | 通过；test_acceptance.py 4 项、unknown-result / ai-fallback；原请求号及外部单号相同，数据库唯一单据 |
| A06 | 重复/过期/未评价、零分母、无验证关闭 | 通过；test_feedback.py 2 项、test_improvements.py 2 项、后台审核至关闭；不认定经营改善 |
| A07 | 未登录、跨店服务、店员发布政策和审核改进、公共响应 | 通过；test_authz.py 3 项含实际动作 403、跨店 404；队列/评价公开字段检查 |
| A08 | 30 条核对用例、固定设置、真实 V1/V2 和实际模型问题修复 | 依赖阻塞；已有 20 条真实开发集试跑，但全部标签 PENDING，未正式计分或比较 V1/V2 |

## 实际检查

按模块先观察目标失败再实现；初始健康入口、权限、规则、AI、质检、队列、Mock 及评测计数均经历失败后修复。下表为最新相关检查，不将多次局部运行说成一次全量测试。pytest 命令在所列目录用项目 .venv 的 Python 执行，均带 -q --tb=short。

| 命令 / 范围 | 目录 | 退出码与结果 |
| --- | --- | --- |
| python -m pytest tests/test_bootstrap.py | backend | 0，6 passed；健康、迁移、库限制、404/500 脱敏 |
| python -m pytest tests/test_quality.py tests/test_authz.py | backend | 0，9 passed；三类质检、修订历史和具体后台权限 |
| python -m pytest tests/test_recommendation_rules.py | backend | 0，4 passed；费用/未知/合约及服务任务处理、关闭、取消 |
| python -m pytest tests/test_ai_boundary.py | backend | 0，7 passed；无网络适配合同、注入边界、失败人工、修复用量累计 |
| python -m pytest tests/test_database_guard.py tests/test_catalog_versions.py tests/test_queue.py tests/test_acceptance.py tests/test_authz.py tests/test_improvements.py | backend | 0，16 passed；版本、并发、恢复、越权、改进及保护 |
| python -m pytest tests/test_account_queries.py；test_feedback.py；test_evaluation_metrics.py（各自运行） | backend | 各 0，各 2 passed；对应实现未再变更，复用证据 |
| python -m pytest tests/test_contract.py | mock_boss | 0，2 passed；原单/冲突、超时、宽带套餐同步 |
| python -m alembic check | backend | 0，No new upgrade operations detected |
| python scripts/prepare_tests.py | 根目录 | 0，专用库迁移及幂等种子 |
| npm run e2e -- service-flow.spec.ts ai-fallback.spec.ts unknown-result.spec.ts admin-pages.spec.ts | frontend | 当次 1：核心三情景通过，扩展后台情景因表单标签失败；未隐藏失败 |
| npm run e2e -- admin-pages.spec.ts（最后一次） | frontend | 0，1 passed / 10.5 秒；修复可访问名称及修订后历史刷新 |
| npm run build（最后一次） | frontend | 0；包含类型检查；主包 1140.65 kB / gzip 359.11 kB，体积提示保留 |
| python scripts/check_migrations.py | 根目录 | 0；空库及 010→011 / 001→002，数据不变、角色隔离 |
| python scripts/database.py backup；restore-check --backup 实际目录 | 根目录 | 均 0；一致快照导出、独立恢复和摘要检查 |
| .local/docker-compose.exe --project-directory . config --quiet | 根目录 | 0；配置解析通过 |
| .local/docker-compose.exe --project-directory . up --build -d | 根目录 | 1；缺 Docker 引擎管道，未进入构建/启动 |
| python scripts/start_local.py --background | 根目录 | 0；迁移、种子及 8000/8001/5173 进程启动，已重启至最终代码 |
| 最终进程重启后 HTTP 与数据库检查 | 根目录 | 0；两个 ready 和网页 200，admin 登录成功；原号、外部单号、129/89 两快照仍在，Mock 单据仍为 1 |
| 私有凭证比对源码、交付文件及前端产物 | 根目录 | 0；192 个文件未出现实际本地密钥或口令 |

截图：.local/e2e-service-flow.png、.local/e2e-unknown-result.png、.local/e2e-admin-pages.png，均忽略且仅在本机。浏览器错误上下文曾包含本地演示口令，已删除相关私有报告并轮换口令；登录测试失败后会清空输入控件，仓库不保存旧值或新值。

## 迁移与恢复的具体证据

迁移已查看并应用：backend 001—011、Mock 001—002；无运行时 create_all。早期 Alembic 默认 schema 导致误判重复表，失败回滚后修正 search_path，未删库重建。

空库升级检查保留 erp_upgrade_20261002181931_test，从 backend 010 / Mock 001 真实数据升级到最新；旧服务整行相同、月费 129.00 不变；主角色读 boss.accounts 被数据库拒绝。

模拟账号 11 实际走过外部保存成功但调用方超时：

| 对象 | 标识 |
| --- | --- |
| 服务 | aeb7610f-a1c6-4e9c-a4ce-916415f1bceb |
| 旧快照（月费129.00） | 0e1034cd-ad3d-4440-b19a-6186d661f3de |
| 受理 | 16483945-1907-44cc-8c34-dbeb0bc53a82 |
| 原请求号 | d98c06f4-b598-4c66-abdf-c8fbd402f177 |
| 外部单号 | bb876941-3cb7-45d3-b90d-0a72aab8f067 |

备份 .local/backups/20261002T182101298195Z 包含 app.dump、boss.dump、manifest.json；备份时 21 服务、1 旧快照、1 UNKNOWN、12 预置评价。恢复到 erp_restore_20261002182253_test，四类记录数量和 SHA-256 完全相同，UNKNOWN 保留 1 条；证据为同目录 restore-check.json。

恢复库通过新主应用会话和真实 HTTP Mock 按**原请求号**核对 SUCCESS，返回上述外部单号，证据 restore-reconcile.json。随后源库也按原号核对，再查询为 89.00，旧 129.00 快照保留并结束接待。没有换号重办，也没有以备份里的本地状态认定外部成功。

种子总量：12 模拟客户、8 套餐/服务、6 类条件、3 类业务、3 窗口、20 条 preset=true 历史（12 预置评价、8 未评）、30 待核对用例。固定样本日期 2026-10-02；新模拟运行与预置历史分开。重复种子不重置已办理事实。

重置入口要求 APP_ENV=demo、成对 erp_demo、规定角色及本项目标识，拒绝 UNKNOWN/SUBMITTING/SUBMITTED，先备份再清空业务表。误库/误确认保护已测试；本次保留现有证据，**未实际执行重置清空**。

## 实现约定与限制

- AI 编排在 recommendations/ai_service.py 和 ai_router.py；查询路由归 services/router.py，DTO 与 ORM 分离。模块化单体、固定 AI 流程、独立 HTTP Mock 与原合同保持一致。
- Argon2 负责口令哈希，pytest / Playwright 满足计划中的验证；指定框架与适配依赖均锁版本。没有 Redis、Celery、向量库、事件总线或多 Agent。
- 自由文本规则只识别显式月费、合约及有效期等有限信息，歧义必须人工复核；没有发现问题不等于完整语义合格。
- 服务记录已分页，部分后台列表只显示最近 100 条；主包体积有构建提示，未进行无关优化。评测批次不自动续跑，未返回 token 用量时保持未知。
- Docker 构建运行、另一台干净机器复装、实际重置未验证；本机原生启动、独立空库升级和备份恢复已有证据。

## 接续

1. 业务核对 30 条草稿；按评测记录冻结正式基线、运行真实开发/保留集、根据真实问题形成 V2 并比较，补 T13/G3/A08。当前所有标签仍 PENDING，联网试跑不计效果分。
2. 有 Docker 引擎后按 README 检查容器；在可清空的隔离演示环境验证完整重置及成文指南，补 T15—T17/G4。在此之前不标“阶段一完成”。

2026-10-03 追加验证：AI 与评测局部测试 11 passed；真实 AI 30 条全成功，总用量 37316 token；开发集试跑 20 成功 / 0 失败；只读浏览器验证服务、未知受理、试跑用途及公共屏通过；前端类型与构建通过。演示数据合计 30 服务、6 票、4 受理、7 服务任务、16 评价、2 改进任务。完整证据在 phase1-demo-data.md，本节之前的命令表保留为首轮离线工程历史。

交付：[README](../../README.md)、[操作指南](../阶段一操作指南.md)、[演示脚本](../阶段一演示脚本.md)、[评测记录](phase1-evaluation.md)。不继续二三期。

