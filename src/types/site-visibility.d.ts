interface SiteVisibilityConfig {
  homepage: {
    patternGate: boolean;
  };
}

interface Window {
  siteVisibility: SiteVisibilityConfig;
}

declare var siteVisibility: SiteVisibilityConfig;
