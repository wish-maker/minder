"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Settings, CheckCircle2, XCircle, Power, PowerOff, Zap, Trash2, Loader2 } from "lucide-react";
import { Plugin } from "@/lib/types/plugin";
import { pluginsManagementApi } from "@/lib/api/plugins-management";
import PluginConfigModal from "@/components/modals/PluginConfigModal";
import PluginLifecycleManager from "@/components/marketplace/PluginLifecycleManager";

interface InstalledPluginCardProps {
  plugin: Plugin;
}

export default function InstalledPluginCard({ plugin }: InstalledPluginCardProps) {
  const queryClient = useQueryClient();
  const [showConfig, setShowConfig] = useState(false);

  const tierColors = {
    community: "bg-green-500/20 text-green-400 border-green-500/50",
    professional: "bg-blue-500/20 text-blue-400 border-blue-500/50",
    enterprise: "bg-purple-500/20 text-purple-400 border-purple-500/50",
  };

  return (
    <>
      <Card className="border-border bg-card/50 backdrop-blur hover:border-primary/50 transition-colors">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <CardTitle className="text-lg">{plugin.display_name}</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">by {plugin.author}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge className={tierColors[plugin.base_tier]}>{plugin.base_tier}</Badge>
              {plugin.is_enabled ? (
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

        <CardContent>
          <p className="text-sm text-muted-foreground mb-4 line-clamp-2">{plugin.description}</p>

          {/* Stats */}
          <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
            <div className="flex items-center gap-1">
              <Settings className="h-4 w-4" />
              <span>v{plugin.current_version}</span>
            </div>
          </div>

          {/* Tags */}
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="text-xs">
              {plugin.distribution_type}
            </Badge>
            <Badge variant="outline" className="text-xs">
              {plugin.pricing_model}
            </Badge>
          </div>
        </CardContent>

        <CardFooter className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            disabled={isMutating || !plugin.is_enabled}
            onClick={() => setShowConfig(true)}
          >
            <Settings className="h-4 w-4 mr-1" />
            Configure
          </Button>

          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            disabled={isMutating || !plugin.is_enabled}
            onClick={() => window.location.href = `/dashboard/plugins/${plugin.id}/ai-tools`}
          >
            <Zap className="h-4 w-4 mr-1" />
            AI Tools
          </Button>

          <PluginLifecycleManager
            plugin={plugin}
            onActionComplete={() => {
              setShowConfig(false);
            }}
          />
        </CardFooter>
      </Card>

      {/* Configuration Modal */}
      {showConfig && (
        <PluginConfigModal
          plugin={plugin}
          isOpen={showConfig}
          onClose={() => setShowConfig(false)}
          onSuccess={() => {
            setShowConfig(false);
          }}
        />
      )}
    </>
  );
}
