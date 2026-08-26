import type { ToolItem } from "./models";

export const tools: ToolItem[] = [
    { name: "锁班皇帝（新）", desc: "好活，直接调用接口锁班，极速。", entry: "http-lock-entry-helper", status: "done", homepageState: "beta" },
    { name: "飞行经历查询（皇帝版）", desc: "好活，直接调用接口查完整飞行经历和起落数，极速。", entry: "http-flight-stats-helper", status: "done", homepageState: "beta" },
    { name: "飞行人员信息查询（皇帝版）", desc: "好活，哈哈。直接调用 IEB 接口查询基础信息、技术等级、运行资格和训练检查记录。", entry: "http-qualification-query-helper", status: "done", homepageState: "beta" },
    { name: "运行资质人员名册", desc: "按门户动态运行资格逐项查询人员，并合并为四列名册。", entry: "http-qualification-roster-helper", status: "done", homepageState: "beta" },
    { name: "OA 已阅助手（HTTP版）", desc: "扫描全部 OA 待办，按指定数量或无限模式逐条处理可点击的公文已阅。", entry: "http-oa-read-helper", status: "done", homepageState: "beta" },
    { name: "资质监控（皇帝版）", desc: "直接调用 IEB 原生导出，按三类资质严格串行获取全部独立 Excel。", entry: "http-qualification-monitor-helper", status: "done", homepageState: "beta" },
    { name: "CAAC 飞行员信息导出", desc: "支持全量或按 Excel 名单抓取飞行员详情，并保存为单 Sheet Excel。", entry: "http-caac-pilot-export-helper", status: "done", homepageState: "beta" },
    { name: "SOC 随机置位批量助手", desc: "导入航班执行申请表，按当前 SOC 动态航班逐条提交随机置位申请。", entry: "http-soc-positioning-helper", status: "done", homepageState: "beta" }
];
