"use client";

import { Plugin } from "@/lib/types/plugin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CheckCircle2,
  XCircle,
  Settings,
  Trash2,
  Power,
  Zap,
} from "lucide-react";
import PluginLifecycleManager from "./PluginLifecycleManager";
import { useState } from "react";

interface PluginListItemProps {
  plugin: Plugin;
}

export default function PluginListItem({ plugin }: PluginListItemProps) {
  const [showLifecycleManager, setShowLifecycleManager] = useState(false);

  const tierColors = {
    community: "bg-green-500/20 text-green-400 border-green-500/50",
    professional: "bg-blue-500/20 text-blue-400 border-blue-500/50",
    enterprise: "bg-purple-500/20 text-purple-400 border-purple-500/50",
  };

  return (
    <div className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0">
            {plugin.logo_url ? (
              <img
                src={plugin.logo_url}
                alt={plugin.display_name}
                className="w-12 h-12 rounded-lg object-cover"
              />
            ) : (
              <div className="w-12 h-12 rounded-lg bg-primary/20 flex items-center justify-center">
                <Zap className="h-6 w-6 text-primary" />
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold truncate">
                {plugin.display_name}
              </h3>
              <Badge className={tierColors[plugin.base_tier]}>
                {plugin.base_tier}
              </Badge>
              {plugin.is_enabled ? (
                <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  Enabled
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-destructive/20">
                  <XCircle className="h-3 w-3 mr-1" />
                  Disabled
                </Badge>
              )}
            </div>

            <p className="text-sm text-muted-foreground truncate mt-1">
              {plugin.description}
            </p>

            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
              <span>Version {plugin.current_version}</span>
              <span>by {plugin.author}</span>
              {plugin.ai_tools_count !== undefined && plugin.ai_tools_count > 0 && (
                <span className="flex items-center gap-1">
                  <Zap className="h-3 w-3" />
                  {plugin.ai_tools_count} AI Tools
                </span>
              )}
              <span>{plugin.download_count} downloads</span>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0 ml-4">
        <Button
          size="sm"
          variant="outline"
          onClick={() => (window.location.href = `/dashboard/plugins/${plugin.id}`)}
        >
          <Settings className="h-4 w-4 mr-2" />
          Manage
        </Button>

        <Button
          size="sm"
          variant={plugin.is_enabled ? "destructive" : "default"}
          onClick={() => setShowLifecycleManager(true)}
        >
          <Power className="h-4 w-4 mr-2" />
          {plugin.is_enabled ? "Disable" : "Enable"}
        </Button>
      </div>

      {showLifecycleManager && (
        <PluginLifecycleManager
          plugin={plugin}
          onActionComplete={() => {
            setShowLifecycleManager(false);
            window.location.reload();
          }}
          onClose={() => setShowLifecycleManager(false)}
        />
      )}
    </div>
  );
}
