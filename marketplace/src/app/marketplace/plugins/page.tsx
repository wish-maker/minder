"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Filter, SlidersHorizontal } from "lucide-react";
import { pluginsApi } from "@/lib/api/plugins";
import PluginCard from "@/components/marketplace/PluginCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function PluginsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedTier, setSelectedTier] = useState<string>("");
  const [selectedPricing, setSelectedPricing] = useState<string>("");

  // Fetch plugins
  const { data: pluginsData, isLoading, error } = useQuery({
    queryKey: ['plugins', searchQuery, selectedCategory, selectedTier, selectedPricing],
    queryFn: () => pluginsApi.listPlugins({
      search: searchQuery || undefined,
      category: selectedCategory || undefined,
      tier: selectedTier as any || undefined,
      pricing: selectedPricing as any || undefined,
    }),
  });

  const plugins = pluginsData?.plugins || [];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold">Plugin Marketplace</h1>
            <Button variant="outline">
              <Filter className="mr-2 h-4 w-4" />
              Filters
            </Button>
          </div>

          {/* Search Bar */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search plugins..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Filter Chips */}
          <div className="flex gap-2 flex-wrap">
            <Button
              variant={selectedTier === 'community' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedTier(selectedTier === 'community' ? '' : 'community')}
            >
              Community
            </Button>
            <Button
              variant={selectedTier === 'professional' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedTier(selectedTier === 'professional' ? '' : 'professional')}
            >
              Professional
            </Button>
            <Button
              variant={selectedTier === 'enterprise' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedTier(selectedTier === 'enterprise' ? '' : 'enterprise')}
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
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">{plugins.length}</div>
            <div className="text-sm text-muted-foreground">Available Plugins</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">
              {plugins.filter(p => p.pricing_model === 'free').length}
            </div>
            <div className="text-sm text-muted-foreground">Free Plugins</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">
              {plugins.filter(p => p.pricing_model === 'paid').length}
            </div>
            <div className="text-sm text-muted-foreground">Paid Plugins</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-2xl font-bold">
              {plugins.filter(p => p.base_tier === 'community').length}
            </div>
            <div className="text-sm text-muted-foreground">Community Tier</div>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
            <p className="mt-4 text-muted-foreground">Loading plugins...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="text-center py-12">
            <p className="text-destructive">Failed to load plugins. Please try again.</p>
          </div>
        )}

        {/* Plugins Grid */}
        {!isLoading && !error && plugins.length === 0 && (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No plugins found matching your criteria.</p>
          </div>
        )}

        {!isLoading && !error && plugins.length > 0 && (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {plugins.map((plugin) => (
              <PluginCard key={plugin.id} plugin={plugin} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}