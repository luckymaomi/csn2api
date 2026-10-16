# 飞行经历时间查询

独立只读 Python APP，输入 Excel 或粘贴员工号与姓名两列，不需要日期。Excel 按表头读取，支持员工号/工号/员工编号和姓名/员工姓名；员工号归一为六位文本，姓名必填。粘贴支持制表符、空格或逗号分列和可选表头。空行忽略，无效行提示跳过；重复员工号只处理首条有效记录。

共享 FlightDetailProtocol 负责页面验证、人员时间轴请求和会话检查，flight_history_contract 校验同一响应的人员归属、独立表头、唯一汇总行和所有数据行列宽。接口声明位于 API catalog 的 flight-detail.query-history；API 和 APP 共用同一 core。

每人只请求一次时间轴页面，完整保留汇总、历史合计、年度和月份所有行、原始顺序、动态表头和空值，不额外请求逐航班明细。历史年份和月份来自当前响应，不补齐未返回的年月，也不把父子汇总重复相加。

查询按输入顺序执行，普通请求、业务或解析异常记录失败并继续；登录失效停止后续请求；人工终止在请求边界生效。不重试、不并发。主结果表为员工号、姓名、门户原表头和所有数据行，时间与员工号均为文本。页面和 Excel 消费同一行列契约，Excel 主表仅含成功人员全页数据；独立“处理记录”sheet 保存所有输入状态和异常。每名员工完成后原子保存检查点并开放下载，停止或失效后保留已有结果。

工作台提供凭据验证、Excel/粘贴输入、数据检查、开始、终止、人员与数据行结果、进度和单个 Excel 下载。公共主题、保活和可打断滚动跟随沿用仓库标准。Cookie 只存本应用后端内存，验证响应向当前页面回传一次规范化 Cookie；普通状态、日志和文件不含凭据。服务只监听 127.0.0.1。

职责：input_data 归一两列输入；portal_client 映射共享协议及保活；runner 维护批量顺序和异常边界；exporter 保存原子 Excel 检查点；manager 持有线程、会话和批次状态；server 提供 loopback API 及静态资源；web 处理人工交互。manager 超过 300 行，仍承担内聚的批次生命周期职责，不包含协议解析、Excel 或 UI 实现。

API：POST /api/session/verify、/api/check-data、/api/run、/api/start、/api/stop，GET /api/status、/api/download/original。输入为 inputMode、pastedText 或 excelBase64/excelName。构建从工具登记动态生成详情、模板入口、独立 ZIP、runtime-tools 和完整协议依赖。

统一真实验收 flight-history Case 分别覆盖 API、APP 粘贴和 Excel、全页数据与导出一致，以及临时端口释放。