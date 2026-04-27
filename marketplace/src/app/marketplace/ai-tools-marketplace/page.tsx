"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Search,
  Filter,
  Zap,
  Shield,
  CheckCircle2,
  XCircle,
  Play,
  Settings,
  Star,
  TrendingUp,
} from "lucide-react";
import { aiToolsApi } from "@/lib/api/ai-tools";
import { AITool } from "@/lib/types/plugin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

export default function AIToolsMarketplacePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedTier, setSelectedTier] = useState<string>("");
  const [selectedType, setSelectedType] = useState<string>("");

  // Fetch all AI tools
  const { data: aiToolsData, isLoading, error } = useQuery({
    queryKey: ["ai-tools-marketplace", searchQuery, selectedCategory, selectedTier, selectedType],
    queryFn: () => aiToolsApi.getAllAITools(true, selectedCategory || undefined, selectedTier || undefined),
  });

  const tools = aiToolsData?.tools || [];

  // Group tools by category
  const toolsByCategory = tools.reduce((acc, tool) => {
    const category = tool.category || "general";
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(tool);
    return acc;
  }, {} as Record<string, AITool[]>);

  const categories = Object.keys(toolsByCategory);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <Zap className="h-8 w-8 text-primary" />
                AI Tools Marketplace
              </h1>
              <p className="text-muted-foreground">
                Discover, test, and enable individual AI tools from all plugins
              </p>
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search AI tools..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            <Button
              variant={selectedType === "analysis" ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedType(selectedType === "analysis" ? "" : "analysis")}
            >
              Analysis
            </Button>
            <Button
              variant={selectedType === "action" ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedType(selectedType === "action" ? "" : "action")}
            >
              Action
            </Button>
            <Button
              variant={selectedType === "query" ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedType(selectedType === "query" ? "" : "query")}
            >
              Query
            </Button>
            <Button
              variant={selectedType === "automation" ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedType(selectedType === "automation" ? "" : "automation")}
            >
              Automation
            </Button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="border-b border-border bg-card/30">
        <div className="container mx-auto px-4 py-6">
          <div className="grid md:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-3xl font-bold">{tools.length}</p>
              <p className="text-sm text-muted-foreground">Total Tools</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-green-400">
                {tools.filter((t) => t.required_tier === "community").length}
              </p>
              <p className="text-sm text-muted-foreground">Free Tools</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-blue-400">
                {tools.filter((t) => t.required_tier === "professional").length}
              </p>
              <p className="text-sm text-muted-foreground">Professional Tools</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-purple-400">
                {tools.filter((t) => t.required_tier === "enterprise").length}
              </p>
              <p className="text-sm text-muted-foreground">Enterprise Tools</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
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

        {/* AI Tools by Category */}
        {!isLoading && !error && categories.map((category) => (
          <div key={category} className="mb-12">
            <h2 className="text-2xl font-bold mb-6 capitalize flex items-center gap-2">
              <Zap className="h-6 w-6" />
              {category}
              <Badge variant="outline">{toolsByCategory[category].length} tools</Badge>
            </h2>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {toolsByCategory[category].map((tool) => (
                <Card key={tool.id} className="border-border bg-card/50 backdrop-blur hover:border-primary/50 transition-colors">
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <CardTitle className="text-lg">{tool.tool_name}</CardTitle>
                        <p className="text-sm text-muted-foreground mt-1">by {tool.plugin_name}</p>
                      </div>
                      <Badge
                        className={
                          tool.required_tier === "community"
                            ? "bg-green-500/20 text-green-400 border-green-500/50"
                            : tool.required_tier === "professional"
                            ? "bg-blue-500/20 text-blue-400 border-blue-500/50"
                            : "bg-purple-500/20 text-purple-400 border-purple-500/50"
                        }
                      >
                        <Shield className="h-3 w-3 mr-1" />
                        {tool.required_tier}
                      </Badge>
                    </div>
                  </CardHeader>

                  <CardContent>
                    <p className="text-sm text-muted-foreground mb-4">
                      {tool.description || "No description provided"}
                    </p>

                    {/* Tool Details */}
                    <div className="space-y-2 text-sm mb-4">
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
                        <code className="text-xs bg-muted px-2 py-1 rounded truncate">
                          {tool.endpoint}
                        </code>
                      </div>
                    </div>

                    {/* Status */}
                    <div className="flex items-center justify-between mb-4">
                      <span className="text-muted-foreground">Status:</span>
                      {tool.is_enabled ? (
                        <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Enabled
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="bg-destructive/20 text-destructive">
                          <XCircle className="h-3 w-3 mr-1" />
                          Disabled
                        </Badge>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        disabled={!tool.is_enabled}
                        onClick={() => window.location.href = `/marketplace/ai-tools/${tool.id}`}
                      >
                        <Play className="h-4 w-4 mr-1" />
                        Test
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
