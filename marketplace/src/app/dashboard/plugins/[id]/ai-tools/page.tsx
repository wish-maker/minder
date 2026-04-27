"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Zap,
  Power,
  PowerOff,
  Settings,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  Shield,
  Code,
} from "lucide-react";
import { aiToolsApi, pluginsApi } from "@/lib/api";
import { AITool, Plugin } from "@/lib/types/plugin";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import TierEnforcementBadge from "@/components/marketplace/TierEnforcementBadge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function PluginAIToolsPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const pluginId = params.id as string;

  const [selectedTool, setSelectedTool] = useState<AITool | null>(null);
  const [dialogState, setDialogState] = useState<{
    isOpen: boolean;
    action: "enable" | "disable" | null;
    toolName: string;
    state: "confirming" | "processing" | "complete";
  }>({
    isOpen: false,
    action: null,
    toolName: "",
    state: "confirming",
  });

  // Fetch plugin details
  const { data: plugin, isLoading: pluginLoading } = useQuery({
    queryKey: ["plugin", pluginId],
    queryFn: () => pluginsApi.getPlugin(pluginId),
    enabled: !!pluginId,
  });

  // Fetch AI tools for this plugin
  const { data: aiToolsData, isLoading: toolsLoading, refetch } = useQuery({
    queryKey: ["plugin-ai-tools", pluginId],
    queryFn: () => aiToolsApi.getPluginAITools(pluginId),
    enabled: !!pluginId,
  });

  const aiTools = aiToolsData?.tools || [];

  // Enable tool mutation
  const enableMutation = useMutation({
    mutationFn: async (toolId: string) => {
      return aiToolsApi.enableAITool(toolId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plugin-ai-tools", pluginId] });
      queryClient.invalidateQueries({ queryKey: ["ai-tools"] });
      setDialogState((prev) => ({ ...prev, state: "complete" }));
      setTimeout(() => {
        setDialogState({ isOpen: false, action: null, toolName: "", state: "confirming" });
      }, 1500);
    },
  });

  // Disable tool mutation
  const disableMutation = useMutation({
    mutationFn: async (toolId: string) => {
      return aiToolsApi.disableAITool(toolId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plugin-ai-tools", pluginId] });
      queryClient.invalidateQueries({ queryKey: ["ai-tools"] });
      setDialogState((prev) => ({ ...prev, state: "complete" }));
      setTimeout(() => {
        setDialogState({ isOpen: false, action: null, toolName: "", state: "confirming" });
      }, 1500);
    },
  });

  if (pluginLoading || toolsLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading plugin AI tools...</p>
        </div>
      </div>
    );
  }

  if (!plugin) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-destructive text-lg">Plugin not found</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/dashboard")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  const handleToolAction = (tool: AITool, action: "enable" | "disable") => {
    setSelectedTool(tool);
    setDialogState({
      isOpen: true,
      action,
      toolName: tool.tool_name,
      state: "confirming",
    });
  };

  const handleConfirm = () => {
    if (!selectedTool) return;

    setDialogState((prev) => ({ ...prev, state: "processing" }));

    if (dialogState.action === "enable") {
      enableMutation.mutate(selectedTool.id);
    } else {
      disableMutation.mutate(selectedTool.id);
    }
  };

  const handleCancel = () => {
    setDialogState({ isOpen: false, action: null, toolName: "", state: "confirming" });
    setSelectedTool(null);
  };

  const stats = {
    total: aiTools.length,
    enabled: aiTools.filter((t) => t.is_enabled).length,
    disabled: aiTools.filter((t) => !t.is_enabled).length,
    community: aiTools.filter((t) => t.required_tier === "community").length,
    professional: aiTools.filter((t) => t.required_tier === "professional").length,
    enterprise: aiTools.filter((t) => t.required_tier === "enterprise").length,
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button
            variant="ghost"
            className="mb-4"
            onClick={() => router.push("/dashboard")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Dashboard
          </Button>

          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <Zap className="h-8 w-8 text-primary" />
                AI Tools Management
              </h1>
              <p className="text-muted-foreground mt-1">
                Manage AI tools for {plugin.display_name}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="border-b border-border bg-card/30">
        <div className="container mx-auto px-4 py-6">
          <div className="grid md:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-3xl font-bold">{stats.total}</p>
              <p className="text-sm text-muted-foreground">Total Tools</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-green-400">{stats.enabled}</p>
              <p className="text-sm text-muted-foreground">Enabled</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-muted-foreground">{stats.disabled}</p>
              <p className="text-sm text-muted-foreground">Disabled</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-blue-400">
                {stats.professional + stats.enterprise}
              </p>
              <p className="text-sm text-muted-foreground">Premium Tools</p>
            </div>
          </div>
        </div>
      </div>

      {/* AI Tools List */}
      <div className="container mx-auto px-4 py-8">
        {aiTools.length === 0 ? (
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="text-center py-12">
              <Zap className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">
                This plugin does not provide any AI tools.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {aiTools.map((tool) => (
              <Card
                key={tool.id}
                className={`border-border bg-card/50 backdrop-blur transition-all ${
                  !tool.is_enabled ? "opacity-75" : ""
                }`}
              >
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{tool.tool_name}</CardTitle>
                      <p className="text-sm text-muted-foreground mt-1">
                        {tool.description}
                      </p>
                    </div>
                    <div className="flex flex-col gap-2">
                      <TierEnforcementBadge
                        currentTier="community"
                        requiredTier={tool.required_tier}
                        featureName={tool.tool_name}
                        description={`Requires ${tool.required_tier} tier`}
                        showUpgradePrompt={false}
                      />
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
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
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
                      <code className="text-xs bg-muted px-2 py-1 rounded truncate">
                        {tool.endpoint}
                      </code>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1"
                      disabled={!tool.is_enabled}
                      onClick={() =>
                        (window.location.href = `/dashboard/plugins/${plugin.id}/tools/${tool.id}`)
                      }
                    >
                      <Code className="h-4 w-4 mr-1" />
                      Test
                    </Button>
                    <Button
                      size="sm"
                      variant={tool.is_enabled ? "destructive" : "default"}
                      className="flex-1"
                      onClick={() =>
                        handleToolAction(
                          tool,
                          tool.is_enabled ? "disable" : "enable"
                        )
                      }
                    >
                      {tool.is_enabled ? (
                        <>
                          <PowerOff className="h-4 w-4 mr-1" />
                          Disable
                        </>
                      ) : (
                        <>
                          <Power className="h-4 w-4 mr-1" />
                          Enable
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Confirmation Dialog */}
      <Dialog open={dialogState.isOpen} onOpenChange={handleCancel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {dialogState.action === "enable" ? "Enable" : "Disable"} AI Tool
            </DialogTitle>
            <DialogDescription>
              {dialogState.action === "enable"
                ? "This will make the AI tool available for use."
                : "This will disable the AI tool and it will no longer be available."}
            </DialogDescription>
          </DialogHeader>

          {dialogState.state === "confirming" && selectedTool && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="font-medium">{selectedTool.tool_name}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {selectedTool.description}
                </p>
              </div>

              {dialogState.action === "disable" && (
                <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/50">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-yellow-400">
                        Tool Dependency Warning
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Other plugins or workflows may depend on this tool. Disabling it may affect their functionality.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <DialogFooter>
                <Button variant="outline" onClick={handleCancel}>
                  Cancel
                </Button>
                <Button
                  variant={dialogState.action === "enable" ? "default" : "destructive"}
                  onClick={handleConfirm}
                  disabled={
                    dialogState.state === "processing" ||
                    enableMutation.isPending ||
                    disableMutation.isPending
                  }
                >
                  {(dialogState.state === "processing" ||
                    enableMutation.isPending ||
                    disableMutation.isPending) && (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  )}
                  {dialogState.action === "enable" ? "Enable Tool" : "Disable Tool"}
                </Button>
              </DialogFooter>
            </div>
          )}

          {dialogState.state === "processing" && (
            <div className="py-8 text-center">
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-3 text-primary" />
              <p className="text-sm text-muted-foreground">
                {dialogState.action === "enable" ? "Enabling..." : "Disabling..."} tool
              </p>
            </div>
          )}

          {dialogState.state === "complete" && (
            <div className="py-8 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-400 mx-auto mb-3" />
              <p className="font-medium mb-1">Success!</p>
              <p className="text-sm text-muted-foreground">
                The AI tool has been{" "}
                {dialogState.action === "enable" ? "enabled" : "disabled"} successfully.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
