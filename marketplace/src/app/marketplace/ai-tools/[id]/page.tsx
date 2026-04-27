"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Play,
  Code,
  CheckCircle2,
  XCircle,
  Loader2,
  Settings,
  Zap,
  Shield,
  Copy,
  Check,
} from "lucide-react";
import { aiToolsApi } from "@/lib/api/ai-tools";
import { pluginsManagementApi } from "@/lib/api/plugins-management";
import { AITool } from "@/lib/types/ai-tools";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function AIToolDetailPage() {
  const params = useParams();
  const router = useRouter();
  const toolId = params.id as string;
  const [params, setParams] = useState<Record<string, any>>({});
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Fetch tool details
  const { data: tool, isLoading, error: fetchError } = useQuery({
    queryKey: ["ai-tool", toolId],
    queryFn: async () => {
      const tools = await aiToolsApi.getAllAITools();
      return tools.tools.find((t) => t.id === toolId);
    },
    enabled: !!toolId,
  });

  const handleTest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await pluginsManagementApi.testTool(toolId, params);
      setResult(response);
    } catch (err: any) {
      setError(err.message || "Test failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCopyCode = () => {
    const code = generateCodeExample();
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const generateCodeExample = () => {
    if (!tool) return "";
    return `// Example: Call ${tool.tool_name}
const response = await fetch('${tool.endpoint}', {
  method: '${tool.method}',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_API_KEY'
  },
  body: JSON.stringify({
    ${Object.keys(tool.parameters || {}).map(key => `${key}: "value"`).join(',\n    ')}
  })
});

const result = await response.json();
console.log(result);`;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading AI tool details...</p>
        </div>
      </div>
    );
  }

  if (fetchError || !tool) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-destructive text-lg">AI tool not found</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/marketplace/ai-tools")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to AI Tools
          </Button>
        </div>
      </div>
    );
  }

  const tierColors = {
    community: "bg-green-500/20 text-green-400 border-green-500/50",
    professional: "bg-blue-500/20 text-blue-400 border-blue-500/50",
    enterprise: "bg-purple-500/20 text-purple-400 border-purple-500/50",
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/50 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button
            variant="ghost"
            onClick={() => router.push("/marketplace/ai-tools")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to AI Tools
          </Button>

          <div className="flex items-start justify-between mt-4">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center">
                  <Zap className="h-6 w-6 text-primary" />
                </div>
                <div>
                  <h1 className="text-3xl font-bold">{tool.tool_name}</h1>
                  <p className="text-muted-foreground">by {tool.plugin_name}</p>
                </div>
              </div>
              <p className="text-muted-foreground mt-2">{tool.description}</p>

              <div className="flex items-center gap-4 mt-4">
                <Badge
                  className={tierColors[tool.required_tier]}
                >
                  <Shield className="h-3 w-3 mr-1" />
                  {tool.required_tier}
                </Badge>
                <Badge variant="outline">{tool.type}</Badge>
                {tool.is_enabled ? (
                  <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    Enabled
                  </Badge>
                ) : (
                  <Badge variant="outline" className="bg-destructive/20 text-destructive">
                    <XCircle className="h-3 w-3 mr-1" />
                    Disabled
                  </Badge>
                )}
              </div>
            </div>

            <Button
              size="lg"
              onClick={handleTest}
              disabled={loading || !tool.is_enabled}
              className="gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Testing...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Test Tool
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Left Column - Test Interface */}
          <div className="lg:col-span-2 space-y-6">
            {/* Tool Parameters */}
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Test Tool</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Provide parameters and test the tool functionality
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                {tool.parameters && Object.keys(tool.parameters).length > 0 ? (
                  Object.entries(tool.parameters).map(([key, schema]: [string, any]) => (
                    <div key={key}>
                      <Label htmlFor={key}>
                        {schema.title || key}
                        {schema.required && <span className="text-destructive ml-1">*</span>}
                      </Label>
                      {schema.type === "boolean" && (
                        <select
                          id={key}
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          value={params[key] || ""}
                          onChange={(e) => setParams({ ...params, [key]: e.target.value === "true" })}
                        >
                          <option value="">Select...</option>
                          <option value="true">True</option>
                          <option value="false">False</option>
                        </select>
                      )}
                      {schema.type === "string" && (
                        <Input
                          id={key}
                          type="text"
                          placeholder={schema.description || `Enter ${key}`}
                          value={params[key] || ""}
                          onChange={(e) => setParams({ ...params, [key]: e.target.value })}
                        />
                      )}
                      {schema.type === "number" && (
                        <Input
                          id={key}
                          type="number"
                          placeholder={schema.description || `Enter ${key}`}
                          value={params[key] || ""}
                          onChange={(e) => setParams({ ...params, [key]: parseFloat(e.target.value) })}
                        />
                      )}
                      {schema.type === "array" && (
                        <Input
                          id={key}
                          type="text"
                          placeholder="Comma-separated values"
                          value={params[key]?.join(", ") || ""}
                          onChange={(e) => setParams({ ...params, [key]: e.target.value.split(", ").filter(Boolean) })}
                        />
                      )}
                      {schema.type === "object" && (
                        <textarea
                          id={key}
                          className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          placeholder={schema.description || `Enter JSON for ${key}`}
                          value={params[key] || ""}
                          onChange={(e) => setParams({ ...params, [key]: JSON.parse(e.target.value) })}
                        />
                      )}
                      {schema.description && (
                        <p className="text-xs text-muted-foreground">{schema.description}</p>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Settings className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p>This tool does not require any parameters.</p>
                  </div>
                )}

                {/* Error */}
                {error && (
                  <div className="bg-destructive/10 border border-destructive/50 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <XCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="font-semibold text-destructive">Error</p>
                        <p className="text-sm text-destructive/80 mt-1">{error}</p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Result */}
                {result && (
                  <div className="bg-green-500/10 border border-green-500/50 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="font-semibold text-green-400">Success</p>
                        <pre className="text-xs bg-muted p-3 rounded mt-2 overflow-auto max-h-64">
                          {JSON.stringify(result, null, 2)}
                        </pre>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Response Format */}
            {tool.response_format && (
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>Expected Response Format</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="text-xs bg-muted p-4 rounded overflow-auto max-h-64">
                    {JSON.stringify(tool.response_format, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Column - Technical Info */}
          <div className="space-y-6">
            {/* Technical Details */}
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Technical Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Endpoint:</span>
                  <code className="text-xs bg-muted px-2 py-1 rounded">{tool.endpoint}</code>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Method:</span>
                  <Badge variant="outline">{tool.method}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Type:</span>
                  <Badge variant="outline">{tool.type}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Required Tier:</span>
                  <Badge className={tierColors[tool.required_tier]}>{tool.required_tier}</Badge>
                </div>
                {tool.category && (
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Category:</span>
                    <Badge variant="outline">{tool.category}</Badge>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Configuration */}
            {tool.configuration_schema && (
              <Card className="border-border bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>Configuration Schema</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="text-xs bg-muted p-4 rounded overflow-auto max-h-64">
                    {JSON.stringify(tool.configuration_schema, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            )}

            {/* Code Example */}
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Code Example</CardTitle>
                  <Button variant="outline" size="sm" onClick={handleCopyCode}>
                    {copied ? (
                      <>
                        <Check className="h-4 w-4 mr-1" />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-1" />
                        Copy
                      </>
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <pre className="text-xs bg-muted p-4 rounded overflow-auto max-h-64">
                  {generateCodeExample()}
                </pre>
              </CardContent>
            </Card>

            {/* Actions */}
            <Card className="border-border bg-card/50 backdrop-blur">
              <CardHeader>
                <CardTitle>Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button variant="outline" className="w-full justify-start" disabled={!tool.is_enabled}>
                  <Settings className="h-4 w-4 mr-2" />
                  Configure Tool
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => router.push(`/marketplace/plugins/${tool.plugin_id}`)}
                >
                  <Zap className="h-4 w-4 mr-2" />
                  View Plugin
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
