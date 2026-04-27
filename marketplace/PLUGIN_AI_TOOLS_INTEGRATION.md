# Minder Plugin Marketplace - Plugin-AI Tools Integration Guide

## 🎯 Complete Architecture Overview

The Minder Plugin Marketplace implements a **modular, extensible plugin architecture** where plugins can define their own AI tools with complete autonomy. This document explains the complete integration between plugins and AI tools.

---

## 📐 Architecture Principles

### 1. Structural Modularity

**Core Principle**: Each plugin is a self-contained unit with:
- **Own AI Tools**: Plugins define tools in their manifest
- **Own Configuration**: Dynamic schema-based configuration
- **Own Dependencies**: Python packages and system requirements
- **Own Implementation**: Code for tool execution
- **Own Lifecycle**: Install, enable, disable, uninstall independently

### 2. AI Tools as First-Class Citizens

**Key Innovation**: AI tools are not separate entities but **integral parts of plugins**:

```yaml
# Plugin manifest defines AI tools
ai_tools:
  default_enabled: true
  tools:
    - name: text_analyzer
      display_name: "Text Analyzer"
      description: "Analyzes text for insights"
      tool_type: analysis
      endpoint_path: /api/v1/tools/analyze
      http_method: POST
      required_tier: community
      implementation_code: |
        def analyze_text(text: str) -> dict:
            return {"insights": ai_analyze(text)}
```

### 3. Tier-Based Access Control

**Three-Tier System**:
- **Community** (Free): Essential tools and plugins
- **Professional** ($29/mo): Advanced tools and priority support
- **Enterprise** (Custom): Full access with dedicated support

**Access Enforcement**:
- Plugin-level tier requirements
- Tool-level tier requirements
- Automatic tier checking
- Visual upgrade prompts

---

## 🔄 Plugin-AI Tools Relationship

### Plugin as Container

```
Plugin (Container)
├── Metadata (name, version, author)
├── Configuration Schema
├── Dependencies
└── AI Tools
    ├── Tool 1 (text_analyzer)
    │   ├── Parameters Schema
    │   ├── Response Schema
    │   ├── Configuration
    │   └── Implementation
    ├── Tool 2 (sentiment_analyzer)
    └── Tool 3 (keyword_extractor)
```

### Lifecycle Cascade Effects

**Plugin Operations Affect AI Tools**:

1. **Enable Plugin** → All default-enabled tools become available
2. **Disable Plugin** → All tools become unavailable
3. **Uninstall Plugin** → Tools removed from system
4. **Configure Plugin** → Shared configuration applies to all tools

**Independent Tool Management**:
- Tools can be enabled/disabled independently
- Tools can have individual configurations
- Tools can be tested independently
- Tools have independent tier requirements

---

## 📋 Manifest V3 Schema

### Complete Plugin Definition

