interface HomePatternGateLogic {
  enabled: boolean;
  pattern: number[];
  appendNode(sequence: number[], node: number): number[];
  matches(sequence: number[]): boolean;
}

interface Window {
  HomePatternGateLogic: HomePatternGateLogic;
  WatchdogTheme?: {
    getTheme(): "light" | "dark";
    setTheme(theme: "light" | "dark"): "light" | "dark";
    toggleTheme(): "light" | "dark";
    storageKey: string;
  };
}
