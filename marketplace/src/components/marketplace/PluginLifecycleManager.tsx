"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Power,
  PowerOff,
  Trash2,
  Settings,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Zap,
} from "lucide-react";
import { pluginsApi, pluginsManagementApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";

interface PluginLifecycleManagerProps {
  plugin: any;
  onActionComplete?: () => void;
}

type ActionType = "enable" | "disable" | "uninstall";
type ConfirmationState = "idle" | "confirming" | "processing" | "complete";

export default function PluginLifecycleManager({
  plugin,
  onActionComplete,
}: PluginLifecycleManagerProps) {
  const queryClient = useQueryClient();
  const [dialogState, setDialogState] = useState<{
    isOpen: boolean;
    action: ActionType | null;
    state: ConfirmationState;
  }>({
    isOpen: false,
    action: null,
    state: "idle",
  });

  const [cascadeInfo, setCascadeInfo] = useState<{
    aiToolsCount: number;
    affectedTools: string[];
  } | null>(null);

  // Enable plugin mutation
  const enableMutation = useMutation({
    mutationFn: async (pluginId: string) => {
      return pluginsManagementApi.enablePlugin(pluginId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plugin', plugin.id] });
      queryClient.invalidateQueries({ queryKey: ['installed-plugins'] });
      queryClient.invalidateQueries({ queryKey: ['ai-tools'] });
      setDialogState((prev) => ({ ...prev, state: "complete" }));
      setTimeout(() => {
        setDialogState({ isOpen: false, action: null, state: "idle" });
        onActionComplete?.();
      }, 1500);
    },
    onError: (error: any) => {
      console.error("Enable error:", error);
      setDialogState((prev) => ({ ...prev, state: "idle" }));
    },
  });

  // Disable plugin mutation
  const disableMutation = useMutation({
    mutationFn: async (pluginId: string) => {
      return pluginsManagementApi.disablePlugin(pluginId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plugin', plugin.id] });
      queryClient.invalidateQueries({ queryKey: ['installed-plugins'] });
      queryClient.invalidateQueries({ queryKey: ['ai-tools'] });
      setDialogState((prev) => ({ ...prev, state: "complete" }));
      setTimeout(() => {
        setDialogState({ isOpen: false, action: null, state: "idle" });
        onActionComplete?.();
      }, 1500);
    },
    onError: (error: any) => {
      console.error("Disable error:", error);
      setDialogState((prev) => ({ ...prev, state: "idle" }));
    },
  });

  // Uninstall plugin mutation
  const uninstallMutation = useMutation({
    mutationFn: async (pluginId: string) => {
      return pluginsApi.uninstallPlugin(pluginId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plugin', plugin.id] });
      queryClient.invalidateQueries({ queryKey: ['installed-plugins'] });
      queryClient.invalidateQueries({ queryKey: ['ai-tools'] });
      setDialogState((prev) => ({ ...prev, state: "complete" }));
      setTimeout(() => {
        setDialogState({ isOpen: false, action: null, state: "idle" });
        onActionComplete?.();
      }, 1500);
    },
    onError: (error: any) => {
      console.error("Uninstall error:", error);
      setDialogState((prev) => ({ ...prev, state: "idle" }));
    },
  });

  const handleAction = (action: ActionType) => {
    // Get AI tools info for cascade effect
    const aiToolsCount = plugin.ai_tools_count || plugin.ai_tools?.length || 0;
    const affectedTools = plugin.ai_tools
      ?.filter((tool: any) => tool.is_enabled)
      .map((tool: any) => tool.tool_name) || [];

    setCascadeInfo({
      aiToolsCount,
      affectedTools,
    });

    setDialogState({
      isOpen: true,
      action,
      state: "confirming",
    });
  };

  const handleConfirm = () => {
    setDialogState((prev) => ({ ...prev, state: "processing" }));

    if (dialogState.action === "enable") {
      enableMutation.mutate(plugin.id);
    } else if (dialogState.action === "disable") {
      disableMutation.mutate(plugin.id);
    } else if (dialogState.action === "uninstall") {
      uninstallMutation.mutate(plugin.id);
    }
  };

  const handleCancel = () => {
    setDialogState({ isOpen: false, action: null, state: "idle" });
    setCascadeInfo(null);
  };

  const getActionInfo = (action: ActionType) => {
    switch (action) {
      case "enable":
        return {
          title: "Enable Plugin",
          description: "This will activate the plugin and all its AI tools.",
          icon: Power,
          iconColor: "text-green-400",
          buttonVariant: "default" as const,
          buttonText: "Enable Plugin",
        };
      case "disable":
        return {
          title: "Disable Plugin",
          description: "This will deactivate the plugin and all its AI tools.",
          icon: PowerOff,
          iconColor: "text-yellow-400",
          buttonVariant: "secondary" as const,
          buttonText: "Disable Plugin",
        };
      case "uninstall":
        return {
          title: "Uninstall Plugin",
          description: "This will remove the plugin and all its data from your system.",
          icon: Trash2,
          iconColor: "text-destructive",
          buttonVariant: "destructive" as const,
          buttonText: "Uninstall Plugin",
        };
    }
  };

  const actionInfo = dialogState.action ? getActionInfo(dialogState.action) : null;
  const ActionIcon = actionInfo?.icon;
  const isLoading =
    dialogState.state === "processing" ||
    enableMutation.isPending ||
    disableMutation.isPending ||
    uninstallMutation.isPending;

  return (
    <>
      <div className="flex gap-2">
        {plugin.is_enabled ? (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAction("disable")}
              disabled={!plugin.can_be_disabled}
            >
              <PowerOff className="h-4 w-4 mr-1" />
              Disable
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAction("uninstall")}
            >
              <Trash2 className="h-4 w-4 mr-1" />
              Uninstall
            </Button>
          </>
        ) : (
          <Button variant="default" size="sm" onClick={() => handleAction("enable")}>
            <Power className="h-4 w-4 mr-1" />
            Enable Plugin
          </Button>
        )}
      </div>

      {/* Confirmation Dialog */}
      <Dialog open={dialogState.isOpen} onOpenChange={handleCancel}>
        <DialogContent>
          <DialogHeader>
            {actionInfo && (
              <>
                <DialogTitle className="flex items-center gap-2">
                  <div className={`p-2 rounded-lg bg-muted ${actionInfo.iconColor}`}>
                    <ActionIcon className="h-5 w-5" />
                  </div>
                  {actionInfo.title}
                </DialogTitle>
                <DialogDescription>{actionInfo.description}</DialogDescription>
              </>
            )}
          </DialogHeader>

          {dialogState.state === "confirming" && (
            <div className="space-y-4">
              {/* Plugin Info */}
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="font-medium">{plugin.display_name}</p>
                <p className="text-sm text-muted-foreground mt-1">{plugin.description}</p>
              </div>

              {/* Cascade Effect Warning */}
              {cascadeInfo && cascadeInfo.aiToolsCount > 0 && (
                <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/50">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-yellow-400">
                        AI Tools Impact
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        This action will affect {cascadeInfo.aiToolsCount} AI tool
                        {cascadeInfo.aiToolsCount !== 1 ? "s" : ""} provided by this plugin.
                      </p>
                      {cascadeInfo.affectedTools.length > 0 && (
                        <div className="mt-2">
                          <p className="text-xs font-medium mb-1">Affected tools:</p>
                          <div className="flex flex-wrap gap-1">
                            {cascadeInfo.affectedTools.map((tool) => (
                              <Badge key={tool} variant="outline" className="text-xs">
                                <Zap className="h-3 w-3 mr-1" />
                                {tool}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Additional Warning for Uninstall */}
              {dialogState.action === "uninstall" && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/50">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-destructive">
                        Warning: Irreversible Action
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Uninstalling will remove all plugin data and configurations. This action cannot be undone.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <DialogFooter>
                <Button variant="outline" onClick={handleCancel} disabled={isLoading}>
                  Cancel
                </Button>
                <Button
                  variant={actionInfo?.buttonVariant}
                  onClick={handleConfirm}
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    actionInfo?.buttonText
                  )}
                </Button>
              </DialogFooter>
            </div>
          )}

          {dialogState.state === "processing" && (
            <div className="py-8 text-center">
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-3 text-primary" />
              <p className="text-sm text-muted-foreground">
                {dialogState.action === "enable" && "Enabling plugin and AI tools..."}
                {dialogState.action === "disable" && "Disabling plugin and AI tools..."}
                {dialogState.action === "uninstall" && "Uninstalling plugin..."}
              </p>
            </div>
          )}

          {dialogState.state === "complete" && (
            <div className="py-8 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-400 mx-auto mb-3" />
              <p className="font-medium mb-1">Action Complete!</p>
              <p className="text-sm text-muted-foreground">
                {dialogState.action === "enable" &&
                  `${plugin.display_name} has been enabled with all its AI tools.`}
                {dialogState.action === "disable" &&
                  `${plugin.display_name} has been disabled with all its AI tools.`}
                {dialogState.action === "uninstall" &&
                  `${plugin.display_name} has been uninstalled from your system.`}
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
