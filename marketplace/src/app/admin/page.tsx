"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Users,
  ShoppingBag,
  TrendingUp,
  Activity,
  DollarSign,
  CheckCircle2,
  Clock,
  XCircle,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function AdminDashboardPage() {
  // Fetch admin stats
  const { data: stats, isLoading } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: async () => {
      // Mock implementation - replace with actual API call
      return {
        totalPlugins: 156,
        totalUsers: 2450,
        activeInstallations: 8900,
        monthlyRevenue: 12500,
        pendingPlugins: 12,
        activePlugins: 142,
        reportedIssues: 5,
        systemHealth: "healthy",
      };
    },
  });

  // Recent activity
  const { data: recentActivity } = useQuery({
    queryKey: ["admin-activity"],
    queryFn: async () => {
      return [
        { id: 1, type: "plugin_submission", title: "New plugin submitted", time: "2 minutes ago", status: "pending" },
        { id: 2, type: "user_registration", title: "New user registered", time: "15 minutes ago", status: "completed" },
        { id: 3, type: "plugin_installation", title: "Plugin installed 50 times", time: "1 hour ago", status: "completed" },
        { id: 4, type: "reported_issue", title: "Plugin bug reported", time: "2 hours ago", status: "pending" },
        { id: 5, type: "plugin_update", title: "Plugin updated to v2.1", time: "3 hours ago", status: "completed" },
      ];
    },
  });

  const statCards = [
    {
      title: "Total Plugins",
      value: stats?.totalPlugins || 0,
      icon: ShoppingBag,
      color: "text-blue-400",
      bgColor: "bg-blue-500/20",
      trend: "+12%",
      trendUp: true,
    },
    {
      title: "Total Users",
      value: stats?.totalUsers || 0,
      icon: Users,
      color: "text-green-400",
      bgColor: "bg-green-500/20",
      trend: "+8%",
      trendUp: true,
    },
    {
      title: "Active Installations",
      value: stats?.activeInstallations || 0,
      icon: Activity,
      color: "text-purple-400",
      bgColor: "bg-purple-500/20",
      trend: "+23%",
      trendUp: true,
    },
    {
      title: "Monthly Revenue",
      value: `$${stats?.monthlyRevenue?.toLocaleString() || 0}`,
      icon: DollarSign,
      color: "text-yellow-400",
      bgColor: "bg-yellow-500/20",
      trend: "+15%",
      trendUp: true,
    },
  ];

  const quickActions = [
    { title: "Pending Plugins", count: stats?.pendingPlugins || 0, icon: Clock, href: "/admin/plugins?status=pending", color: "text-yellow-400" },
    { title: "Active Plugins", count: stats?.activePlugins || 0, icon: CheckCircle2, href: "/admin/plugins?status=active", color: "text-green-400" },
    { title: "Reported Issues", count: stats?.reportedIssues || 0, icon: XCircle, href: "/admin/moderation", color: "text-red-400" },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <h1 className="text-3xl font-bold">Admin Dashboard</h1>
          <p className="text-muted-foreground">
            Platform overview and management controls
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        {/* Stats Grid */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          {statCards.map((stat) => {
            const Icon = stat.icon;
            return (
              <Card key={stat.title} className="border-border bg-card/50 backdrop-blur">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">{stat.title}</p>
                      <p className="text-3xl font-bold mt-1">{stat.value}</p>
                      <p className={`text-xs mt-2 ${stat.trendUp ? "text-green-400" : "text-red-400"}`}>
                        {stat.trend} from last month
                      </p>
                    </div>
                    <div className={`h-12 w-12 rounded-full ${stat.bgColor} flex items-center justify-center`}>
                      <Icon className={`h-6 w-6 ${stat.color}`} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Quick Actions */}
        <div className="grid md:grid-cols-3 gap-4 mb-8">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <a key={action.title} href={action.href}>
                <Card className="border-border bg-card/50 backdrop-blur hover:border-primary/50 transition-colors cursor-pointer">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">{action.title}</p>
                        <p className="text-2xl font-bold mt-1">{action.count}</p>
                      </div>
                      <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                        <Icon className={`h-5 w-5 ${action.color}`} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </a>
            );
          })}
        </div>

        {/* Content Grid */}
        <div className="grid lg:grid-cols-2 gap-6">
          {/* Recent Activity */}
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Recent Activity</CardTitle>
                <Button variant="outline" size="sm">View All</Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {recentActivity?.map((activity) => (
                  <div key={activity.id} className="flex items-start gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors">
                    <div className={`h-8 w-8 rounded-full flex items-center justify-center ${
                      activity.status === "pending" ? "bg-yellow-500/20" : "bg-green-500/20"
                    }`}>
                      {activity.status === "pending" ? (
                        <Clock className="h-4 w-4 text-yellow-400" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 text-green-400" />
                      )}
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{activity.title}</p>
                      <p className="text-xs text-muted-foreground">{activity.time}</p>
                    </div>
                    <Badge variant="outline" className="text-xs">
                      {activity.type.replace(/_/g, " ")}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* System Health */}
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <CardTitle>System Health</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-green-500/20 flex items-center justify-center">
                      <CheckCircle2 className="h-4 w-4 text-green-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">API Server</p>
                      <p className="text-xs text-muted-foreground">All systems operational</p>
                    </div>
                  </div>
                  <Badge className="bg-green-500/20 text-green-400 border-green-500/50">Healthy</Badge>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-green-500/20 flex items-center justify-center">
                      <CheckCircle2 className="h-4 w-4 text-green-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Database</p>
                      <p className="text-xs text-muted-foreground">Response time: 12ms</p>
                    </div>
                  </div>
                  <Badge className="bg-green-500/20 text-green-400 border-green-500/50">Healthy</Badge>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-green-500/20 flex items-center justify-center">
                      <CheckCircle2 className="h-4 w-4 text-green-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Plugin Registry</p>
                      <p className="text-xs text-muted-foreground">156 plugins loaded</p>
                    </div>
                  </div>
                  <Badge className="bg-green-500/20 text-green-400 border-green-500/50">Healthy</Badge>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-yellow-500/20 flex items-center justify-center">
                      <Clock className="h-4 w-4 text-yellow-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">AI Tools Service</p>
                      <p className="text-xs text-muted-foreground">High load detected</p>
                    </div>
                  </div>
                  <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/50">Degraded</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Quick Links */}
        <Card className="border-border bg-card/50 backdrop-blur mt-6">
          <CardHeader>
            <CardTitle>Management</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-4 gap-4">
              <Button variant="outline" className="h-20 flex-col gap-2">
                <ShoppingBag className="h-6 w-6" />
                <span>Plugins</span>
              </Button>
              <Button variant="outline" className="h-20 flex-col gap-2">
                <Users className="h-6 w-6" />
                <span>Users</span>
              </Button>
              <Button variant="outline" className="h-20 flex-col gap-2">
                <TrendingUp className="h-6 w-6" />
                <span>Analytics</span>
              </Button>
              <Button variant="outline" className="h-20 flex-col gap-2">
                <Activity className="h-6 w-6" />
                <span>Moderation</span>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
