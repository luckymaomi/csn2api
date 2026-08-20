type ToolStatus = "done" | "wip";
type ToolHomepageState = "enabled" | "beta" | "cooling";

interface ToolItem {
  name: string;
  desc: string;
  entry: string;
  status: ToolStatus;
  homepageState?: ToolHomepageState;
}

