"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  TrendingDown,
  Download,
  Star,
  Activity,
  Calendar,
  BarChart3,
  PieChart,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface AnalyticsData {
  totalDownloads: number;
  activeInstallations: number;
  averageRating: number;
  totalReviews: number;
  trend: {
    period: string;
    change: number;
    direction: "up" | "down";
  };
  topPlugins: Array<{
    id: string;
    name: string;
    downloads: number;
    rating: number;
    change: number;
  }>;
  categoryBreakdown: Array<{
    category: string;
    count: number;
    percentage: number;
  }>;
  recentActivity: Array<{
    id: string;
    type: "install" | "uninstall" | "review";
    pluginName: string;
    user: string;
    timestamp: string;
  }>;
}

interface PluginAnalyticsProps {
  timeframe?: "7d" | "30d" | "90d";
  pluginId?: string;
  adminView?: boolean;
}

export default function PluginAnalytics({
  timeframe = "30d",
  pluginId,
  adminView = false,
}: PluginAnalyticsProps) {
  const [selectedTimeframe, setSelectedTimeframe] = useState(timeframe);

  // Mock data - replace with actual API call
  const { data: analytics, isLoading } = useQuery<AnalyticsData>({
    queryKey: ["analytics", selectedTimeframe, pluginId],
    queryFn: async () => ({
      totalDownloads: 12458,
      activeInstallations: 3421,
      averageRating: 4.5,
      totalReviews: 823,
      trend: {
        period: selectedTimeframe,
        change: 12.5,
        direction: "up",
      },
      topPlugins: [
        { id: "1", name: "AI Assistant", downloads: 3421, rating: 4.8, change: 15.3 },
        { id: "2", name: "Code Review", downloads: 2156, rating: 4.6, change: 8.7 },
        { id: "3", name: "Documentation", downloads: 1892, rating: 4.4, change: -2.1 },
        { id: "4", name: "Testing Tools", downloads: 1543, rating: 4.7, change: 5.4 },
        { id: "5", name: "CI/CD", downloads: 1234, rating: 4.5, change: 3.2 },
      ],
      categoryBreakdown: [
        { category: "AI Tools", count: 15, percentage: 35 },
        { category: "Development", count: 12, percentage: 28 },
        { category: "Analytics", count: 8, percentage: 19 },
        { category: "Productivity", count: 8, percentage: 18 },
      ],
      recentActivity: [
        { id: "1", type: "install", pluginName: "AI Assistant", user: "john.doe", timestamp: "2 hours ago" },
        { id: "2", type: "review", pluginName: "Code Review", user: "jane.smith", timestamp: "4 hours ago" },
        { id: "3", type: "install", pluginName: "Testing Tools", user: "bob.wilson", timestamp: "6 hours ago" },
        { id: "4", type: "uninstall", pluginName: "Documentation", user: "alice.brown", timestamp: "8 hours ago" },
        { id: "5", type: "install", pluginName: "CI/CD", user: "charlie.davis", timestamp: "12 hours ago" },
      ],
    }),
  });

  if (isLoading) {
    return (
      <div className="grid gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="animate-pulse">
                <div className="h-4 bg-muted rounded w-1/3 mb-2"></div>
                <div className="h-8 bg-muted rounded w-1/2"></div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!analytics) return null;

  const StatCard = ({
    title,
    value,
    icon: Icon,
    trend,
    color,
  }: {
    title: string;
    value: string | number;
    icon: any;
    trend?: { change: number; direction: "up" | "down" };
    color?: string;
  }) => (
    <Card className="border-border bg-card/50 backdrop-blur">
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
            {trend && (
              <div className="flex items-center gap-1 mt-2">
                {trend.direction === "up" ? (
                  <TrendingUp className="h-4 w-4 text-green-400" />
                ) : (
                  <TrendingDown className="h-4 w-4 text-red-400" />
                )}
                <span
                  className={`text-sm font-medium ${
                    trend.direction === "up" ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {trend.change > 0 ? "+" : ""}
                  {trend.change}%
                </span>
                <span className="text-xs text-muted-foreground ml-1">
                  vs last {analytics.trend.period}
                </span>
              </div>
            )}
          </div>
          <div className={`p-3 rounded-lg ${color || "bg-primary/20"}`}>
            <Icon className={`h-6 w-6 ${color ? "" : "text-primary"}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Analytics</h2>
          <p className="text-muted-foreground">
            Track your plugin performance and usage
          </p>
        </div>
        <div className="flex gap-2">
          {["7d", "30d", "90d"].map((tf) => (
            <Button
              key={tf}
              variant={selectedTimeframe === tf ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedTimeframe(tf as any)}
            >
              {tf === "7d" ? "7 Days" : tf === "30d" ? "30 Days" : "90 Days"}
            </Button>
          ))}
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid md:grid-cols-4 gap-4">
        <StatCard
          title="Total Downloads"
          value={analytics.totalDownloads.toLocaleString()}
          icon={Download}
          trend={analytics.trend}
        />
        <StatCard
          title="Active Installations"
          value={analytics.activeInstallations.toLocaleString()}
          icon={Activity}
          trend={analytics.trend}
          color="bg-green-500/20"
        />
        <StatCard
          title="Average Rating"
          value={analytics.averageRating.toFixed(1)}
          icon={Star}
          trend={analytics.trend}
          color="bg-yellow-500/20"
        />
        <StatCard
          title="Total Reviews"
          value={analytics.totalReviews.toLocaleString()}
          icon={BarChart3}
          trend={analytics.trend}
          color="bg-blue-500/20"
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Top Plugins */}
        <Card className="border-border bg-card/50 backdrop-blur">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Top Performing Plugins
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {analytics.topPlugins.map((plugin, index) => (
                <div
                  key={plugin.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/20 text-primary font-semibold text-sm">
                      {index + 1}
                    </div>
                    <div>
                      <p className="font-medium">{plugin.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {plugin.downloads.toLocaleString()} downloads
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="flex items-center gap-1">
                      <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                      <span className="font-medium">{plugin.rating}</span>
                    </div>
                    <div
                      className={`flex items-center gap-1 text-xs ${
                        plugin.change >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {plugin.change >= 0 ? (
                        <TrendingUp className="h-3 w-3" />
                      ) : (
                        <TrendingDown className="h-3 w-3" />
                      )}
                      {plugin.change > 0 ? "+" : ""}
                      {plugin.change}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Category Breakdown */}
        <Card className="border-border bg-card/50 backdrop-blur">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PieChart className="h-5 w-5" />
              Plugins by Category
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {analytics.categoryBreakdown.map((category) => (
                <div key={category.category}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium">{category.category}</span>
                    <span className="text-sm text-muted-foreground">
                      {category.count} plugins ({category.percentage}%)
                    </span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div
                      className="bg-primary h-2 rounded-full transition-all"
                      style={{ width: `${category.percentage}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity */}
      {adminView && (
        <Card className="border-border bg-card/50 backdrop-blur">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {analytics.recentActivity.map((activity) => (
                <div
                  key={activity.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <Badge
                      variant={
                        activity.type === "install"
                          ? "default"
                          : activity.type === "review"
                          ? "secondary"
                          : "outline"
                      }
                      className="capitalize"
                    >
                      {activity.type}
                    </Badge>
                    <div>
                      <p className="font-medium">{activity.pluginName}</p>
                      <p className="text-xs text-muted-foreground">
                        by {activity.user}
                      </p>
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {activity.timestamp}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
