"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Play, Code, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { AITool } from "@/lib/types/plugin";

interface AIToolTestInterfaceProps {
  tool: AITool;
  onTest?: (toolId: string, params: Record<string, any>) => Promise<any>;
}

export default function AIToolTestInterface({ tool, onTest }: AIToolTestInterfaceProps) {
  const [params, setParams] = useState<Record<string, any>>({});
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);

  const handleTest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = onTest ? await onTest(tool.id, params) : { success: true, result: "Test successful" };
      setResult(response);
    } catch (err: any) {
      setError(err.message || "Test failed");
    } finally {
      setLoading(false);
    }
  };

  const renderParameters = () => {
    if (!tool.parameters || Object.keys(tool.parameters).length === 0) {
      return <p className="text-sm text-muted-foreground">This tool does not require any parameters.</p>;
    }

    return Object.entries(tool.parameters).map(([key, schema]: [string, any]) => (
      <div key={key} className="space-y-2">
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
            placeholder={`Comma-separated values`}
            value={params[key]?.join(", ") || ""}
            onChange={(e) => setParams({ ...params, [key]: e.target.value.split(", ").filter(Boolean) })}
          />
        )}
        {schema.description && (
          <p className="text-xs text-muted-foreground">{schema.description}</p>
        )}
      </div>
    ));
  };

  return (
    <Card className="border-border bg-card/50 backdrop-blur">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="text-lg">{tool.tool_name}</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">{tool.description}</p>
          </div>
          <Badge
            className={
              tool.required_tier === "community"
                ? "bg-green-500/20 text-green-400 border-green-500/50"
                : tool.required_tier === "professional"
                ? "bg-blue-500/20 text-blue-400 border-blue-500/50"
                : "bg-purple-500/20 text-purple-400 border-purple-500/50"
            }
          >
            {tool.required_tier}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Tool Metadata */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Type:</span>
            <Badge variant="outline" className="ml-2">{tool.type}</Badge>
          </div>
          <div>
            <span className="text-muted-foreground">Method:</span>
            <Badge variant="outline" className="ml-2">{tool.method}</Badge>
          </div>
          <div className="col-span-2">
            <span className="text-muted-foreground">Endpoint:</span>
            <code className="ml-2 text-xs bg-muted px-2 py-1 rounded">{tool.endpoint}</code>
          </div>
        </div>

        {/* Parameters */}
        <div>
          <h3 className="font-semibold mb-3">Parameters</h3>
          <div className="space-y-4">{renderParameters()}</div>
        </div>

        {/* Test Button */}
        <Button onClick={handleTest} disabled={loading || !tool.is_enabled} className="w-full">
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Testing...
            </>
          ) : (
            <>
              <Play className="mr-2 h-4 w-4" />
              Test Tool
            </>
          )}
        </Button>

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
          <div className="bg-success/10 border border-success/50 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="flex items-center justify-between mb-2">
                  <p className="font-semibold text-green-400">Success</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowJson(!showJson)}
                    className="gap-1"
                  >
                    <Code className="h-4 w-4" />
                    {showJson ? "Hide" : "Show"} JSON
                  </Button>
                </div>
                {showJson ? (
                  <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-64">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Tool executed successfully. Click "Show JSON" to view the full response.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Response Format */}
        {tool.response_format && (
          <div>
            <h3 className="font-semibold mb-3">Expected Response Format</h3>
            <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-48">
              {JSON.stringify(tool.response_format, null, 2)}
            </pre>
          </div>
        )}

        {/* Configuration */}
        {tool.configuration_schema && (
          <div>
            <h3 className="font-semibold mb-3">Configuration Schema</h3>
            <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-48">
              {JSON.stringify(tool.configuration_schema, null, 2)}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
