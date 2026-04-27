"use client";

import { useQuery } from "@tanstack/react-query";
import { Shield, Star, Zap, CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { defaultPluginsApi } from "@/lib/api/default-plugins";

interface DefaultPluginsSectionProps {
  userTier: "community" | "professional" | "enterprise";
}

export default function DefaultPluginsSection({
  userTier,
}: DefaultPluginsSectionProps) {
  const { data: defaultPluginsData, isLoading } = useQuery({
    queryKey: ["default-plugins", userTier],
    queryFn: () => defaultPluginsApi.getDefaultPlugins(userTier),
  });

  const defaultPlugins = defaultPluginsData?.plugins || [];
  const autoEnabled = defaultPluginsData?.auto_enabled || [];
  const available = defaultPluginsData?.available || [];

  const tierColors = {
    community: "bg-green-500/20 text-green-400 border-green-500/50",
    professional: "bg-blue-500/20 text-blue-400 border-blue-500/50",
    enterprise: "bg-purple-500/20 text-purple-400 border-purple-500/50",
  };

  const tierInfo = {
    community: { name: "Community", icon: Shield },
    professional: { name: "Professional", icon: Star },
    enterprise: { name: "Enterprise", icon: Zap },
  };

  const TierIcon = tierInfo[userTier].icon;

  if (isLoading) {
    return (
      <Card className="border-border bg-card/50 backdrop-blur">
        <CardContent className="pt-6">
          <div className="animate-pulse space-y-3">
            <div className="h-4 bg-muted rounded w-1/3"></div>
            <div className="h-20 bg-muted rounded"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-border bg-card/50 backdrop-blur">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <div className={`p-2 rounded-lg ${tierColors[userTier]}`}>
              <TierIcon className="h-5 w-5" />
            </div>
            Default Plugins for {tierInfo[userTier].name} Tier
          </CardTitle>
          <Badge className={tierColors[userTier]}>{userTier}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Essential plugins automatically available for your tier
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Auto-Enabled Plugins */}
        {autoEnabled.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-400" />
              Auto-Enabled ({autoEnabled.length})
            </h3>
            <div className="space-y-2">
              {autoEnabled.map((plugin) => (
                <div
                  key={plugin.pluginId}
                  className="flex items-center justify-between p-3 rounded-lg bg-green-500/10 border border-green-500/50"
                >
                  <div className="flex-1">
                    <p className="font-medium text-sm">{plugin.name}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {plugin.description}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {plugin.category}
                    </Badge>
                    <Badge className="bg-green-500/20 text-green-400 border-green-500/50 text-xs">
                      Enabled
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Available Plugins */}
        {available.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-3">
              Available to Install ({available.length})
            </h3>
            <div className="space-y-2">
              {available.map((plugin) => (
                <div
                  key={plugin.pluginId}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/30 border border-border hover:border-primary/50 transition-colors"
                >
                  <div className="flex-1">
                    <p className="font-medium text-sm">{plugin.name}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {plugin.description}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {plugin.category}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs"
                      onClick={() =>
                        (window.location.href = `/marketplace/plugins/${plugin.pluginId}`)
                      }
                    >
                      Install
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {autoEnabled.length === 0 && available.length === 0 && (
          <div className="text-center py-8">
            <Shield className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">
              No default plugins configured for {tierInfo[userTier].name} tier
            </p>
          </div>
        )}

        {/* Info */}
        <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/50">
          <p className="text-xs text-blue-400">
            <strong>Tip:</strong> Default plugins are automatically enabled based on your tier. You can disable or uninstall them from the Installed Plugins section.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
