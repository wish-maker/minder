"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  Zap,
  Crown,
  Shield,
  ArrowRight,
  Settings,
  Sparkles,
} from "lucide-react";
import { pluginsApi, defaultPluginsApi } from "@/lib/api";
import { DefaultPlugin } from "@/lib/types/default-plugins";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type OnboardingStep = "welcome" | "select-plugins" | "installing" | "complete";

const tierInfo = {
  community: {
    name: "Community",
    icon: Shield,
    color: "text-green-400",
    bgColor: "bg-green-500/20",
    borderColor: "border-green-500/50",
    description: "Free tier with essential plugins and AI tools",
  },
  professional: {
    name: "Professional",
    icon: Crown,
    color: "text-blue-400",
    bgColor: "bg-blue-500/20",
    borderColor: "border-blue-500/50",
    description: "Advanced plugins and priority support",
  },
  enterprise: {
    name: "Enterprise",
    icon: Zap,
    color: "text-purple-400",
    bgColor: "bg-purple-500/20",
    borderColor: "border-purple-500/50",
    description: "Full access to all plugins and dedicated support",
  },
};

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = useState<OnboardingStep>("welcome");
  const [userTier, setUserTier] = useState<"community" | "professional" | "enterprise">("community");
  const [selectedPlugins, setSelectedPlugins] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // Fetch default plugins for user's tier
  const { data: defaultPluginsData, isLoading } = useQuery({
    queryKey: ["default-plugins", userTier],
    queryFn: () => defaultPluginsApi.getDefaultPlugins(userTier),
    enabled: currentStep === "select-plugins",
  });

  const defaultPlugins = defaultPluginsData?.plugins || [];

  // Installation mutation
  const installMutation = useMutation({
    mutationFn: async () => {
      const pluginsToInstall = Array.from(selectedPlugins);
      const promises = pluginsToInstall.map((pluginId) =>
        pluginsApi.installPlugin(pluginId, {})
      );
      await Promise.all(promises);
    },
    onSuccess: () => {
      setCurrentStep("complete");
      queryClient.invalidateQueries({ queryKey: ['installed-plugins'] });
    },
    onError: (err: any) => {
      setError(err.message || "Installation failed");
      setCurrentStep("select-plugins");
    },
  });

  const handlePluginToggle = (pluginId: string) => {
    setSelectedPlugins((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(pluginId)) {
        newSet.delete(pluginId);
      } else {
        newSet.add(pluginId);
      }
      return newSet;
    });
  };

  const handleSelectAll = () => {
    const allPluginIds = new Set(defaultPlugins.map((p) => p.pluginId));
    setSelectedPlugins(allPluginIds);
  };

  const handleContinue = () => {
    setError(null);
    if (currentStep === "welcome") {
      setCurrentStep("select-plugins");
    } else if (currentStep === "select-plugins") {
      setCurrentStep("installing");
      installMutation.mutate();
    }
  };

  const handleSkip = () => {
    router.push("/dashboard");
  };

  const handleFinish = () => {
    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Welcome Step */}
      {currentStep === "welcome" && (
        <div className="min-h-screen flex items-center justify-center">
          <div className="container mx-auto px-4">
            <div className="max-w-4xl mx-auto">
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader className="text-center pb-8">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/20 text-primary mb-4">
                    <Sparkles className="h-8 w-8" />
                  </div>
                  <CardTitle className="text-3xl">Welcome to Minder!</CardTitle>
                  <p className="text-muted-foreground mt-2">
                    Let's get you set up with the best plugins for your needs
                  </p>
                </CardHeader>
                <CardContent className="space-y-8">
                  {/* Tier Selection */}
                  <div>
                    <h3 className="text-lg font-semibold mb-4">Select Your Tier</h3>
                    <div className="grid md:grid-cols-3 gap-4">
                      {(Object.keys(tierInfo) as Array<keyof typeof tierInfo>).map((tier) => {
                        const info = tierInfo[tier];
                        const Icon = info.icon;
                        const isSelected = userTier === tier;

                        return (
                          <Card
                            key={tier}
                            className={`cursor-pointer transition-all ${
                              isSelected
                                ? "border-primary bg-primary/10"
                                : "border-border hover:border-primary/50"
                            }`}
                            onClick={() => setUserTier(tier)}
                          >
                            <CardContent className="pt-6">
                              <div className="text-center">
                                <div
                                  className={`inline-flex items-center justify-center w-12 h-12 rounded-full ${info.bgColor} ${info.color} mb-3`}
                                >
                                  <Icon className="h-6 w-6" />
                                </div>
                                <h4 className="font-semibold mb-1">{info.name}</h4>
                                <p className="text-xs text-muted-foreground mb-3">
                                  {info.description}
                                </p>
                                {isSelected && (
                                  <Badge className={info.borderColor}>Selected</Badge>
                                )}
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  </div>

                  {/* Features Preview */}
                  <div className="bg-muted/50 rounded-lg p-6">
                    <h3 className="font-semibold mb-3">What's Included</h3>
                    <div className="grid md:grid-cols-2 gap-3 text-sm">
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-400 flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">
                          Essential plugins for your tier
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-400 flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">
                          Pre-configured AI tools
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-400 flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">
                          Access to plugin marketplace
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-400 flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">
                          Ready-to-use configurations
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-between">
                    <Button variant="ghost" onClick={handleSkip}>
                      Skip for now
                    </Button>
                    <Button className="gap-2" onClick={handleContinue}>
                      Continue
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Select Plugins Step */}
      {currentStep === "select-plugins" && (
        <div className="min-h-screen">
          <div className="container mx-auto px-4 py-8">
            <div className="max-w-4xl mx-auto">
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-2xl">Select Your Plugins</CardTitle>
                      <p className="text-muted-foreground mt-1">
                        Choose the default plugins you want to install
                      </p>
                    </div>
                    <Badge className={tierInfo[userTier].bgColor + " " + tierInfo[userTier].color + " " + tierInfo[userTier].borderColor}>
                      {tierInfo[userTier].name} Tier
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  {isLoading ? (
                    <div className="text-center py-12">
                      <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
                      <p className="mt-4 text-muted-foreground">Loading plugins...</p>
                    </div>
                  ) : (
                    <>
                      <div className="flex justify-between items-center">
                        <p className="text-sm text-muted-foreground">
                          {selectedPlugins.size} of {defaultPlugins.length} plugins selected
                        </p>
                        <Button variant="outline" size="sm" onClick={handleSelectAll}>
                          Select All
                        </Button>
                      </div>

                      <div className="grid md:grid-cols-2 gap-4">
                        {defaultPlugins.map((plugin) => {
                          const isSelected = selectedPlugins.has(plugin.pluginId);

                          return (
                            <Card
                              key={plugin.pluginId}
                              className={`cursor-pointer transition-all ${
                                isSelected
                                  ? "border-primary bg-primary/10"
                                  : "border-border hover:border-primary/50"
                              }`}
                              onClick={() => handlePluginToggle(plugin.pluginId)}
                            >
                              <CardContent className="pt-6">
                                <div className="flex items-start justify-between mb-3">
                                  <div className="flex-1">
                                    <h4 className="font-semibold">{plugin.name}</h4>
                                    <p className="text-sm text-muted-foreground mt-1">
                                      {plugin.description}
                                    </p>
                                  </div>
                                  {isSelected && (
                                    <CheckCircle2 className="h-5 w-5 text-primary flex-shrink-0" />
                                  )}
                                </div>
                                <div className="flex items-center gap-2">
                                  <Badge variant="outline" className="text-xs">
                                    {plugin.category}
                                  </Badge>
                                  {plugin.autoEnable && (
                                    <Badge className="text-xs bg-green-500/20 text-green-400 border-green-500/50">
                                      Auto-Enabled
                                    </Badge>
                                  )}
                                </div>
                              </CardContent>
                            </Card>
                          );
                        })}
                      </div>

                      {error && (
                        <div className="bg-destructive/10 border border-destructive/50 rounded-lg p-4">
                          <p className="text-sm text-destructive">{error}</p>
                        </div>
                      )}

                      <div className="flex justify-between">
                        <Button variant="outline" onClick={handleSkip}>
                          Skip
                        </Button>
                        <Button
                          className="gap-2"
                          onClick={handleContinue}
                          disabled={selectedPlugins.size === 0}
                        >
                          Install Selected Plugins
                          <ArrowRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Installing Step */}
      {currentStep === "installing" && (
        <div className="min-h-screen flex items-center justify-center">
          <div className="container mx-auto px-4">
            <div className="max-w-md mx-auto text-center">
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardContent className="pt-12 pb-12">
                  <div className="inline-block h-16 w-16 animate-spin rounded-full border-4 border-primary border-t-transparent mb-6"></div>
                  <h2 className="text-2xl font-bold mb-2">Installing Plugins</h2>
                  <p className="text-muted-foreground">
                    Setting up your {selectedPlugins.size} plugins...
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Complete Step */}
      {currentStep === "complete" && (
        <div className="min-h-screen flex items-center justify-center">
          <div className="container mx-auto px-4">
            <div className="max-w-md mx-auto text-center">
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardContent className="pt-12 pb-12">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-500/20 text-green-400 mb-6">
                    <CheckCircle2 className="h-8 w-8" />
                  </div>
                  <h2 className="text-2xl font-bold mb-2">You're All Set!</h2>
                  <p className="text-muted-foreground mb-8">
                    Your plugins have been installed and are ready to use.
                  </p>
                  <Button className="w-full gap-2" onClick={handleFinish}>
                    Go to Dashboard
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
