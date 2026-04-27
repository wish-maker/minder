"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, Circuit, Settings, Play, CheckCircle, XCircle } from "lucide-react";
import { aiToolsApi } from "@/lib/api/ai-tools";
import { AITool } from "@/lib/types/plugin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function AIToolsPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedTier, setSelectedTier] = useState<string>("");

  // Fetch all AI tools
  const { data: aiToolsData, isLoading, error } = useQuery({
    queryKey: ['ai-tools', selectedCategory, selectedTier],
    queryFn: () => aiToolsApi.getAllAITools(true, selectedCategory || undefined, selectedTier || undefined),
  });

  const tools = aiToolsData?.tools || [];

  // Group tools by plugin
  const toolsByPlugin = tools.reduce((acc, tool) => {
    if (!acc[tool.plugin_name]) {
      acc[tool.plugin_name] = [];
    }
    acc[tool.plugin_name].push(tool);
    return acc;
  }, {} as Record<string, AITool[]>);

  // Test tool function
  const handleTestTool = async (toolId: string, params: Record<string, any>) => {
    // Mock implementation - replace with actual API call
    return {
      success: true,
      result: `Tool ${toolId} executed with params: ${JSON.stringify(params)}`,
      timestamp: new Date().toISOString(),
    };
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center gap-3 mb-4">
            <Brain className="h-8 w-8 text-primary" />
            <h1 className="text-3xl font-bold">AI Tools Dashboard</h1>
          </div>
          <p className="text-muted-foreground">
            Browse and test AI tools provided by all installed plugins
          </p>

          {/* Filters */}
          <div className="flex gap-2 mt-4">
            <Button
              variant={selectedTier === 'community' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedTier(selectedTier === 'community' ? '' : 'community')}
            >
              Community Tools
            </Button>
            <Button
              variant={selectedTier === 'professional' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedTier(selectedTier === 'professional' ? '' : 'professional')}
            >
              Professional Tools
            </Button>
            <Button
              variant={selectedTier === 'enterprise' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedTier(selectedTier === 'enterprise' ? '' : 'enterprise')}
            >
              Enterprise Tools
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        {/* Stats */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">{tools.length}</div>
            <div className="text-sm text-muted-foreground">Total AI Tools</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">{Object.keys(toolsByPlugin).length}</div>
            <div className="text-sm text-muted-foreground">Plugins with Tools</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">
              {tools.filter(t => t.type === 'analysis').length}
            </div>
            <div className="text-sm text-muted-foreground">Analysis Tools</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">
              {tools.filter(t => t.type === 'action').length}
            </div>
            <div className="text-sm text-muted-foreground">Action Tools</div>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
            <p className="mt-4 text-muted-foreground">Loading AI tools...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="text-center py-12">
            <p className="text-destructive">Failed to load AI tools. Please try again.</p>
          </div>
        )}

        {/* AI Tools by Plugin */}
        {!isLoading && !error && Object.entries(toolsByPlugin).map(([pluginName, pluginTools]) => (
          <div key={pluginName} className="mb-8">
            <h2 className="text-2xl font-bold mb-4 capitalize flex items-center gap-2">
              <Circuit className="h-6 w-6" />
              {pluginName}
              <Badge variant="outline" className="text-sm">
                {pluginTools.length} tools
              </Badge>
            </h2>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {pluginTools.map((tool) => (
                <Card key={tool.id} className="border-border bg-card/50 backdrop-blur">
                  <CardHeader>
                    <CardTitle className="text-lg">{tool.tool_name}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground mb-4">
                      {tool.description || 'No description provided'}
                    </p>

                    {/* Tool Details */}
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Type:</span>
                        <Badge variant="outline">{tool.type}</Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Method:</span>
                        <Badge variant="outline">{tool.method}</Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Endpoint:</span>
                        <code className="text-xs bg-muted px-2 py-1 rounded">
                          {tool.endpoint}
                        </code>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Tier:</span>
                        <Badge
                          className={
                            tool.required_tier === 'community'
                              ? 'bg-green-500/20 text-green-400 border-green-500/50'
                              : tool.required_tier === 'professional'
                              ? 'bg-blue-500/20 text-blue-400 border-blue-500/50'
                              : 'bg-purple-500/20 text-purple-400 border-purple-500/50'
                          }
                        >
                          {tool.required_tier}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Status:</span>
                        {tool.is_enabled ? (
                          <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Enabled
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-destructive/20 text-destructive">
                            <XCircle className="h-3 w-3 mr-1" />
                            Disabled
                          </Badge>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2 mt-4">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        disabled={!tool.is_enabled}
                        onClick={() => window.location.href = `/marketplace/ai-tools/${tool.id}`}
                      >
                        <Play className="h-4 w-4 mr-1" />
                        Test Tool
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        onClick={() => window.location.href = `/marketplace/plugins/${tool.plugin_id}`}
                      >
                        <Settings className="h-4 w-4 mr-1" />
                        View Plugin
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}