import apiClient from './client';
import { AITool } from '../types/plugin';

interface AIToolsResponse {
  tools: AITool[];
  count: number;
}

export const aiToolsApi = {
  // Get all AI tools across all plugins
  getAllAITools: async (activeOnly = true, category?: string, tier?: string): Promise<AIToolsResponse> => {
    const params = new URLSearchParams();

    if (activeOnly) params.append('active_only', 'true');
    if (category) params.append('category', category);
    if (tier) params.append('tier', tier);

    const response = await apiClient.get(`/v1/marketplace/ai/tools?${params.toString()}`);
    return response.data;
  },

  // Get AI tools for specific plugin
  getPluginAITools: async (pluginId: string): Promise<AITool[]> => {
    const response = await apiClient.get(`/v1/marketplace/plugins/${pluginId}/ai-tools`);
    return response.data;
  },

  // Enable AI tool
  enableTool: async (toolId: string, configuration?: Record<string, any>): Promise<any> => {
    const response = await apiClient.put(`/v1/marketplace/ai/tools/${toolId}/enable`, {
      configuration
    });
    return response.data;
  },

  // Disable AI tool
  disableTool: async (toolId: string): Promise<any> => {
    const response = await apiClient.delete(`/v1/marketplace/ai/tools/${toolId}/disable`);
    return response.data;
  },

  // Sync AI tools from plugin manifest
  syncAITools: async (pluginName: string, manifest: Record<string, any>): Promise<any> => {
    const response = await apiClient.post('/v1/marketplace/ai/sync', {
      plugin_name: pluginName,
      manifest
    });
    return response.data;
  }
};