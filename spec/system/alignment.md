# 规格核对与证据

## 核对层级

此表将当前 dev/user 与实现入口、导出模块和测试对照。它表明仓库内有相应行为与证据，不代表每个底层分支都已写进自然语言规格，也不代表当前生产系统已经实测。真实样本、权限和写入结果须另行授权复验。

APP 实现均位于 `public/tool/app/<entry>/`；下表模块名位于各 APP 的业务包，协议名位于 `_shared/`。API 从同一 catalog 和 core 生成，不复制另一套参数事实。

| APP/能力 | 核对的输入、行为和结果 | 主要代码与测试证据 |
| --- | --- | --- |
| 飞行经历时间查询 | 两列身份、完整时间页、动态列、汇总唯一性、失败继续与逐人检查点 | `http_flight_history/`、`ieb_protocol/flight_history_contract.py`、`tests/python/test_flight_history.py` |
| 锁班皇帝（新） | 动态类型、五列及可选时间、单次提交、冲突归属、可选通过后回查、即时 Excel | `http_lock_entry/`、`ieb_protocol/lock_*.py`、`tests/python/http_lock_entry_tests/` |
| 飞行经历查询（皇帝版） | 日期输入、范围筛选、单次逐人查询、结束时原版/去分钟版 | `http_flight_stats/`、`ieb_protocol/flight_stats*.py`、`tests/python/http_flight_stats_tests/` |
| 航班明细查询（皇帝版） | 四列年月、时间轴及逐月明细、追加检查点、收口 Excel、分页结果 | `http_flight_detail/`、`ieb_protocol/flight_detail*.py`、`tests/python/http_flight_detail_tests/` |
| 飞行人员信息查询（皇帝版） | 员工唯一归属、历史资格、培训分页、五类结果、Excel/JSON/报告 | `http_qualification_query/`、`ieb_protocol/personnel*.py`、`tests/python/http_qualification_query_tests/` |
| 训练安排查询（HTTP版） | 动态类别、单类别/区域默认、周期去重、占位行剔除、通过率与完整导出 | `http_training_arrangement/`、`ieb_protocol/training_arrangement*.py`、`tests/python/http_training_arrangement_tests/` |
| 运行资质人员名册 | 动态筛选、逐资格导出、人数核对、人员动态列与跨资格保留 | `http_qualification_roster/`、`ieb_protocol/roster*.py`、`qualification_roster.py`、`tests/python/http_qualification_roster_tests/` |
| OA 已阅助手（HTTP版） | 完整 cURL、全量分页、公文筛选、任意正整数/全部、逐条一次提交 | `http_oa_read/`、`oa_protocol/`、`tests/python/http_oa_read_tests/` |
| 资质监控（皇帝版） | 动态分类、原生 OOXML、JCY 特判、失败继续、全成功 ZIP | `http_qualification_monitor/`、`ieb_protocol/qualification_monitor*.py`、`tests/python/http_qualification_monitor_tests/` |
| CAAC 飞行员信息导出 | 全量/名单、姓名与档案号唯一归属、动态字段、单 Sheet 检查点 | `caac_pilot_export/`、`caac_protocol/`、`tests/python/http_caac_pilot_export_tests/` |
| SOC 随机置位批量助手 | Excel 行筛选、动态航班完整值、独立会话、逐条业务 message | `soc_positioning/`、`soc_protocol/`、`tests/python/soc_positioning_tests/` |
| API 文档 | catalog 规范化、同源 Markdown、执行器、会话与结构化响应 | `api-docs/`、`tests/tool/api-docs/`、`tests/python/api_docs_tests/` |
| 万能查询 | 动态发现、默认参数、安全结果、普通/渐进执行 | `api-docs/universal_query/`、`tests/python/api_docs_tests/test_server.py` |
| 局域网与独立分发 | 提示型接管、隔离会话、资源、全部子服务关闭与独立 ZIP | `csn2api_runtime/`、`tests/python/test_start_all.py`、`tests/python/test_http_workbench_assets.py`、`tests/smoke/lan-runtime-contract.test.ts` |

## 自动交付合同

工具清单、protocol 声明、catalog 和构建产物的关联由 `tests/tool/protocol-core-contract.test.ts`、`http-workbench-core-runtime.test.ts` 及 `tests/smoke/tool-delivery-contract.test.ts` 保护。Python 系统测试保护 catalog 与请求路径、方法、字段和核心结果。合并文档测试动态覆盖全部 APP dev/user 和当前 API 端点，验证目录、链接、中文和排除本地凭据。

文档覆盖与自动测试只能发现契约层面的不一致，不能自动判断全部自然语言语义、页面视觉、生产权限或现场业务结果。规格未穷尽的解析边界仍须参考合成测试；API 或 APP 任一入口的成功不能代替另一入口验收。