```yaml
# Basic Information
name: advanced-analytics
display_name: "Advanced Analytics Plugin"
description: "Provides advanced data analysis and visualization tools"
version: "1.0.0"
author: "DataCorp Inc."
category: analytics
tags: [data, analysis, visualization]
license: MIT

# Tier & Pricing
tier: professional
pricing:
  model: subscription
  monthly_price: 29.99

# AI Tools Definition
ai_tools:
  default_enabled: true
  
  # Shared configuration for all tools
  shared_configuration:
    properties:
      api_key:
        type: string
        description: "API key for external services"
  
  shared_defaults:
    api_key: "default_key"
  
  # Individual tools
  tools:
    - name: trend_analysis
      display_name: "Trend Analysis Tool"
      description: "Analyzes trends in time series data"
      tool_type: analysis
      category: analysis
      endpoint_path: /api/v1/tools/trend-analysis
      http_method: POST
      
      # Tier requirement
      required_tier: community
      
      # Parameters schema
      parameters_schema:
        data:
          type: array
          description: "Time series data"
          required: true
        window_size:
          type: integer
          description: "Window size for moving average"
          default: 7
      
      # Response schema
      response_schema:
        type: object
        properties:
          trends:
            type: array
          confidence:
            type: number
      
      # Tool configuration
      configuration_schema:
        properties:
          sensitivity:
            type: number
            description: "Analysis sensitivity"
          algorithm:
            type: string
            description: "Algorithm to use"
        required: [algorithm]
      
      default_configuration:
        sensitivity: 0.8
        algorithm: "moving_average"
      
      # Flags
      is_default_enabled: true
      requires_configuration: false
      allow_user_configuration: true
      display_order: 1
      tags: [trends, time-series]
      version: "1.0.0"
    
    - name: predictive_modeling
      display_name: "Predictive Modeling Tool"
      description: "Advanced ML-based predictions"
      tool_type: analysis
      category: analysis
      endpoint_path: /api/v1/tools/predictive-modeling
      http_method: POST
      
      # Higher tier requirement
      required_tier: professional
      
      # Requires configuration
      requires_configuration: true
      
      parameters_schema:
        input_data:
          type: array
          description: "Training data"
          required: true
        model_type:
          type: string
          description: "Type of ML model"
          enum: [random_forest, neural_network, svm]
          required: true
      
      configuration_schema:
        properties:
          model_type:
            type: string
          accuracy_threshold:
            type: number
          training_iterations:
            type: integer
        required: [model_type]
      
      default_configuration:
        model_type: "random_forest"
        accuracy_threshold: 0.8
        training_iterations: 100
      
      is_default_enabled: false
      requires_configuration: true
      allow_user_configuration: true
      display_order: 2
      tags: [ml, prediction, advanced]
      version: "1.5.0"

# Plugin-level Configuration
configuration_schema:
  properties:
    max_data_points:
      type: integer
      description: "Maximum data points for analysis"
    cache_enabled:
      type: boolean
      description: "Enable result caching"
  required: [max_data_points]

default_configuration:
  max_data_points: 10000
  cache_enabled: true

# Dependencies
dependencies:
  - name: pandas
    version: ">=2.0.0"
    optional: false
  - name: scikit-learn
    version: ">=1.3.0"
    optional: false
  - name: matplotlib
    version: ">=3.5.0"
    optional: true

# Lifecycle
requires_restart: false
is_default_enabled: true
can_be_disabled: true

# Metadata
homepage: https://datacorp.example/plugins/advanced-analytics
repository: https://github.com/datacorp/advanced-analytics-plugin
documentation: https://docs.datacorp.example/advanced-analytics
logo_url: https://datacorp.example/logo.png
screenshots:
  - https://datacorp.example/screenshot1.png
  - https://datacorp.example/screenshot2.png
```

---

## 🔌 Frontend Integration

### 1. Plugin Detail Page

Shows AI tools as **integral part of plugin**:

```typescript
// /marketplace/plugins/{id}/page.tsx
{activeTab === "overview" && (
  <>
    {/* AI Tools Preview */}
    {aiTools.length > 0 && (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            AI Tools ({aiTools.length})
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            This plugin provides {aiTools.length} AI tools
          </p>
        </CardHeader>
        <CardContent>
          {aiTools.slice(0, 4).map((tool) => (
            <div key={tool.id}>
              <h4>{tool.tool_name}</h4>
              <TierEnforcementBadge
                currentTier="community"
                requiredTier={tool.required_tier}
                featureName={tool.tool_name}
              />
              <p>{tool.description}</p>
              <Badge>{tool.type}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    )}
  </>
)}
```

### 2. AI Tools Tab

Dedicated tab showing **all tools from this plugin**:

```typescript
{activeTab === "ai-tools" && (
  <div className="space-y-6">
    <div>
      <h2 className="text-2xl font-bold">AI Tools</h2>
      <p className="text-muted-foreground">
        This plugin provides {aiTools.length} AI tools
      </p>
    </div>

    <div className="grid md:grid-cols-2 gap-4">
      {aiTools.map((tool) => (
        <Card key={tool.id}>
          <CardHeader>
            <CardTitle>{tool.tool_name}</CardTitle>
            <TierEnforcementBadge
              currentTier="community"
              requiredTier={tool.required_tier}
              featureName={tool.tool_name}
            />
          </CardHeader>
          <CardContent>
            <p>{tool.description}</p>
            
            {/* Tool Details */}
            <div className="space-y-2 text-sm">
              <div>Type: <Badge>{tool.type}</Badge></div>
              <div>Method: <Badge>{tool.method}</Badge></div>
              <div>Endpoint: <code>{tool.endpoint}</code></div>
            </div>

            {/* Status */}
            <div>
              {tool.is_enabled ? (
                <Badge className="bg-green-500/20 text-green-400">
                  Enabled
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-destructive/20">
                  Disabled
                </Badge>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 mt-4">
              <Button
                disabled={!tool.is_enabled}
                onClick={() => testTool(tool.id)}
              >
                Test
              </Button>
              <Button
                onClick={() => configureTool(tool.id)}
              >
                Configure
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  </div>
)}
```

