"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Settings,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Download,
  TrendingUp,
  Zap,
  ArrowRight,
} from "lucide-react";
import { pluginsApi } from "@/lib/api/plugins";
import { Plugin } from "@/lib/types/plugin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import InstalledPluginCard from "@/components/dashboard/InstalledPluginCard";
import DefaultPluginsSection from "@/components/dashboard/DefaultPluginsSection";

export default function DashboardPage() {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [userTier, setUserTier] = useState<"community" | "professional" | "enterprise">("community");

  // Fetch installed plugins
  const { data: installedPlugins, isLoading, error } = useQuery({
    queryKey: ['installed-plugins'],
    queryFn: () => pluginsApi.listPlugins({ installed: true }),
  });

  const plugins = installedPlugins?.plugins || [];

  // Calculate stats
  const enabledCount = plugins.filter((p) => p.is_enabled).length;
  const totalCount = plugins.length;
  const communityPlugins = plugins.filter((p) => p.base_tier === "community").length;
  const professionalPlugins = plugins.filter((p) => p.base_tier === "professional").length;
  const enterprisePlugins = plugins.filter((p) => p.base_tier === "enterprise").length;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold">Dashboard</h1>
              <p className="text-muted-foreground">
                Manage your installed plugins and monitor their performance
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={() => (window.location.href = "/marketplace/plugins")}
              >
                <Download className="mr-2 h-4 w-4" />
                Browse Marketplace
              </Button>
            </div>
          </div>

          {/* View Toggle */}
          <div className="flex gap-2">
            <Button
              variant={viewMode === "grid" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("grid")}
            >
              Grid View
            </Button>
            <Button
              variant={viewMode === "list" ? "default" : "outline"}
              size="sm"
              onClick={() => setViewMode("list")}
            >
              List View
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        {/* Default Plugins Section */}
        <div className="mb-8">
          <DefaultPluginsSection userTier={userTier} />
        </div>

        {/* Stats Overview */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Plugins</p>
                  <p className="text-3xl font-bold mt-1">{totalCount}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center">
                  <Download className="h-6 w-6 text-primary" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Enabled</p>
                  <p className="text-3xl font-bold mt-1 text-green-400">{enabledCount}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-green-500/20 flex items-center justify-center">
                  <CheckCircle2 className="h-6 w-6 text-green-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Disabled</p>
                  <p className="text-3xl font-bold mt-1 text-muted-foreground">
                    {totalCount - enabledCount}
                  </p>
                </div>
                <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                  <XCircle className="h-6 w-6 text-muted-foreground" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">This Week</p>
                  <p className="text-3xl font-bold mt-1 text-blue-400">+{Math.floor(Math.random() * 5)}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-blue-500/20 flex items-center justify-center">
                  <TrendingUp className="h-6 w-6 text-blue-400" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Tier Distribution */}
        <div className="grid md:grid-cols-3 gap-4 mb-8">
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Community Tier</p>
                  <p className="text-2xl font-bold mt-1">{communityPlugins}</p>
                </div>
                <Badge className="bg-green-500/20 text-green-400 border-green-500/50">Free</Badge>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Professional Tier</p>
                  <p className="text-2xl font-bold mt-1">{professionalPlugins}</p>
                </div>
                <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/50">Pro</Badge>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Enterprise Tier</p>
                  <p className="text-2xl font-bold mt-1">{enterprisePlugins}</p>
                </div>
                <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/50">
                  Enterprise
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
            <p className="mt-4 text-muted-foreground">Loading installed plugins...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="text-center py-12">
            <p className="text-destructive">Failed to load plugins. Please try again.</p>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && plugins.length === 0 && (
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="text-center py-16">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-muted mb-4">
                <Download className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="text-xl font-semibold mb-2">No Plugins Installed</h3>
              <p className="text-muted-foreground mb-6">
                Get started by browsing the marketplace and installing your first plugin.
              </p>
              <Button>
                <Download className="mr-2 h-4 w-4" />
                Browse Marketplace
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Plugins Grid */}
        {!isLoading && !error && plugins.length > 0 && viewMode === "grid" && (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {plugins.map((plugin) => (
              <InstalledPluginCard key={plugin.id} plugin={plugin} />
            ))}
          </div>
        )}

        {/* Plugins List */}
        {!isLoading && !error && plugins.length > 0 && viewMode === "list" && (
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="p-0">
              <div className="divide-y divide-border">
                {plugins.map((plugin) => (
                  <PluginListItem key={plugin.id} plugin={plugin} />
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
