"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Download,
  Star,
  CheckCircle2,
  Settings,
  Play,
  Shield,
  Zap,
  Code,
  Image as ImageIcon,
} from "lucide-react";
import { pluginsApi, aiToolsApi } from "@/lib/api";
import { Plugin, AITool } from "@/lib/types/plugin";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import TierEnforcementBadge from "@/components/marketplace/TierEnforcementBadge";
import PluginManifestViewer from "@/components/marketplace/PluginManifestViewer";

export default function PluginDetailPage() {
  const params = useParams();
  const router = useRouter();
  const pluginId = params.id as string;
  const [activeTab, setActiveTab] = useState<"overview" | "ai-tools" | "reviews">("overview");

  // Fetch plugin details
  const { data: plugin, isLoading: pluginLoading, error: pluginError } = useQuery({
    queryKey: ['plugin', pluginId],
    queryFn: () => pluginsApi.getPlugin(pluginId),
    enabled: !!pluginId,
  });

  // Fetch AI tools for this plugin (as integral part of plugin)
  const { data: aiToolsData, isLoading: toolsLoading } = useQuery({
    queryKey: ['plugin-ai-tools', pluginId],
    queryFn: () => aiToolsApi.getPluginAITools(pluginId),
    enabled: !!pluginId,
  });

  // Fetch plugin manifest for detailed information
  const { data: manifestData } = useQuery({
    queryKey: ['plugin-manifest', pluginId],
    queryFn: async () => {
      // This would fetch the manifest from the backend
      // For now, we'll enhance the plugin data structure
      return plugin?.manifest || null;
    },
    enabled: !!pluginId,
  });

  const aiTools = aiToolsData?.tools || [];
  const manifest = manifestData || plugin?.manifest;

  if (pluginLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading plugin details...</p>
        </div>
      </div>
    );
  }

  if (pluginError || !plugin) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-destructive text-lg">Plugin not found</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/marketplace/plugins")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Plugins
          </Button>
        </div>
      </div>
    );
  }

  const isFree = plugin.pricing_model === "free";
  const tierColors = {
    community: "bg-green-500/20 text-green-400 border-green-500/50",
    professional: "bg-blue-500/20 text-blue-400 border-blue-500/50",
    enterprise: "bg-purple-500/20 text-purple-400 border-purple-500/50",
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button
            variant="ghost"
            className="mb-4"
            onClick={() => router.push("/marketplace/plugins")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Plugins
          </Button>

          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-4xl font-bold">{plugin.display_name}</h1>
                <Badge className={tierColors[plugin.base_tier]}>
                  {plugin.base_tier}
                </Badge>
                {plugin.featured && (
                  <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
                    Featured
                  </Badge>
                )}
              </div>
              <p className="text-lg text-muted-foreground">by {plugin.author}</p>
              <p className="text-muted-foreground mt-2">{plugin.description}</p>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" size="lg">
                <Settings className="mr-2 h-4 w-4" />
                Configure
              </Button>
              <Button size="lg" className="gap-2">
                <Download className="h-4 w-4" />
                Install Plugin
              </Button>
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-6 mt-6 text-sm">
            <div className="flex items-center gap-2">
              <Download className="h-4 w-4 text-muted-foreground" />
              <span className="font-semibold">{plugin.download_count}</span>
              <span className="text-muted-foreground">downloads</span>
            </div>
            {plugin.rating_count > 0 && (
              <div className="flex items-center gap-2">
                <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                <span className="font-semibold">{plugin.rating_average?.toFixed(1)}</span>
                <span className="text-muted-foreground">({plugin.rating_count} reviews)</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-400" />
              <span className="font-semibold">v{plugin.current_version}</span>
              <span className="text-muted-foreground">stable</span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-border bg-card/30">
        <div className="container mx-auto px-4">
          <div className="flex gap-4">
            <button
              className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                activeTab === "overview"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("overview")}
            >
              Overview
            </button>
            <button
              className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                activeTab === "ai-tools"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("ai-tools")}
            >
              AI Tools ({aiTools.length})
            </button>
            <button
              className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                activeTab === "manifest"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("manifest")}
            >
              Manifest
            </button>
            <button
              className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                activeTab === "reviews"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("reviews")}
            >
              Reviews
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="container mx-auto px-4 py-8">
        {activeTab === "overview" && (
          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              {/* Description */}
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>About this Plugin</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-invert max-w-none">
                    <p className="text-muted-foreground whitespace-pre-line">
                      {plugin.long_description || plugin.description}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* AI Tools Preview (Enhanced) */}
              {aiTools.length > 0 && (
                <Card className="border-border bg-card/50 backdrop-blur">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        <Zap className="h-5 w-5 text-primary" />
                        AI Tools ({aiTools.length})
                      </CardTitle>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setActiveTab("ai-tools")}
                      >
                        View All Tools
                      </Button>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      This plugin provides {aiTools.length} AI tool{aiTools.length !== 1 ? "s" : ""}
                    </p>
                  </CardHeader>
                  <CardContent>
                    <div className="grid md:grid-cols-2 gap-3">
                      {aiTools.slice(0, 4).map((tool) => (
                        <div
                          key={tool.id}
                          className="p-3 rounded-lg bg-muted/50 border border-border"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex-1">
                              <p className="font-medium text-sm">{tool.tool_name}</p>
                              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                                {tool.description}
                              </p>
                            </div>
                            <TierEnforcementBadge
                              currentTier="community"
                              requiredTier={tool.required_tier}
                              featureName={tool.tool_name}
                              description={`Requires ${tool.required_tier} tier`}
                              showUpgradePrompt={false}
                            />
                          </div>
                          <div className="flex items-center gap-2 text-xs">
                            <Badge variant="outline">{tool.type}</Badge>
                            {tool.is_enabled ? (
                              <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                                Enabled
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="bg-destructive/20 text-destructive">
                                Disabled
                              </Badge>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    {aiTools.length > 4 && (
                      <Button
                        variant="link"
                        className="mt-3"
                        onClick={() => setActiveTab("ai-tools")}
                      >
                        View {aiTools.length - 4} more tools →
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Features */}
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>Features</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2">
                    {plugin.capabilities?.map((capability, index) => (
                      <li key={index} className="flex items-start gap-2">
                        <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">{capability}</span>
                      </li>
                    )) || (
                      <li className="text-muted-foreground">No features listed</li>
                    )}
                  </ul>
                </CardContent>
              </Card>

              {/* Screenshots */}
              {plugin.screenshots && plugin.screenshots.length > 0 && (
                <Card className="border-border bg-card/50 backdrop-blur">
                  <CardHeader>
                    <CardTitle>Screenshots</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      {plugin.screenshots.map((screenshot, index) => (
                        <div
                          key={index}
                          className="aspect-video bg-muted rounded-lg flex items-center justify-center border border-border"
                        >
                          <ImageIcon className="h-12 w-12 text-muted-foreground" />
                          <p className="text-sm text-muted-foreground ml-2">{screenshot}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Sidebar */}
            <div className="space-y-6">
              {/* Pricing */}
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>Pricing</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Model:</span>
                      <Badge variant="outline" className="capitalize">
                        {plugin.pricing_model}
                      </Badge>
                    </div>
                    {plugin.pricing_model !== "free" && plugin.pricing_details && (
                      <div className="text-sm text-muted-foreground">
                        {plugin.pricing_details}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Technical Info */}
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>Technical Information</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Version:</span>
                    <span className="font-mono">v{plugin.current_version}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Type:</span>
                    <Badge variant="outline" className="capitalize">
                      {plugin.distribution_type}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Min Minder:</span>
                    <span className="font-mono">{plugin.min_minder_version || "Any"}</span>
                  </div>
                  {plugin.homepage && (
                    <div className="pt-2">
                      <a
                        href={plugin.homepage}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline text-sm"
                      >
                        Homepage →
                      </a>
                    </div>
                  )}
                  {plugin.repository && (
                    <div>
                      <a
                        href={plugin.repository}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline text-sm"
                      >
                        Repository →
                      </a>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Categories */}
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>Categories</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {plugin.categories?.map((category) => (
                      <Badge key={category} variant="outline">
                        {category}
                      </Badge>
                    )) || <span className="text-muted-foreground text-sm">No categories</span>}
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {activeTab === "ai-tools" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold">AI Tools</h2>
                <p className="text-muted-foreground">
                  This plugin provides {aiTools.length} AI tool{aiTools.length !== 1 ? "s" : ""}
                </p>
              </div>
            </div>

            {toolsLoading ? (
              <div className="text-center py-12">
                <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
                <p className="mt-4 text-muted-foreground">Loading AI tools...</p>
              </div>
            ) : aiTools.length === 0 ? (
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardContent className="text-center py-12">
                  <Zap className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">This plugin does not provide any AI tools.</p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid md:grid-cols-2 gap-4">
                {aiTools.map((tool) => (
                  <Card key={tool.id} className="border-border bg-card/50 backdrop-blur">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <CardTitle className="text-lg">{tool.tool_name}</CardTitle>
                        <TierEnforcementBadge
                          currentTier="community"
                          requiredTier={tool.required_tier}
                          featureName={tool.tool_name}
                          description={`Requires ${tool.required_tier} tier or higher`}
                        />
                      </div>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-muted-foreground mb-4">
                        {tool.description || "No description provided"}
                      </p>

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
                          <span className="text-muted-foreground">Status:</span>
                          {tool.is_enabled ? (
                            <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                              Enabled
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="bg-destructive/20 text-destructive">
                              Disabled
                            </Badge>
                          )}
                        </div>
                      </div>

                      <div className="flex gap-2 mt-4">
                        <Button
                          size="sm"
                          variant="outline"
                          className="flex-1"
                          disabled={!tool.is_enabled}
                        >
                          <Play className="h-4 w-4 mr-1" />
                          Test
                        </Button>
                        <Button size="sm" variant="outline" className="flex-1">
                          <Code className="h-4 w-4 mr-1" />
                          View Code
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "reviews" && (
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="text-center py-12">
              <Star className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No reviews yet. Be the first to review this plugin!</p>
              <Button className="mt-4">Write a Review</Button>
            </CardContent>
          </Card>
        )}

        {activeTab === "manifest" && (
          <PluginManifestViewer
            manifest={plugin?.manifest || plugin}
            pluginName={plugin.display_name}
          />
        )}
      </div>
    </div>
  );
}