### 3. Manifest Tab

Shows **complete plugin manifest** including:

```typescript
{activeTab === "manifest" && (
  <PluginManifestViewer
    manifest={plugin.manifest}
    pluginName={plugin.display_name}
  />
)}
```

**Displays**:
- Overview (name, version, tier, etc.)
- AI Tools (all tools with schemas)
- Dependencies (required and optional)
- Configuration Schema
- Default Configuration
- Lifecycle Settings

---

## 🎮 User Interactions

### 1. Plugin Installation

**Multi-Step Wizard with AI Tools Awareness**:

```
Step 1: Overview
├── Plugin information
├── Tier requirements
└── AI tools count preview

Step 2: Configure
├── Plugin-level configuration
└── Tool-specific configurations (if required)

Step 3: Confirm
├── Review plugin settings
├── Review AI tools to be enabled
└── Agree to terms

Step 4: Installing
├── Install plugin
├── Enable default-enabled AI tools
└── Configure shared settings

Step 5: Complete
└── Success with AI tools ready to use
```

### 2. Plugin Lifecycle Management

**Enable Plugin**:
```typescript
// Cascade effect
enablePlugin(pluginId)
  → Install plugin
  → Enable all default-enabled AI tools
  → Apply shared configuration
  → Tools become available
```

**Disable Plugin**:
```typescript
// Cascade effect
disablePlugin(pluginId)
  → Disable plugin
  → Disable all AI tools
  → Tools become unavailable
  → Preserve configuration
```

**Uninstall Plugin**:
```typescript
// Irversible action
uninstallPlugin(pluginId)
  → Uninstall plugin
  → Remove all AI tools
  → Delete configuration
  → Clean up resources
```

### 3. Independent Tool Management

**Enable Tool** (without enabling plugin):
```typescript
enableTool(toolId)
  → Tool becomes available
  → Independent of plugin state
  → Can be used in other plugins
```

**Disable Tool**:
```typescript
disableTool(toolId)
  → Tool becomes unavailable
  → Plugin remains enabled
  → Other tools unaffected
```

---

## 🎨 UI Components

### 1. PluginCard

Shows plugin with AI tools preview:

```typescript
<PluginCard plugin={plugin}>
  {/* Basic Info */}
  <h3>{plugin.display_name}</h3>
  <p>{plugin.description}</p>
  
  {/* AI Tools Preview */}
  <div className="flex items-center gap-2">
    <Zap className="h-4 w-4" />
    <span>{plugin.ai_tools_count || 0} AI Tools</span>
  </div>
  
  {/* Tier Badge */}
  <TierEnforcementBadge
    currentTier="community"
    requiredTier={plugin.base_tier}
    featureName={plugin.display_name}
  />
  
  {/* Actions */}
  <Button onClick={viewDetails}>View Details</Button>
  <Button onClick={install}>Install</Button>
</PluginCard>
```

### 2. TierEnforcementBadge

Shows tier restrictions with upgrade prompts:

```typescript
<TierEnforcementBadge
  currentTier="community"
  requiredTier="professional"
  featureName="Advanced Analytics Tool"
  description="Requires Professional tier or higher"
  showUpgradePrompt={true}
  onUpgrade={() => window.location.href = "/pricing"}
/>
```

**States**:
- ✅ Accessible (green checkmark)
- 🔒 Locked (yellow lock icon)
- 💰 Upgrade prompt with pricing

### 3. PluginLifecycleManager

Manages plugin operations with cascade warnings:

