import type { ToolItem } from "./models";

export const tools: ToolItem[] = [
    { name: "锁班皇帝（新）", desc: "好活，直接调用接口锁班，极速。", entry: "http-lock-entry-helper", status: "done", homepageState: "beta" },
    { name: "飞行经历查询（皇帝版）", desc: "好活，直接调用接口查完整飞行经历和起落数，极速。", entry: "http-flight-stats-helper", status: "done", homepageState: "beta" },
    { name: "飞行人员信息查询（皇帝版）", desc: "好活，哈哈。直接调用 IEB 接口查询基础信息、技术等级、运行资格和训练检查记录。", entry: "http-qualification-query-helper", status: "done", homepageState: "beta" },
    { name: "OA 已阅助手（HTTP版）", desc: "扫描全部 OA 待办，按指定数量或无限模式逐条处理可点击的公文已阅。", entry: "http-oa-read-helper", status: "done", homepageState: "beta" }
];
