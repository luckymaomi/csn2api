export type ToolStatus = "done" | "wip";
export type ToolHomepageState = "enabled" | "beta" | "cooling";

export interface ToolItem {
  name: string;
  desc: string;
  entry: string;
  status: ToolStatus;
  homepageState?: ToolHomepageState;
}
