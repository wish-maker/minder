"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Plus,
  X,
  Upload,
  FileText,
  Image as ImageIcon,
  Zap,
} from "lucide-react";
import { pluginsApi } from "@/lib/api/plugins";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

type SubmissionStep = "basic" | "ai-tools" | "manifest" | "media" | "review";

export default function NewPluginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = useState<SubmissionStep>("basic");
  const [pluginData, setPluginData] = useState({
    // Basic Info
    name: "",
    display_name: "",
    description: "",
    long_description: "",
    author: "",
    author_email: "",
    repository: "",
    homepage: "",
    license: "MIT",
    distribution_type: "python" as "container" | "python" | "typescript",
    docker_image: "",
    pricing_model: "free" as "free" | "paid" | "freemium",
    base_tier: "community" as "community" | "professional" | "enterprise",
    categories: [] as string[],
    tags: [] as string[],

    // AI Tools
    ai_tools: [] as Array<{
      name: string;
      tool_name: string;
      type: "analysis" | "action" | "query" | "automation";
      description: string;
      endpoint: string;
      method: string;
      parameters?: Record<string, any>;
      required_tier: "community" | "professional" | "enterprise";
    }>,

    // Manifest
    manifest_content: "",

    // Media
    logo_url: "",
    screenshots: [] as string[],
  });

  const steps = [
    { id: "basic", label: "Basic Info", icon: FileText },
    { id: "ai-tools", label: "AI Tools", icon: Zap },
    { id: "manifest", label: "Manifest", icon: FileText },
    { id: "media", label: "Media", icon: ImageIcon },
    { id: "review", label: "Review", icon: CheckCircle2 },
  ] as const;

  const currentStepIndex = steps.findIndex((s) => s.id === currentStep);

  // Submit plugin mutation
  const submitMutation = useMutation({
    mutationFn: async (data: typeof pluginData) => {
      return pluginsApi.listPlugins({}); // Mock - replace with actual submit API
    },
    onSuccess: () => {
      router.push("/developer?submitted=true");
    },
  });

  const handleNext = () => {
    const stepOrder: SubmissionStep[] = ["basic", "ai-tools", "manifest", "media", "review"];
    const currentIndex = stepOrder.indexOf(currentStep);
    if (currentIndex < stepOrder.length - 1) {
      setCurrentStep(stepOrder[currentIndex + 1]);
    }
  };

  const handleBack = () => {
    const stepOrder: SubmissionStep[] = ["basic", "ai-tools", "manifest", "media", "review"];
    const currentIndex = stepOrder.indexOf(currentStep);
    if (currentIndex > 0) {
      setCurrentStep(stepOrder[currentIndex - 1]);
    }
  };

  const handleSubmit = () => {
    submitMutation.mutate(pluginData);
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button
            variant="ghost"
            onClick={() => router.push("/developer")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Portal
          </Button>

          <h1 className="text-3xl font-bold mt-4">Submit New Plugin</h1>
          <p className="text-muted-foreground">
            Follow the steps to submit your plugin to the marketplace
          </p>
        </div>
      </div>

      {/* Progress Steps */}
      <div className="border-b border-border bg-card/30">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center justify-between max-w-4xl mx-auto">
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
          {currentStep === "basic" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Provide the basic details about your plugin
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="name">Plugin Name *</Label>
                    <Input
                      id="name"
                      placeholder="my-awesome-plugin"
                      value={pluginData.name}
                      onChange={(e) => setPluginData({ ...pluginData, name: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label htmlFor="display_name">Display Name *</Label>
                    <Input
                      id="display_name"
                      placeholder="My Awesome Plugin"
                      value={pluginData.display_name}
                      onChange={(e) => setPluginData({ ...pluginData, display_name: e.target.value })}
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="description">Short Description *</Label>
                  <Input
                    id="description"
                    placeholder="A brief description of your plugin"
                    value={pluginData.description}
                    onChange={(e) => setPluginData({ ...pluginData, description: e.target.value })}
                  />
                </div>

                <div>
                  <Label htmlFor="long_description">Long Description</Label>
                  <textarea
                    id="long_description"
                    className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    placeholder="Detailed description of what your plugin does..."
                    value={pluginData.long_description}
                    onChange={(e) => setPluginData({ ...pluginData, long_description: e.target.value })}
                  />
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="author">Author Name *</Label>
                    <Input
                      id="author"
                      placeholder="Your name or organization"
                      value={pluginData.author}
                      onChange={(e) => setPluginData({ ...pluginData, author: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label htmlFor="author_email">Author Email</Label>
                    <Input
                      id="author_email"
                      type="email"
                      placeholder="your@email.com"
                      value={pluginData.author_email}
                      onChange={(e) => setPluginData({ ...pluginData, author_email: e.target.value })}
                    />
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="repository">Repository URL</Label>
                    <Input
                      id="repository"
                      placeholder="https://github.com/user/repo"
                      value={pluginData.repository}
                      onChange={(e) => setPluginData({ ...pluginData, repository: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label htmlFor="homepage">Homepage URL</Label>
                    <Input
                      id="homepage"
                      placeholder="https://your-plugin.com"
                      value={pluginData.homepage}
                      onChange={(e) => setPluginData({ ...pluginData, homepage: e.target.value })}
                    />
                  </div>
                </div>

                <div className="grid md:grid-cols-3 gap-4">
                  <div>
                    <Label htmlFor="distribution_type">Distribution Type *</Label>
                    <select
                      id="distribution_type"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={pluginData.distribution_type}
                      onChange={(e) => setPluginData({ ...pluginData, distribution_type: e.target.value as any })}
                    >
                      <option value="python">Python Package</option>
                      <option value="container">Container</option>
                      <option value="typescript">TypeScript Package</option>
                    </select>
                  </div>

                  <div>
                    <Label htmlFor="pricing_model">Pricing Model *</Label>
                    <select
                      id="pricing_model"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={pluginData.pricing_model}
                      onChange={(e) => setPluginData({ ...pluginData, pricing_model: e.target.value as any })}
                    >
                      <option value="free">Free</option>
                      <option value="paid">Paid</option>
                      <option value="freemium">Freemium</option>
                    </select>
                  </div>

                  <div>
                    <Label htmlFor="base_tier">Required Tier *</Label>
                    <select
                      id="base_tier"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={pluginData.base_tier}
                      onChange={(e) => setPluginData({ ...pluginData, base_tier: e.target.value as any })}
                    >
                      <option value="community">Community</option>
                      <option value="professional">Professional</option>
                      <option value="enterprise">Enterprise</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-between">
                  <Button variant="outline" onClick={() => router.back()}>
                    Cancel
                  </Button>
                  <Button onClick={handleNext}>
                    Next: AI Tools
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {currentStep === "ai-tools" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>AI Tools Definition</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Define the AI tools provided by your plugin
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="text-center py-8 border-2 border-dashed border-border rounded-lg">
                  <Zap className="h-12 w-12 mx-auto mb-3 text-muted-foreground" />
                  <p className="text-muted-foreground mb-2">Define AI tools in your plugin</p>
                  <p className="text-sm text-muted-foreground mb-4">
                    AI tools allow your plugin to provide intelligent capabilities
                  </p>
                  <Button variant="outline">
                    <Plus className="h-4 w-4 mr-2" />
                    Add AI Tool
                  </Button>
                </div>

                {pluginData.ai_tools.length > 0 && (
                  <div className="space-y-2">
                    {pluginData.ai_tools.map((tool, index) => (
                      <div key={index} className="p-3 rounded-lg bg-muted/50 flex items-center justify-between">
                        <div>
                          <p className="font-medium">{tool.tool_name}</p>
                          <p className="text-sm text-muted-foreground">{tool.description}</p>
                        </div>
                        <Button variant="ghost" size="sm">
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex justify-between">
                  <Button variant="outline" onClick={handleBack}>
                    Back
                  </Button>
                  <Button onClick={handleNext}>
                    Next: Manifest
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {currentStep === "manifest" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Plugin Manifest</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Provide your plugin manifest (YAML or JSON)
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="manifest_content">Manifest Content</Label>
                  <textarea
                    id="manifest_content"
                    className="flex min-h-[300px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
                    placeholder="# Plugin manifest in YAML or JSON format"
                    value={pluginData.manifest_content}
                    onChange={(e) => setPluginData({ ...pluginData, manifest_content: e.target.value })}
                  />
                  <p className="text-xs text-muted-foreground mt-2">
                    Define your plugin's AI tools, configuration schema, and metadata
                  </p>
                </div>

                <div className="flex justify-between">
                  <Button variant="outline" onClick={handleBack}>
                    Back
                  </Button>
                  <Button onClick={handleNext}>
                    Next: Media
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {currentStep === "media" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Media Assets</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Upload your plugin logo and screenshots
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Plugin Logo</Label>
                  <div className="mt-2 border-2 border-dashed border-border rounded-lg p-8 text-center">
                    <Upload className="h-12 w-12 mx-auto mb-3 text-muted-foreground" />
                    <p className="text-muted-foreground mb-2">Upload plugin logo</p>
                    <p className="text-xs text-muted-foreground">Recommended: 512x512px, PNG or SVG</p>
                    <Button variant="outline" className="mt-4">
                      Choose File
                    </Button>
                  </div>
                </div>

                <div>
                  <Label>Screenshots</Label>
                  <div className="mt-2 border-2 border-dashed border-border rounded-lg p-8 text-center">
                    <ImageIcon className="h-12 w-12 mx-auto mb-3 text-muted-foreground" />
                    <p className="text-muted-foreground mb-2">Upload plugin screenshots</p>
                    <p className="text-xs text-muted-foreground">Recommended: 16:9 aspect ratio, max 5 screenshots</p>
                    <Button variant="outline" className="mt-4">
                      Choose Files
                    </Button>
                  </div>
                </div>

                <div className="flex justify-between">
                  <Button variant="outline" onClick={handleBack}>
                    Back
                  </Button>
                  <Button onClick={handleNext}>
                    Next: Review
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {currentStep === "review" && (
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Review & Submit</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Review your plugin submission before submitting
                </p>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h3 className="font-semibold mb-3">Plugin Information</h3>
                  <div className="space-y-2 text-sm bg-muted/50 rounded-lg p-4">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Name:</span>
                      <span className="font-medium">{pluginData.display_name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Type:</span>
                      <span className="font-medium capitalize">{pluginData.distribution_type}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Pricing:</span>
                      <span className="font-medium Capitalize">{pluginData.pricing_model}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Tier:</span>
                      <span className="font-medium Capitalize">{pluginData.base_tier}</span>
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold mb-3">AI Tools</h3>
                  <p className="text-sm text-muted-foreground">
                    {pluginData.ai_tools.length} AI tool{pluginData.ai_tools.length !== 1 ? "s" : ""} defined
                  </p>
                </div>

                <div className="bg-yellow-500/10 border border-yellow-500/50 rounded-lg p-4">
                  <p className="text-sm text-yellow-400">
                    <strong>Important:</strong> By submitting this plugin, you agree to our terms of service
                    and guidelines. Your plugin will be reviewed by our team before being published to the marketplace.
                  </p>
                </div>

                <div className="flex justify-between">
                  <Button variant="outline" onClick={handleBack} disabled={submitMutation.isPending}>
                    Back
                  </Button>
                  <Button onClick={handleSubmit} disabled={submitMutation.isPending}>
                    {submitMutation.isPending ? "Submitting..." : "Submit Plugin"}
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
