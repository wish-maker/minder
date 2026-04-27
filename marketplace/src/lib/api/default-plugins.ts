import apiClient from "./client";
import { DefaultPlugin } from "../types/default-plugins";

/**
 * Default Plugins API
 * Handles default plugin installation and tier-based setup
 */

export const defaultPluginsApi = {
  /**
   * Get default plugins configuration for a tier
   */
  async getDefaultPlugins(tier: "community" | "professional" | "enterprise"): Promise<{
    plugins: DefaultPlugin[];
    auto_enabled: DefaultPlugin[];
    available: DefaultPlugin[];
  }> {
    const response = await apiClient.get(`/v1/marketplace/default-plugins/${tier}`);
    return response.data;
  },

  /**
   * Install default plugins for a new user
   */
  async installDefaultPlugins(tier: "community" | "professional" | "enterprise"): Promise<{
    installed: Array<{ pluginId: string; success: boolean }>;
    failed: string[];
  }> {
    const response = await apiClient.post(`/v1/marketplace/default-plugins/install`, { tier });
    return response.data;
  },

  /**
   * Enable a default plugin
   */
  async enableDefaultPlugin(pluginId: string): Promise<{
    message: string;
    plugin: any;
  }> {
    const response = await apiClient.post(`/v1/plugins/${pluginId}/enable`, {
      source: "default-plugins",
    });
    return response.data;
  },

  /**
   * Disable a default plugin
   */
  async disableDefaultPlugin(pluginId: string): Promise<{
    message: string;
    plugin: any;
  }> {
    const response = await apiClient.post(`/v1/plugins/${pluginId}/disable`, {
      source: "default-plugins",
    });
    return response.data;
  },

  /**
   * Get plugin dependencies
   */
  async getPluginDependencies(pluginId: string): Promise<{
    requires: string[];
    required_by: string[];
  }> {
    const response = await apiClient.get(`/v1/plugins/${pluginId}/dependencies`);
    return response.data;
  },

  /**
   * Check if plugin can be enabled (tier check, dependencies check)
   */
  async checkPluginEligibility(pluginId: string): Promise<{
    eligible: boolean;
    reason?: string;
    tier_required?: string;
    missing_dependencies?: string[];
  }> {
    const response = await apiClient.get(`/v1/plugins/${pluginId}/eligibility`);
    return response.data;
  },
};
