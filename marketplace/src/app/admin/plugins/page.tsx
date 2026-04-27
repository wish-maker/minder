"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  Clock,
  Star,
  Eye,
  Edit,
  Trash2,
  MoreVertical,
} from "lucide-react";
import { pluginsApi } from "@/lib/api/plugins";
import { Plugin } from "@/lib/types/plugin";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export default function AdminPluginsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [tierFilter, setTierFilter] = useState<string>("all");

  // Fetch plugins with admin access
  const { data: pluginsData, isLoading } = useQuery({
    queryKey: ["admin-plugins", searchQuery, statusFilter, tierFilter],
    queryFn: () => pluginsApi.listPlugins({
      search: searchQuery || undefined,
    }),
  });

  const plugins = pluginsData?.plugins || [];

  // Filter plugins based on status and tier
  const filteredPlugins = plugins.filter((plugin) => {
    if (statusFilter !== "all" && plugin.status !== statusFilter) return false;
    if (tierFilter !== "all" && plugin.base_tier !== tierFilter) return false;
    return true;
  });

  const statusColors = {
    pending: "bg-yellow-500/20 text-yellow-400 border-yellow-500/50",
    approved: "bg-green-500/20 text-green-400 border-green-500/50",
    rejected: "bg-red-500/20 text-red-400 border-red-500/50",
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold">Plugin Management</h1>
              <p className="text-muted-foreground">
                Approve, manage, and monitor all plugins
              </p>
            </div>
            <Button>
              <Filter className="mr-2 h-4 w-4" />
              Advanced Filters
            </Button>
          </div>

          {/* Search */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search plugins..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            <Button
              variant={statusFilter === "all" ? "default" : "outline"}
              size="sm"
              onClick={() => setStatusFilter("all")}
            >
              All Status
            </Button>
            <Button
              variant={statusFilter === "pending" ? "default" : "outline"}
              size="sm"
              onClick={() => setStatusFilter("pending")}
            >
              Pending ({plugins.filter((p) => p.status === "pending").length})
            </Button>
            <Button
              variant={statusFilter === "approved" ? "default" : "outline"}
              size="sm"
              onClick={() => setStatusFilter("approved")}
            >
              Approved
            </Button>
            <Button
              variant={statusFilter === "rejected" ? "default" : "outline"}
              size="sm"
              onClick={() => setStatusFilter("rejected")}
            >
              Rejected
            </Button>

            <div className="w-px h-6 bg-border mx-2" />

            <Button
              variant={tierFilter === "all" ? "default" : "outline"}
              size="sm"
              onClick={() => setTierFilter("all")}
            >
              All Tiers
            </Button>
            <Button
              variant={tierFilter === "community" ? "default" : "outline"}
              size="sm"
              onClick={() => setTierFilter("community")}
            >
              Community
            </Button>
            <Button
              variant={tierFilter === "professional" ? "default" : "outline"}
              size="sm"
              onClick={() => setTierFilter("professional")}
            >
              Professional
            </Button>
            <Button
              variant={tierFilter === "enterprise" ? "default" : "outline"}
              size="sm"
              onClick={() => setTierFilter("enterprise")}
            >
              Enterprise
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        {/* Stats */}
        <div className="grid md:grid-cols-4 gap-4 mb-8">
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Plugins</p>
                  <p className="text-2xl font-bold mt-1">{plugins.length}</p>
                </div>
                <div className="h-10 w-10 rounded-full bg-blue-500/20 flex items-center justify-center">
                  <Eye className="h-5 w-5 text-blue-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Pending Review</p>
                  <p className="text-2xl font-bold mt-1 text-yellow-400">
                    {plugins.filter((p) => p.status === "pending").length}
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-yellow-500/20 flex items-center justify-center">
                  <Clock className="h-5 w-5 text-yellow-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Approved</p>
                  <p className="text-2xl font-bold mt-1 text-green-400">
                    {plugins.filter((p) => p.status === "approved").length}
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-green-500/20 flex items-center justify-center">
                  <CheckCircle2 className="h-5 w-5 text-green-400" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Featured</p>
                  <p className="text-2xl font-bold mt-1 text-purple-400">
                    {plugins.filter((p) => p.featured).length}
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-purple-500/20 flex items-center justify-center">
                  <Star className="h-5 w-5 text-purple-400" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
            <p className="mt-4 text-muted-foreground">Loading plugins...</p>
          </div>
        )}

        {/* Plugins Table */}
        {!isLoading && (
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="border-b border-border">
                    <tr className="text-left text-sm text-muted-foreground">
                      <th className="p-4 font-medium">Plugin</th>
                      <th className="p-4 font-medium">Author</th>
                      <th className="p-4 font-medium">Status</th>
                      <th className="p-4 font-medium">Tier</th>
                      <th className="p-4 font-medium">Downloads</th>
                      <th className="p-4 font-medium">Rating</th>
                      <th className="p-4 font-medium">Featured</th>
                      <th className="p-4 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPlugins.map((plugin) => (
                      <tr key={plugin.id} className="border-b border-border hover:bg-muted/50 transition-colors">
                        <td className="p-4">
                          <div>
                            <p className="font-medium">{plugin.display_name}</p>
                            <p className="text-sm text-muted-foreground">{plugin.description}</p>
                          </div>
                        </td>
                        <td className="p-4">
                          <p className="text-sm">{plugin.author}</p>
                        </td>
                        <td className="p-4">
                          <Badge className={statusColors[plugin.status]}>
                            {plugin.status}
                          </Badge>
                        </td>
                        <td className="p-4">
                          <Badge
                            className={
                              plugin.base_tier === "community"
                                ? "bg-green-500/20 text-green-400 border-green-500/50"
                                : plugin.base_tier === "professional"
                                ? "bg-blue-500/20 text-blue-400 border-blue-500/50"
                                : "bg-purple-500/20 text-purple-400 border-purple-500/50"
                            }
                          >
                            {plugin.base_tier}
                          </Badge>
                        </td>
                        <td className="p-4">
                          <p className="text-sm">{plugin.download_count.toLocaleString()}</p>
                        </td>
                        <td className="p-4">
                          {plugin.rating_count > 0 ? (
                            <div className="flex items-center gap-1">
                              <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                              <span className="text-sm">{plugin.rating_average?.toFixed(1)}</span>
                              <span className="text-xs text-muted-foreground">
                                ({plugin.rating_count})
                              </span>
                            </div>
                          ) : (
                            <span className="text-sm text-muted-foreground">No ratings</span>
                          )}
                        </td>
                        <td className="p-4">
                          {plugin.featured ? (
                            <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
                              <Star className="h-3 w-3 mr-1 fill-current" />
                              Featured
                            </Badge>
                          ) : (
                            <span className="text-sm text-muted-foreground">No</span>
                          )}
                        </td>
                        <td className="p-4">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm">
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem>
                                <Eye className="h-4 w-4 mr-2" />
                                View Details
                              </DropdownMenuItem>
                              <DropdownMenuItem>
                                <Edit className="h-4 w-4 mr-2" />
                                Edit Plugin
                              </DropdownMenuItem>
                              {plugin.status === "pending" && (
                                <>
                                  <DropdownMenuItem className="text-green-400">
                                    <CheckCircle2 className="h-4 w-4 mr-2" />
                                    Approve
                                  </DropdownMenuItem>
                                  <DropdownMenuItem className="text-red-400">
                                    <XCircle className="h-4 w-4 mr-2" />
                                    Reject
                                  </DropdownMenuItem>
                                </>
                              )}
                              {plugin.status === "approved" && (
                                <DropdownMenuItem>
                                  <Star className="h-4 w-4 mr-2" />
                                  {plugin.featured ? "Remove Featured" : "Make Featured"}
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuItem className="text-red-400">
                                <Trash2 className="h-4 w-4 mr-2" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Empty State */}
              {filteredPlugins.length === 0 && (
                <div className="text-center py-12">
                  <p className="text-muted-foreground">No plugins found matching your criteria.</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
