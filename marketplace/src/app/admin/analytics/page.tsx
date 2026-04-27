"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  Users,
  Download,
  DollarSign,
  Calendar,
  BarChart3,
  PieChart,
  Activity,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function AdminAnalyticsPage() {
  const [timeRange, setTimeRange] = useState<"7d" | "30d" | "90d" | "1y">("30d");

  // Fetch analytics data
  const { data: analytics, isLoading } = useQuery({
    queryKey: ["admin-analytics", timeRange],
    queryFn: async () => {
      // Mock implementation - replace with actual API call
      return {
        overview: {
          totalRevenue: 125000,
          revenueChange: 15.3,
          totalUsers: 8540,
          userChange: 8.2,
          totalDownloads: 45600,
          downloadChange: 23.1,
          activePlugins: 156,
          pluginChange: 12.0,
        },
        installationTrends: [
          { date: "2024-01-01", installations: 120, uninstallations: 5 },
          { date: "2024-01-02", installations: 145, uninstallations: 8 },
          { date: "2024-01-03", installations: 132, uninstallations: 3 },
          { date: "2024-01-04", installations: 167, uninstallations: 12 },
          { date: "2024-01-05", installations: 189, uninstallations: 6 },
          { date: "2024-01-06", installations: 201, uninstallations: 9 },
          { date: "2024-01-07", installations: 178, uninstallations: 7 },
        ],
        popularPlugins: [
          { name: "AI Assistant", downloads: 12500, rating: 4.8, tier: "professional" },
          { name: "Code Analyzer", downloads: 9800, rating: 4.6, tier: "community" },
          { name: "Data Pipeline", downloads: 8900, rating: 4.7, tier: "enterprise" },
          { name: "Security Scanner", downloads: 7600, rating: 4.5, tier: "professional" },
          { name: "Test Generator", downloads: 6500, rating: 4.4, tier: "community" },
        ],
        tierDistribution: {
          community: 45,
          professional: 35,
          enterprise: 20,
        },
        revenueByTier: {
          community: 15000,
          professional: 45000,
          enterprise: 65000,
        },
        topCategories: [
          { name: "AI & Machine Learning", count: 42, installations: 15000 },
          { name: "Developer Tools", count: 38, installations: 12000 },
          { name: "Security", count: 25, installations: 8500 },
          { name: "Data Processing", count: 21, installations: 6200 },
          { name: "Monitoring", count: 18, installations: 4900 },
        ],
      };
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading analytics...</p>
        </div>
      </div>
    );
  }

  const overviewCards = [
    {
      title: "Total Revenue",
      value: `$${analytics?.overview.totalRevenue.toLocaleString()}`,
      change: `+${analytics?.overview.revenueChange}%`,
      icon: DollarSign,
      color: "text-green-400",
      bgColor: "bg-green-500/20",
    },
    {
      title: "Total Users",
      value: analytics?.overview.totalUsers.toLocaleString(),
      change: `+${analytics?.overview.userChange}%`,
      icon: Users,
      color: "text-blue-400",
      bgColor: "bg-blue-500/20",
    },
    {
      title: "Total Downloads",
      value: analytics?.overview.totalDownloads.toLocaleString(),
      change: `+${analytics?.overview.downloadChange}%`,
      icon: Download,
      color: "text-purple-400",
      bgColor: "bg-purple-500/20",
    },
    {
      title: "Active Plugins",
      value: analytics?.overview.activePlugins,
      change: `+${analytics?.overview.pluginChange}%`,
      icon: Activity,
      color: "text-yellow-400",
      bgColor: "bg-yellow-500/20",
    },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">Analytics Dashboard</h1>
              <p className="text-muted-foreground">
                Platform performance and user engagement metrics
              </p>
            </div>
            <div className="flex gap-2">
              {(["7d", "30d", "90d", "1y"] as const).map((range) => (
                <Button
                  key={range}
                  variant={timeRange === range ? "default" : "outline"}
                  size="sm"
                  onClick={() => setTimeRange(range)}
                >
                  {range === "7d" && "7 Days"}
                  {range === "30d" && "30 Days"}
                  {range === "90d" && "90 Days"}
                  {range === "1y" && "1 Year"}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        {/* Overview Stats */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          {overviewCards.map((card) => {
            const Icon = card.icon;
            return (
              <Card key={card.title} className="border-border bg-card/50 backdrop-blur">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">{card.title}</p>
                      <p className="text-3xl font-bold mt-1">{card.value}</p>
                      <p className="text-xs text-green-400 mt-2">{card.change} from last period</p>
                    </div>
                    <div className={`h-12 w-12 rounded-full ${card.bgColor} flex items-center justify-center`}>
                      <Icon className={`h-6 w-6 ${card.color}`} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Charts Row */}
        <div className="grid lg:grid-cols-2 gap-6 mb-8">
          {/* Installation Trends */}
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Installation Trends</CardTitle>
                <BarChart3 className="h-5 w-5 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {analytics?.installationTrends.map((trend) => (
                  <div key={trend.date} className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{trend.date}</span>
                      <span className="font-medium">
                        {trend.installations} installed / {trend.uninstallations} uninstalled
                      </span>
                    </div>
                    <div className="flex gap-1">
                      <div
                        className="h-2 bg-green-500 rounded-full"
                        style={{ width: `${(trend.installations / 250) * 100}%` }}
                      />
                      <div
                        className="h-2 bg-red-500 rounded-full"
                        style={{ width: `${(trend.uninstallations / 250) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Tier Distribution */}
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Revenue by Tier</CardTitle>
                <PieChart className="h-5 w-5 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {analytics && Object.entries(analytics.revenueByTier).map(([tier, revenue]) => {
                  const total = Object.values(analytics.revenueByTier).reduce((a, b) => a + b, 0);
                  const percentage = ((revenue / total) * 100).toFixed(1);
                  const colors = {
                    community: "bg-green-500",
                    professional: "bg-blue-500",
                    enterprise: "bg-purple-500",
                  };
                  return (
                    <div key={tier} className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="capitalize font-medium">{tier}</span>
                        <span>${revenue.toLocaleString()} ({percentage}%)</span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full ${colors[tier as keyof typeof colors]} rounded-full`}
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Popular Plugins */}
        <Card className="border-border bg-card/50 backdrop-blur mb-8">
          <CardHeader>
            <CardTitle>Most Popular Plugins</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {analytics?.popularPlugins.map((plugin, index) => (
                <div key={plugin.name} className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-4">
                    <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center font-bold text-primary">
                      {index + 1}
                    </div>
                    <div>
                      <p className="font-medium">{plugin.name}</p>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs capitalize">
                          {plugin.tier}
                        </Badge>
                        <span className="text-xs text-muted-foreground">★ {plugin.rating}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold">{plugin.downloads.toLocaleString()}</p>
                    <p className="text-xs text-muted-foreground">downloads</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Top Categories */}
        <Card className="border-border bg-card/50 backdrop-blur">
          <CardHeader>
            <CardTitle>Top Categories</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-5 gap-4">
              {analytics?.topCategories.map((category) => (
                <div key={category.name} className="p-4 rounded-lg bg-muted/50 text-center">
                  <p className="text-2xl font-bold">{category.count}</p>
                  <p className="text-sm text-muted-foreground mt-1">{category.name}</p>
                  <p className="text-xs text-muted-foreground mt-2">{category.installations.toLocaleString()} installs</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
