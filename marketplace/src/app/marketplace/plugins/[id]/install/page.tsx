"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  AlertCircle,
  Settings,
  Shield,
  Zap,
} from "lucide-react";
import { pluginsApi } from "@/lib/api/plugins";
import { Plugin } from "@/lib/types/plugin";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import TierEnforcementBadge from "@/components/marketplace/TierEnforcementBadge";

type InstallStep = "overview" | "configure" | "confirm" | "installing" | "complete";

export default function PluginInstallPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const pluginId = params.id as string;
  const [currentStep, setCurrentStep] = useState<InstallStep>("overview");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [agreedToLicense, setAgreedToLicense] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userTier, setUserTier] = useState<"community" | "professional" | "enterprise">("community");

  // Fetch plugin details
  const { data: plugin, isLoading, error: fetchError } = useQuery({
    queryKey: ['plugin', pluginId],
    queryFn: () => pluginsApi.getPlugin(pluginId),
    enabled: !!pluginId,
  });

  // Installation mutation
  const installMutation = useMutation({
    mutationFn: async (pluginId: string) => {
      return pluginsApi.installPlugin(pluginId, config);
    },
    onSuccess: () => {
      setCurrentStep("complete");
      queryClient.invalidateQueries({ queryKey: ['installed-plugins'] });
    },
    onError: (err: any) => {
      setError(err.message || "Installation failed");
      setCurrentStep("overview");
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading plugin details...</p>
        </div>
      </div>
    );
  }

  if (fetchError || !plugin) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-destructive text-lg">Plugin not found</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/marketplace/plugins")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Plugins
          </Button>
        </div>
      </div>
    );
  }

  const steps = [
    { id: "overview", label: "Overview", icon: Download },
    { id: "configure", label: "Configure", icon: Settings },
    { id: "confirm", label: "Confirm", icon: Shield },
    { id: "installing", label: "Installing", icon: Zap },
    { id: "complete", label: "Complete", icon: CheckCircle2 },
  ] as const;

  const currentStepIndex = steps.findIndex((s) => s.id === currentStep);

  const handleNext = () => {
    setError(null);
    if (currentStep === "overview") setCurrentStep("configure");
    else if (currentStep === "configure") setCurrentStep("confirm");
    else if (currentStep === "confirm") {
      setCurrentStep("installing");
      installMutation.mutate(pluginId);
    }
  };

  const handleBack = () => {
    setError(null);
    if (currentStep === "configure") setCurrentStep("overview");
    else if (currentStep === "confirm") setCurrentStep("configure");
  };

  const handleConfigChange = (key: string, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button
            variant="ghost"
            onClick={() => router.push(`/marketplace/plugins/${pluginId}`)}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Plugin
          </Button>
        </div>
      </div>

      {/* Progress Steps */}
      <div className="border-b border-border bg-card/30">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center justify-between max-w-3xl mx-auto">
            {steps.map((step, index) => {
              const Icon = step.icon;
              const isCompleted = index < currentStepIndex;
              const isCurrent = index === currentStepIndex;

              return (
                <div key={step.id} className="flex items-center flex-1">
                  <div className="flex flex-col items-center flex-1">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-colors ${
                        isCompleted
                          ? "bg-green-500 border-green-500 text-white"
                          : isCurrent
                          ? "bg-primary border-primary text-primary-foreground"
                          : "bg-muted border-border text-muted-foreground"
                      }`}
                    >
                      {isCompleted ? (
                        <CheckCircle2 className="h-5 w-5" />
                      ) : (
                        <Icon className="h-5 w-5" />
                      )}
                    </div>
                    <span
                      className={`text-xs mt-2 font-medium ${
                        isCurrent ? "text-primary" : "text-muted-foreground"
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                  {index < steps.length - 1 && (
                    <div
                      className={`h-0.5 flex-1 mx-2 transition-colors ${
                        isCompleted ? "bg-green-500" : "bg-border"
                      }`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-3xl mx-auto">
          {/* Overview Step */}
          {currentStep === "overview" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Install {plugin.display_name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <p className="text-muted-foreground">{plugin.description}</p>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <Label className="text-muted-foreground">Version</Label>
                    <p className="font-semibold">v{plugin.current_version}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Author</Label>
                    <p className="font-semibold">{plugin.author}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">License</Label>
                    <p className="font-semibold">{plugin.license || "Standard"}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Required Tier</Label>
                    <TierEnforcementBadge
                      currentTier={userTier}
                      requiredTier={plugin.base_tier}
                      featureName={plugin.display_name}
                      description={`This plugin requires ${plugin.base_tier} tier or higher`}
                      onUpgrade={() => window.location.href = "/pricing"}
                    />
                  </div>
                </div>

                {plugin.pricing_model !== "free" && (
                  <div className="bg-yellow-500/10 border border-yellow-500/50 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold text-yellow-400">Paid Plugin</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          This plugin requires a {plugin.base_tier} subscription. You will be charged
                          according to your pricing plan.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => router.back()}>
                    Cancel
                  </Button>
                  <Button onClick={handleNext}>
                    Continue to Configuration
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Configure Step */}
          {currentStep === "configure" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Configuration</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Configure the plugin settings before installation
                </p>
              </CardHeader>
              <CardContent className="space-y-6">
                {plugin.configuration_schema?.fields && plugin.configuration_schema.fields.length > 0 ? (
                  <div className="space-y-4">
                    {plugin.configuration_schema.fields.map((field) => (
                      <div key={field.name}>
                        <Label htmlFor={field.name}>
                          {field.label || field.name}
                          {field.required && <span className="text-destructive ml-1">*</span>}
                        </Label>
                        <Input
                          id={field.name}
                          type={field.type === "password" ? "password" : "text"}
                          placeholder={field.placeholder || `Enter ${field.label || field.name}`}
                          value={config[field.name] || ""}
                          onChange={(e) => handleConfigChange(field.name, e.target.value)}
                          className="mt-1"
                        />
                        {field.description && (
                          <p className="text-xs text-muted-foreground mt-1">{field.description}</p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Settings className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p>This plugin does not require any configuration.</p>
                  </div>
                )}

                {error && (
                  <div className="bg-destructive/10 border border-destructive/50 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-destructive">{error}</p>
                    </div>
                  </div>
                )}

                <div className="flex justify-between">
                  <Button variant="outline" onClick={handleBack}>
                    Back
                  </Button>
                  <Button onClick={handleNext}>Review & Confirm</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Confirm Step */}
          {currentStep === "confirm" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Review & Confirm</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Review your configuration before installing
                </p>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h3 className="font-semibold mb-3">Plugin Information</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Name:</span>
                      <span className="font-medium">{plugin.display_name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Version:</span>
                      <span className="font-medium">v{plugin.current_version}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Type:</span>
                      <span className="font-medium capitalize">{plugin.distribution_type}</span>
                    </div>
                  </div>
                </div>

                {Object.keys(config).length > 0 && (
                  <div>
                    <h3 className="font-semibold mb-3">Configuration</h3>
                    <div className="space-y-2 text-sm bg-muted/50 rounded-lg p-4">
                      {Object.entries(config).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span className="text-muted-foreground">{key}:</span>
                          <span className="font-medium font-mono">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={agreedToLicense}
                      onChange={(e) => setAgreedToLicense(e.target.checked)}
                      className="mt-1"
                    />
                    <span className="text-sm text-muted-foreground">
                      I agree to the{" "}
                      <a
                        href={plugin.license_url || "#"}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline"
                      >
                        license terms
                      </a>{" "}
                      and understand that this plugin will be installed on my system.
                    </span>
                  </label>
                </div>

                {error && (
                  <div className="bg-destructive/10 border border-destructive/50 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-destructive">{error}</p>
                    </div>
                  </div>
                )}

                <div className="flex justify-between">
                  <Button variant="outline" onClick={handleBack}>
                    Back
                  </Button>
                  <Button onClick={handleNext} disabled={!agreedToLicense}>
                    Install Plugin
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Installing Step */}
          {currentStep === "installing" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardContent className="text-center py-12">
                <div className="inline-block h-16 w-16 animate-spin rounded-full border-4 border-primary border-t-transparent mb-6"></div>
                <h2 className="text-2xl font-bold mb-2">Installing {plugin.display_name}</h2>
                <p className="text-muted-foreground">Please wait while we install the plugin...</p>
                {installMutation.isError && (
                  <div className="mt-6 bg-destructive/10 border border-destructive/50 rounded-lg p-4 max-w-md mx-auto">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-destructive">
                        {error || "Installation failed. Please try again."}
                      </p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Complete Step */}
          {currentStep === "complete" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardContent className="text-center py-12">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-500/20 text-green-400 mb-6">
                  <CheckCircle2 className="h-8 w-8" />
                </div>
                <h2 className="text-2xl font-bold mb-2">Installation Complete!</h2>
                <p className="text-muted-foreground mb-8">
                  {plugin.display_name} has been successfully installed and is ready to use.
                </p>
                <div className="flex justify-center gap-3">
                  <Button variant="outline" onClick={() => router.push("/dashboard")}>
                    Go to Dashboard
                  </Button>
                  <Button onClick={() => router.push(`/marketplace/plugins/${pluginId}`)}>
                    View Plugin
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
