import apiClient from "./client";
import { Plugin } from "../types/plugin";

/**
 * Plugin Management API
 * Handles plugin lifecycle operations: enable, disable, configure
 */

export const pluginsManagementApi = {
  /**
   * Enable a plugin
   */
  async enablePlugin(pluginId: string): Promise<{ message: string; plugin: Plugin }> {
    const response = await apiClient.post(`/v1/plugins/${pluginId}/enable`);
    return response.data;
  },

  /**
   * Disable a plugin
   */
  async disablePlugin(pluginId: string): Promise<{ message: string; plugin: Plugin }> {
    const response = await apiClient.post(`/v1/plugins/${pluginId}/disable`);
    return response.data;
  },

  /**
   * Configure a plugin
   */
  async configurePlugin(
    pluginId: string,
    config: Record<string, any>
  ): Promise<{ message: string; plugin: Plugin }> {
    const response = await apiClient.put(`/v1/plugins/${pluginId}/config`, config);
    return response.data;
  },

  /**
   * Get plugin configuration
   */
  async getPluginConfig(pluginId: string): Promise<Record<string, any>> {
    const response = await apiClient.get(`/v1/plugins/${pluginId}/config`);
    return response.data;
  },

  /**
   * Test a plugin AI tool
   */
  async testTool(toolId: string, params: Record<string, any>): Promise<any> {
    const response = await apiClient.post(`/v1/marketplace/ai/tools/${toolId}/test`, params);
    return response.data;
  },

  /**
   * Get plugin health status
   */
  async getPluginHealth(pluginId: string): Promise<{
    status: "healthy" | "degraded" | "unhealthy";
    last_check: string;
    metrics: Record<string, any>;
  }> {
    const response = await apiClient.get(`/v1/plugins/${pluginId}/health`);
    return response.data;
  },

  /**
   * Get plugin logs
   */
  async getPluginLogs(pluginId: string, limit = 100): Promise<{
    logs: Array<{
      timestamp: string;
      level: string;
      message: string;
    }>;
  }> {
    const response = await apiClient.get(`/v1/plugins/${pluginId}/logs?limit=${limit}`);
    return response.data;
  },

  /**
   * Restart a plugin
   */
  async restartPlugin(pluginId: string): Promise<{ message: string; plugin: Plugin }> {
    const response = await apiClient.post(`/v1/plugins/${pluginId}/restart`);
    return response.data;
  },

  /**
   * Uninstall a plugin
   */
  async uninstallPlugin(pluginId: string): Promise<{ message: string }> {
    const response = await apiClient.delete(`/v1/plugins/${pluginId}`);
    return response.data;
  },
};
