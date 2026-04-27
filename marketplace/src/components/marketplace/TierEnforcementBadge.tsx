"use client";

import { useState } from "react";
import {
  Lock,
  Crown,
  Shield,
  AlertTriangle,
  CheckCircle2,
  Info,
  ChevronRight,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { defaultPluginsApi } from "@/lib/api/default-plugins";

interface TierEnforcementBadgeProps {
  currentTier: "community" | "professional" | "enterprise";
  requiredTier: "community" | "professional" | "enterprise";
  featureName: string;
  description?: string;
  showUpgradePrompt?: boolean;
  onUpgrade?: () => void;
}

export default function TierEnforcementBadge({
  currentTier,
  requiredTier,
  featureName,
  description,
  showUpgradePrompt = true,
  onUpgrade,
}: TierEnforcementBadgeProps) {
  const [showDetails, setShowDetails] = useState(false);

  const tierLevels = { community: 0, professional: 1, enterprise: 2 };
  const currentLevel = tierLevels[currentTier];
  const requiredLevel = tierLevels[requiredTier];
  const isAccessible = currentLevel >= requiredLevel;

  const tierConfig = {
    community: {
      name: "Community",
      icon: Shield,
      color: "text-green-400",
      bgColor: "bg-green-500/20",
      borderColor: "border-green-500/50",
      price: "Free",
    },
    professional: {
      name: "Professional",
      icon: Crown,
      color: "text-blue-400",
      bgColor: "bg-blue-500/20",
      borderColor: "border-blue-500/50",
      price: "$29/mo",
    },
    enterprise: {
      name: "Enterprise",
      icon: Lock,
      color: "text-purple-400",
      bgColor: "bg-purple-500/20",
      borderColor: "border-purple-500/50",
      price: "Custom",
    },
  };

  const config = tierConfig[requiredTier];

  if (isAccessible) {
    return (
      <Badge className={`bg-green-500/20 text-green-400 border-green-500/50`}>
        <CheckCircle2 className="h-3 w-3 mr-1" />
        Available
      </Badge>
    );
  }

  return (
    <div className="relative">
      <Badge
        className={`bg-yellow-500/20 text-yellow-400 border-yellow-500/50 cursor-pointer hover:bg-yellow-500/30 transition-colors`}
        onClick={() => setShowDetails(!showDetails)}
      >
        <Lock className="h-3 w-3 mr-1" />
        {config.name}
      </Badge>

      {showDetails && showUpgradePrompt && (
        <Card className="absolute z-50 w-80 mt-2 border-border bg-card shadow-lg">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Tier Upgrade Required</CardTitle>
              <button
                onClick={() => setShowDetails(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg ${config.bgColor}`}>
              <config.icon className={`h-5 w-5 ${config.color}`} />
              <div>
                <p className="font-semibold text-sm">{config.name} Tier</p>
                <p className="text-xs text-muted-foreground">{config.price}</p>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">{featureName}</p>
              {description && (
                <p className="text-xs text-muted-foreground">{description}</p>
              )}
            </div>

            <div className="bg-yellow-500/10 border border-yellow-500/50 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-yellow-400">
                  This feature requires {config.name} tier or higher
                </p>
              </div>
            </div>

            <Button
              className="w-full"
              size="sm"
              onClick={() => {
                onUpgrade?.();
                setShowDetails(false);
              }}
            >
              <Crown className="h-4 w-4 mr-2" />
              Upgrade to {config.name}
            </Button>

            <Button
              variant="outline"
              className="w-full"
              size="sm"
              onClick={() => setShowDetails(false)}
            >
              Maybe Later
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
