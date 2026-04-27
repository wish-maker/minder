// Plugin types matching backend models
export interface Plugin {
  id: string;
  name: string;
  display_name: string;
  description: string;
  long_description?: string;
  author: string;
  author_email?: string;
  repository_url?: string;
  repository?: string;
  homepage?: string;
  distribution_type: 'container' | 'python' | 'typescript';
  docker_image?: string;
  current_version: string;
  pricing_model: 'free' | 'paid' | 'freemium';
  pricing_details?: string;
  base_tier: 'community' | 'professional' | 'enterprise';
  status: 'pending' | 'approved' | 'rejected';
  featured: boolean;
  is_enabled?: boolean;
  can_be_disabled?: boolean;
  is_default_enabled?: boolean;
  requires_restart?: boolean;
  download_count: number;
  rating_average?: number;
  rating_count: number;
  created_at: string;
  updated_at: string;
  published_at?: string;
  developer_id?: string;
  category_id?: string;
  categories?: string[];
  capabilities?: string[];
  screenshots?: string[];
  license?: string;
  license_url?: string;
  min_minder_version?: string;

  // Enhanced manifest support
  manifest?: {
    name: string;
    display_name: string;
    description: string;
    version: string;
    author: string;
    author_email?: string;
    organization?: string;
    category: string;
    tags: string[];
    license: string;
    tier: 'community' | 'professional' | 'enterprise';
    pricing?: any;
    python_version?: string;
    install_command?: string;
    requires_restart?: boolean;
    is_default_enabled?: boolean;
    can_be_disabled?: boolean;
    homepage?: string;
    repository?: string;
    documentation?: string;
    logo_url?: string;
    screenshots?: string[];
    minder_version?: string;
    breaking_changes?: string[];

    // AI Tools Configuration (Enhanced)
    ai_tools?: {
      default_enabled: boolean;
      tools: Array<{
        name: string;
        display_name: string;
        description: string;
        tool_type: 'analysis' | 'action' | 'query' | 'automation';
        category: string;
        endpoint_path: string;
        http_method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
        parameters_schema?: Record<string, {
          type: string;
          description: string;
          required: boolean;
          default?: any;
          enum?: string[];
          minimum?: number;
          maximum?: number;
          pattern?: string;
        }>;
        response_schema?: Record<string, any>;
        configuration_schema?: Record<string, any>;
        default_configuration?: Record<string, any>;
        required_tier: 'community' | 'professional' | 'enterprise';
        requires_configuration: boolean;
        allow_user_configuration: boolean;
        is_default_enabled: boolean;
        display_order: number;
        tags: string[];
        version: string;
        author?: string;
        implementation_code?: string;
        implementation_file?: string;
      }>;
      shared_configuration?: Record<string, any>;
      shared_defaults?: Record<string, any>;
    };

    // Dependencies
    dependencies?: Array<{
      name: string;
      version: string;
      optional: boolean;
    }>;

    // Configuration Schema
    configuration_schema?: {
      properties: Record<string, {
        type: string;
        description: string;
        default?: any;
      }>;
      required?: string[];
    };

    // Default Configuration
    default_configuration?: Record<string, any>;
  };

  // AI Tools count (for display)
  ai_tools_count?: number;

  // Configuration Schema (for backward compatibility)
  configuration_schema?: {
    fields: Array<{
      name: string;
      type: 'text' | 'password' | 'number' | 'boolean';
      label?: string;
      description?: string;
      placeholder?: string;
      required: boolean;
      default?: string | number | boolean;
    }>;
  };
}

export interface AITool {
  id: string;
  plugin_id: string;
  plugin_name: string;
  tool_name: string;
  type: 'analysis' | 'action' | 'query' | 'automation';
  description: string;
  endpoint: string;
  method: string;
  parameters?: Record<string, any>;
  response_format?: Record<string, any>;
  required_tier: 'community' | 'professional' | 'enterprise';
  is_enabled: boolean;
  category?: string;
  tags?: string[];
  configuration_schema?: Record<string, any>;
  default_configuration?: Record<string, any>;
}

export interface PluginInstallation {
  id: string;
  user_id: string;
  plugin_id: string;
  status: 'pending' | 'installed' | 'failed' | 'updating';
  enabled: boolean;
  configuration?: Record<string, any>;
  installed_at: string;
  updated_at: string;
}

export interface PluginFilters {
  category?: string;
  tier?: 'community' | 'professional' | 'enterprise';
  pricing?: 'free' | 'paid' | 'freemium';
  search?: string;
  featured?: boolean;
}

export interface MarketplaceStats {
  total_plugins: number;
  total_ai_tools: number;
  total_installations: number;
  active_users: number;
}