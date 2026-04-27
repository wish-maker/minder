import apiClient from './client';
import { Plugin, PluginFilters } from '../types/plugin';

interface PluginsResponse {
  plugins: Plugin[];
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const pluginsApi = {
  // List all plugins with optional filters
  listPlugins: async (filters?: PluginFilters): Promise<PluginsResponse> => {
    const params = new URLSearchParams();

    if (filters?.category) params.append('category', filters.category);
    if (filters?.tier) params.append('base_tier', filters.tier);
    if (filters?.pricing) params.append('pricing_model', filters.pricing);
    if (filters?.search) params.append('q', filters.search);
    if (filters?.featured) params.append('featured', 'true');

    const response = await apiClient.get(`/v1/marketplace/plugins?${params.toString()}`);
    return response.data;
  },

  // Search plugins
  searchPlugins: async (query: string, page = 1, pageSize = 10): Promise<PluginsResponse> => {
    const response = await apiClient.get(
      `/v1/marketplace/plugins/search?q=${encodeURIComponent(query)}&page=${page}&page_size=${pageSize}`
    );
    return response.data;
  },

  // Get plugin by ID
  getPlugin: async (pluginId: string): Promise<Plugin> => {
    const response = await apiClient.get(`/v1/marketplace/plugins/${pluginId}`);
    return response.data;
  },

  // Get featured plugins
  getFeaturedPlugins: async (limit = 10): Promise<PluginsResponse> => {
    const response = await apiClient.get(`/v1/marketplace/plugins/featured?limit=${limit}`);
    return response.data;
  },

  // Install plugin
  installPlugin: async (pluginId: string, configuration?: Record<string, any>): Promise<any> => {
    const response = await apiClient.post(`/v1/marketplace/plugins/${pluginId}/install`, {
      configuration
    });
    return response.data;
  },

  // Uninstall plugin
  uninstallPlugin: async (installationId: string): Promise<any> => {
    const response = await apiClient.delete(`/v1/marketplace/installations/${installationId}`);
    return response.data;
  },

  // Enable plugin
  enablePlugin: async (pluginName: string): Promise<any> => {
    const response = await apiClient.post(`/v1/plugins/${pluginName}/enable`);
    return response.data;
  },

  // Disable plugin
  disablePlugin: async (pluginName: string): Promise<any> => {
    const response = await apiClient.post(`/v1/plugins/${pluginName}/disable`);
    return response.data;
  }
};