```typescript
<PluginLifecycleManager
  plugin={plugin}
  onActionComplete={() => refetch()}
/>
```

**Features**:
- Enable/disable with confirmation
- Uninstall with warning
- Shows affected AI tools
- Cascade effect information
- Progress indication

### 4. PluginManifestViewer

Displays complete manifest structure:

```typescript
<PluginManifestViewer
  manifest={plugin.manifest}
  pluginName={plugin.display_name}
/>
```

**Sections**:
- Overview (metadata, tier, version)
- AI Tools (all tools with schemas)
- Dependencies (required/optional)
- Configuration Schema
- Default Configuration
- Lifecycle Settings

---

## 📊 API Integration

### Plugin Endpoints

```typescript
// Get plugin with AI tools
GET /v1/marketplace/plugins/{id}
Response: {
  id: string;
  display_name: string;
  manifest: {
    ai_tools: {
      tools: AITool[];
    };
  };
}

// List plugins with AI tools count
GET /v1/marketplace/plugins
Response: {
  plugins: Plugin[];
  each with ai_tools_count
}

// Install plugin
POST /v1/marketplace/plugins/{id}/install
Body: { config: Record<string, any> }
Response: {
  message: string;
  enabled_tools: string[];
  disabled_tools: string[];
}
```

### AI Tools Endpoints

```typescript
// Get AI tools for plugin
GET /v1/marketplace/plugins/{id}/ai-tools
Response: {
  tools: AITool[];
}

// Enable AI tool
PUT /v1/marketplace/ai/tools/{tool_id}/enable
Response: {
  message: string;
  tool: AITool;
}

// Disable AI tool
DELETE /v1/marketplace/ai/tools/{tool_id}/disable
Response: {
  message: string;
  tool: AITool;
}

// Test AI tool
POST /v1/marketplace/ai/tools/{tool_id}/test
Body: { parameters: Record<string, any> }
Response: {
  result: any;
  execution_time: number;
}
```

---

## 🔄 State Management

### React Query Keys

```typescript
// Plugin queries
['plugin', pluginId]
['plugins', filters]
['installed-plugins']

// AI tools queries
['plugin-ai-tools', pluginId]
['ai-tools', filters]
['ai-tool', toolId]

// Default plugins
['default-plugins', tier]

// Manifest
['plugin-manifest', pluginId]
```

### Cache Invalidation

```typescript
// When plugin state changes
queryClient.invalidateQueries({
  queryKey: ['plugin', pluginId]
});

// When plugin enabled/disabled
queryClient.invalidateQueries({
  queryKey: ['installed-plugins']
});

// When AI tools change
queryClient.invalidateQueries({
  queryKey: ['ai-tools']
});
```

---

## 🎯 Use Cases

### Use Case 1: User Installs Plugin

```
1. User browses marketplace
2. Finds "Advanced Analytics" plugin
3. Clicks "Install"
4. Sees plugin provides 5 AI tools:
   - Trend Analysis (Community)
   - Predictive Modeling (Professional)
   - Data Visualization (Community)
   - Anomaly Detection (Enterprise)
   - Report Generator (Professional)
5. Configures plugin settings
6. Confirms installation
7. Plugin installed with 3 tools enabled (Community tier)
8. 2 tools show "Upgrade to Professional" badges
```

### Use Case 2: User Manages AI Tools

```
1. User goes to Dashboard
2. Finds "Advanced Analytics" plugin
3. Clicks "AI Tools" button
4. Sees all 5 tools with status
5. Enables "Predictive Modeling" (upgrades tier)
6. Tests tool with sample data
7. Configures tool parameters
8. Tool ready to use
```

### Use Case 3: Developer Submits Plugin

```
1. Developer goes to Developer Portal
2. Clicks "New Plugin"
3. Fills in plugin information
4. Defines AI tools in manifest:
   - Tool names, types, descriptions
   - Parameter schemas
   - Response schemas
   - Configuration requirements
5. Uploads implementation code
6. Specifies tier requirements
7. Submits for review
8. Admin reviews manifest
9. Plugin approved
10. Available in marketplace
```

---

## 🚀 Advanced Features

### 1. Tool Dependencies

Tools can depend on other tools:

