"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Upload,
  FolderOpen,
  Settings,
  BarChart3,
  Plus,
  TrendingUp,
  DollarSign,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useRouter } from "next/navigation";

export default function DeveloperPortalPage() {
  const router = useRouter();

  // Fetch developer stats
  const { data: stats } = useQuery({
    queryKey: ["developer-stats"],
    queryFn: async () => {
      // Mock implementation
      return {
        totalPlugins: 5,
        activePlugins: 4,
        pendingPlugins: 1,
        totalDownloads: 12500,
        monthlyRevenue: 2500,
        totalReviews: 48,
        averageRating: 4.5,
      };
    },
  });

  // Fetch developer's plugins
  const { data: myPlugins } = useQuery({
    queryKey: ["my-plugins"],
    queryFn: async () => {
      // Mock implementation
      return [
        {
          id: "1",
          name: "AI Code Assistant",
          display_name: "AI Code Assistant",
          description: "Intelligent code completion and refactoring",
          status: "approved",
          downloads: 5400,
          rating: 4.8,
          featured: true,
        },
        {
          id: "2",
          name: "Data Visualizer",
          display_name: "Data Visualizer",
          description: "Beautiful data visualization tools",
          status: "approved",
          downloads: 3200,
          rating: 4.6,
          featured: false,
        },
        {
          id: "3",
          name: "Test Generator",
          display_name: "Test Generator",
          description: "Automated test generation from code",
          status: "pending",
          downloads: 0,
          rating: 0,
          featured: false,
        },
      ];
    },
  });

  const quickActions = [
    {
      title: "Submit New Plugin",
      description: "Create and submit a new plugin",
      icon: Plus,
      href: "/developer/plugins/new",
      color: "text-blue-400",
    },
    {
      title: "My Plugins",
      description: "Manage your existing plugins",
      icon: FolderOpen,
      href: "/developer/plugins",
      count: myPlugins?.length || 0,
      color: "text-green-400",
    },
    {
      title: "Analytics",
      description: "View performance metrics",
      icon: BarChart3,
      href: "/developer/analytics",
      color: "text-purple-400",
    },
    {
      title: "Settings",
      description: "Developer preferences",
      icon: Settings,
      href: "/developer/settings",
      color: "text-yellow-400",
    },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">Developer Portal</h1>
              <p className="text-muted-foreground">
                Manage your plugins and track performance
              </p>
            </div>
            <Button onClick={() => router.push("/developer/plugins/new")}>
              <Plus className="mr-2 h-4 w-4" />
              New Plugin
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        {/* Stats Overview */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Plugins</p>
                  <p className="text-3xl font-bold mt-1">{stats?.totalPlugins || 0}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-blue-500/20 flex items-center justify-center">
                  <FolderOpen className="h-6 w-6 text-blue-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Downloads</p>
                  <p className="text-3xl font-bold mt-1">{stats?.totalDownloads?.toLocaleString() || 0}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-green-500/20 flex items-center justify-center">
                  <TrendingUp className="h-6 w-6 text-green-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Monthly Revenue</p>
                  <p className="text-3xl font-bold mt-1">${stats?.monthlyRevenue?.toLocaleString() || 0}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-yellow-500/20 flex items-center justify-center">
                  <DollarSign className="h-6 w-6 text-yellow-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Average Rating</p>
                  <p className="text-3xl font-bold mt-1">{stats?.averageRating || 0}</p>
                </div>
                <div className="h-12 w-12 rounded-full bg-purple-500/20 flex items-center justify-center">
                  <CheckCircle2 className="h-6 w-6 text-purple-400" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Quick Actions */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <a
                key={action.href}
                href={action.href}
                className="block"
              >
                <Card className="border-border bg-card/50 backdrop-blur hover:border-primary/50 transition-colors cursor-pointer h-full">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className={`h-10 w-10 rounded-full bg-muted flex items-center justify-center`}>
                        <Icon className={`h-5 w-5 ${action.color}`} />
                      </div>
                      {action.count !== undefined && (
                        <Badge variant="outline">{action.count}</Badge>
                      )}
                    </div>
                    <h3 className="font-semibold mb-1">{action.title}</h3>
                    <p className="text-sm text-muted-foreground">{action.description}</p>
                  </CardContent>
                </Card>
              </a>
            );
          })}
        </div>

        {/* My Plugins */}
        <Card className="border-border bg-card/50 backdrop-blur">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>My Plugins</CardTitle>
              <Button variant="outline" onClick={() => router.push("/developer/plugins")}>
                View All
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {myPlugins && myPlugins.length > 0 ? (
              <div className="space-y-4">
                {myPlugins.map((plugin) => (
                  <div
                    key={plugin.id}
                    className="flex items-center justify-between p-4 rounded-lg hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold">{plugin.display_name}</h3>
                        {plugin.status === "approved" ? (
                          <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Approved
                          </Badge>
                        ) : (
                          <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
                            <Clock className="h-3 w-3 mr-1" />
                            Pending
                          </Badge>
                        )}
                        {plugin.featured && (
                          <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
                            Featured
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">{plugin.description}</p>
                    </div>

                    <div className="flex items-center gap-6 text-sm">
                      <div className="text-center">
                        <p className="font-semibold">{plugin.downloads?.toLocaleString() || 0}</p>
                        <p className="text-xs text-muted-foreground">Downloads</p>
                      </div>
                      <div className="text-center">
                        <p className="font-semibold">★ {plugin.rating || 0}</p>
                        <p className="text-xs text-muted-foreground">Rating</p>
                      </div>

                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => router.push(`/developer/plugins/${plugin.id}`)}
                      >
                        Manage
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <Upload className="h-12 w-12 mx-auto mb-3 opacity-50" />
                <p className="mb-4">You haven't submitted any plugins yet.</p>
                <Button onClick={() => router.push("/developer/plugins/new")}>
                  <Plus className="mr-2 h-4 w-4" />
                  Submit Your First Plugin
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
