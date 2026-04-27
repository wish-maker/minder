"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, Star, ArrowRight, CheckCircle2, Settings, Eye } from "lucide-react";
import { Plugin } from "@/lib/types/plugin";
import TierEnforcementBadge from "@/components/marketplace/TierEnforcementBadge";

interface PluginCardProps {
  plugin: Plugin;
}

export default function PluginCard({ plugin }: PluginCardProps) {
  const isFree = plugin.pricing_model === 'free';
  const tierColors = {
    community: 'bg-green-500/20 text-green-400 border-green-500/50',
    professional: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
    enterprise: 'bg-purple-500/20 text-purple-400 border-purple-500/50',
  };

  return (
    <Card className="border-border bg-card/50 backdrop-blur hover:border-primary/50 transition-colors">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="text-lg">{plugin.display_name}</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">by {plugin.author}</p>
          </div>
          <Badge className={tierColors[plugin.base_tier]}>
            {plugin.base_tier}
          </Badge>
        </div>
      </CardHeader>

      <CardContent>
        <p className="text-sm text-muted-foreground mb-4 line-clamp-3">
          {plugin.description}
        </p>

        {/* Stats */}
        <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
          <div className="flex items-center gap-1">
            <Download className="h-4 w-4" />
            <span>{plugin.download_count}</span>
          </div>
          {plugin.rating_count > 0 && (
            <div className="flex items-center gap-1">
              <Star className="h-4 w-4 fill-yellow-400" />
              <span>{plugin.rating_average?.toFixed(1)} ({plugin.rating_count})</span>
            </div>
          )}
          <div className="flex items-center gap-1">
            <CheckCircle2 className="h-4 w-4 text-green-400" />
            <span>v{plugin.current_version}</span>
          </div>
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="text-xs">
            {plugin.distribution_type}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {isFree ? 'Free' : 'Paid'}
          </Badge>
          <TierEnforcementBadge
            currentTier="community"
            requiredTier={plugin.base_tier}
            featureName={plugin.display_name}
            description={`Requires ${plugin.base_tier} tier or higher`}
          />
          {plugin.featured && (
            <Badge className="text-xs bg-yellow-500/20 text-yellow-400 border-yellow-500/50">
              Featured
            </Badge>
          )}
        </div>
      </CardContent>

      <CardFooter className="flex gap-2">
        <Link href={`/marketplace/plugins/${plugin.id}`} className="flex-1">
          <Button variant="outline" className="w-full gap-2">
            <Eye className="h-4 w-4" />
            View Details
          </Button>
        </Link>
        <Button className="flex-1 gap-2">
          <Download className="h-4 w-4" />
          Install
        </Button>
      </CardFooter>
    </Card>
  );
}