```yaml
ai_tools:
  tools:
    - name: data_preprocessor
      depends_on: []
    
    - name: analyzer
      depends_on: [data_preprocessor]
      requires:
        - data_preprocessor.enabled: true
```

### 2. Tool Composition

Tools can be chained together:

```yaml
ai_tools:
  tools:
    - name: analyze_and_visualize
      type: automation
      composition:
        - analyze_data
        - create_visualization
```

### 3. Dynamic Tool Loading

Tools can be loaded dynamically:

```typescript
// Load tool implementation
const toolImplementation = await import(
  `/plugins/${pluginId}/tools/${toolName}.js`
);

// Execute tool
const result = await toolImplementation.execute(parameters);
```

### 4. Tool Versioning

Tools can have independent versions:

```yaml
ai_tools:
  tools:
    - name: analyzer
      version: "2.0.0"
      compatible_versions: ["1.0.0", "1.5.0"]
```

---

## 📈 Monitoring & Analytics

### Plugin Metrics

```typescript
interface PluginMetrics {
  plugin_id: string;
  installations: number;
  active_users: number;
  ai_tools_usage: {
    [tool_id: string]: {
      invocations: number;
      avg_execution_time: number;
      success_rate: number;
    };
  };
}
```

### Tool Usage Tracking

```typescript
// Track tool invocations
trackToolUsage({
  toolId: tool.id,
  pluginId: plugin.id,
  userId: user.id,
  timestamp: Date.now(),
  parameters: params,
  executionTime: duration,
  success: true
});
```

---

## 🎓 Best Practices

### For Plugin Developers

1. **Manifest Design**:
   - Use clear, descriptive tool names
   - Provide detailed parameter schemas
   - Set appropriate tier requirements
   - Include configuration defaults

2. **Tool Organization**:
   - Group related tools
   - Use consistent naming
   - Provide usage examples
   - Document dependencies

3. **Configuration**:
   - Keep required fields minimal
   - Provide sensible defaults
   - Allow user customization
   - Validate configurations

### For Users

1. **Plugin Selection**:
   - Check tier requirements
   - Review AI tools included
   - Understand dependencies
   - Read documentation

2. **Configuration**:
   - Start with defaults
   - Adjust based on needs
   - Test before production
   - Monitor performance

3. **Tool Management**:
   - Enable only needed tools
   - Disable unused tools
   - Keep tools updated
   - Monitor usage metrics

---

## 🔐 Security Considerations

### 1. Input Validation

```typescript
// Validate tool parameters
const validateParameters = (
  tool: AITool,
  params: Record<string, any>
) => {
  const schema = tool.parameters_schema;
  // Validate against schema
  const validation = validateAgainstSchema(params, schema);
  return validation;
};
```

### 2. Access Control

```typescript
// Check tool access
const canAccessTool = (
  tool: AITool,
  userTier: string
) => {
  const tierOrder = {
    community: 0,
    professional: 1,
    enterprise: 2
  };
  const toolTier = tierOrder[tool.required_tier];
  const userTierLevel = tierOrder[userTier];
  return userTierLevel >= toolTier;
};
```

### 3. Rate Limiting

```typescript
// Rate limit tool invocations
const rateLimitTool = async (toolId: string) => {
  const usage = await getToolUsage(toolId);
  if (usage.count > MAX_USAGE) {
    throw new Error("Rate limit exceeded");
  }
};
```

---

## 🎉 Summary

The Minder Plugin Marketplace provides:

✅ **Complete Plugin-AI Tools Integration**
- Plugins define tools in manifests
- Tools are integral parts of plugins
- Independent tool management

✅ **Structural Modularity**
- Plugins are self-contained units
- Tools have own configurations
- Full lifecycle management

✅ **Grafana-Style Marketplace**
- Plugin browsing and discovery
- AI tools showcase
- Tier-based access control
- Installation and management

✅ **Developer-Friendly**
- Comprehensive manifest schema
- Clear submission process
- Testing and validation tools
- Analytics and monitoring

✅ **User-Friendly**
- Intuitive interface
- Clear tier requirements
- Easy configuration
- Transparent operations

This architecture enables **unlimited extensibility** while maintaining **consistency** and **security**.
