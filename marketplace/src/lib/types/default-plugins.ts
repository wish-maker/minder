// Default enabled plugins configuration
// These plugins are automatically installed for new users based on their tier

export interface DefaultPlugin {
  pluginId: string;
  minTier: "community" | "professional" | "enterprise";
  autoEnable: boolean;
  defaultConfig?: Record<string, any>;
  requiredBy?: string[]; // Other plugins that depend on this one
  category: "essential" | "recommended" | "optional";
}

export const DEFAULT_PLUGINS: DefaultPlugin[] = [
  // Community Tier (Free)
  {
    pluginId: "basic-ai-assistant",
    minTier: "community",
    autoEnable: true,
    category: "essential",
    defaultConfig: {
      max_tokens: 1000,
      model: "gpt-3.5-turbo",
    },
  },
  {
    pluginId: "code-formatter",
    minTier: "community",
    autoEnable: true,
    category: "essential",
    defaultConfig: {
      language: "typescript",
      tab_size: 2,
    },
  },
  {
    pluginId: "file-explorer",
    minTier: "community",
    autoEnable: true,
    category: "recommended",
  },

  // Professional Tier (Paid)
  {
    pluginId: "advanced-code-analyzer",
    minTier: "professional",
    autoEnable: false,
    category: "recommended",
    defaultConfig: {
      analysis_depth: "deep",
      security_scan: true,
    },
  },
  {
    pluginId: "test-generator",
    minTier: "professional",
    autoEnable: false,
    category: "recommended",
    defaultConfig: {
      framework: "jest",
      coverage_target: 80,
    },
  },
  {
    pluginId: "performance-profiler",
    minTier: "professional",
    autoEnable: false,
    category: "optional",
    defaultConfig: {
      sampling_rate: 0.1,
    },
  },

  // Enterprise Tier (Premium)
  {
    pluginId: "enterprise-security-scanner",
    minTier: "enterprise",
    autoEnable: false,
    category: "essential",
    defaultConfig: {
      scan_frequency: "daily",
      compliance_standards: ["SOC2", "ISO27001"],
    },
  },
  {
    pluginId: "custom-model-deployer",
    minTier: "enterprise",
    autoEnable: false,
    category: "recommended",
    defaultConfig: {
      max_models: 10,
      gpu_acceleration: true,
    },
  },
  {
    pluginId: "team-collaboration",
    minTier: "enterprise",
    autoEnable: false,
    category: "optional",
    defaultConfig: {
      max_team_size: 100,
      sso_integration: true,
    },
  },
];

export function getDefaultPluginsForTier(tier: "community" | "professional" | "enterprise"): DefaultPlugin[] {
  return DEFAULT_PLUGINS.filter((plugin) => {
    const tierLevels = { community: 0, professional: 1, enterprise: 2 };
    const pluginLevel = tierLevels[plugin.minTier];
    const userLevel = tierLevels[tier];
    return pluginLevel <= userLevel;
  });
}

export function getAutoEnabledPluginsForTier(tier: "community" | "professional" | "enterprise"): DefaultPlugin[] {
  return getDefaultPluginsForTier(tier).filter((plugin) => plugin.autoEnable);
}
