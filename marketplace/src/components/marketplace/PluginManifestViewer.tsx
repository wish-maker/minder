"use client";

import { useState } from "react";
import {
  FileCode,
  Settings,
  Zap,
  Package,
  Shield,
  ChevronDown,
  ChevronRight,
  Copy,
  CheckCircle2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface PluginManifestViewerProps {
  manifest: any;
  pluginName: string;
}

interface ToolDefinition {
  name: string;
  display_name: string;
  description: string;
  tool_type: string;
  category: string;
  endpoint_path: string;
  http_method: string;
  required_tier: string;
  parameters_schema?: Record<string, any>;
  response_schema?: Record<string, any>;
  configuration_schema?: Record<string, any>;
  default_configuration?: Record<string, any>;
  is_default_enabled: boolean;
  tags: string[];
  version: string;
}

interface DependencySpec {
  name: string;
  version: string;
  optional: boolean;
}

export default function PluginManifestViewer({
  manifest,
  pluginName,
}: PluginManifestViewerProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(["overview", "ai_tools"])
  );
  const [copiedItem, setCopiedItem] = useState<string | null>(null);

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(section)) {
        newSet.delete(section);
      } else {
        newSet.add(section);
      }
      return newSet;
    });
  };

  const copyToClipboard = (text: string, item: string) => {
    navigator.clipboard.writeText(text);
    setCopiedItem(item);
    setTimeout(() => setCopiedItem(null), 2000);
  };

  const aiTools = manifest?.ai_tools?.tools || [];
  const dependencies = manifest?.dependencies || [];
  const configurationSchema = manifest?.configuration_schema?.properties || {};
  const defaultConfiguration = manifest?.default_configuration || {};

  const SectionHeader = ({
    section,
    title,
    icon: Icon,
    count,
    badge,
  }: {
    section: string;
    title: string;
    icon: any;
    count?: number;
    badge?: string;
  }) => {
    const isExpanded = expandedSections.has(section);
    return (
      <div
        className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 cursor-pointer transition-colors"
        onClick={() => toggleSection(section)}
      >
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium">{title}</span>
          {count !== undefined && (
            <Badge variant="secondary" className="text-xs">
              {count}
            </Badge>
          )}
          {badge && (
            <Badge variant="outline" className="text-xs">
              {badge}
            </Badge>
          )}
        </div>
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </div>
    );
  };

  return (
    <Card className="border-border bg-card/50 backdrop-blur">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileCode className="h-5 w-5" />
          Plugin Manifest
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Technical details about {pluginName} plugin structure and configuration
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Overview Section */}
        <div className="space-y-2">
          <SectionHeader
            section="overview"
            title="Overview"
            icon={Settings}
          />
          {expandedSections.has("overview") && (
            <div className="p-4 rounded-lg bg-muted/30 space-y-3">
              <div className="grid md:grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground">Name:</span>
                  <span className="ml-2 font-mono font-medium">
                    {manifest?.name}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Version:</span>
                  <span className="ml-2 font-mono">{manifest?.version}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Tier:</span>
                  <Badge
                    className={`ml-2 ${
                      manifest?.tier === "community"
                        ? "bg-green-500/20 text-green-400 border-green-500/50"
                        : manifest?.tier === "professional"
                        ? "bg-blue-500/20 text-blue-400 border-blue-500/50"
                        : "bg-purple-500/20 text-purple-400 border-purple-500/50"
                    }`}
                  >
                    {manifest?.tier}
                  </Badge>
                </div>
                <div>
                  <span className="text-muted-foreground">Python:</span>
                  <span className="ml-2 font-mono text-xs">
                    {manifest?.python_version || ">=3.11"}
                  </span>
                </div>
                <div className="md:col-span-2">
                  <span className="text-muted-foreground">Category:</span>
                  <span className="ml-2">{manifest?.category}</span>
                </div>
                <div className="md:col-span-2">
                  <span className="text-muted-foreground">License:</span>
                  <span className="ml-2 font-mono">{manifest?.license}</span>
                </div>
              </div>

              {manifest?.homepage && (
                <div className="pt-2">
                  <a
                    href={manifest.homepage}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline text-sm"
                  >
                    Homepage →
                  </a>
                </div>
              )}
              {manifest?.repository && (
                <div>
                  <a
                    href={manifest.repository}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline text-sm"
                  >
                    Repository →
                  </a>
                </div>
              )}
            </div>
          )}
        </div>

        {/* AI Tools Section */}
        <div className="space-y-2">
          <SectionHeader
            section="ai_tools"
            title="AI Tools"
            icon={Zap}
            count={aiTools.length}
          />
          {expandedSections.has("ai_tools") && (
            <div className="space-y-3">
              {aiTools.map((tool: ToolDefinition, index: number) => (
                <div
                  key={index}
                  className="p-4 rounded-lg bg-muted/30 border border-border"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-semibold">{tool.display_name}</h4>
                        <Badge variant="outline" className="text-xs">
                          {tool.tool_type}
                        </Badge>
                        <Badge
                          className={`text-xs ${
                            tool.required_tier === "community"
                              ? "bg-green-500/20 text-green-400 border-green-500/50"
                              : tool.required_tier === "professional"
                              ? "bg-blue-500/20 text-blue-400 border-blue-500/50"
                              : "bg-purple-500/20 text-purple-400 border-purple-500/50"
                          }`}
                        >
                          {tool.required_tier}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mb-2">
                        {tool.description}
                      </p>
                      <div className="flex items-center gap-3 text-xs font-mono text-muted-foreground">
                        <span>{tool.http_method}</span>
                        <span>{tool.endpoint_path}</span>
                        <span>v{tool.version}</span>
                      </div>
                    </div>
                    {tool.is_default_enabled && (
                      <Badge className="bg-green-500/20 text-green-400 border-green-500/50">
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        Default Enabled
                      </Badge>
                    )}
                  </div>

                  {/* Parameters */}
                  {tool.parameters_schema && Object.keys(tool.parameters_schema).length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs font-semibold mb-2">Parameters:</p>
                      <div className="space-y-1">
                        {Object.entries(tool.parameters_schema).map(([paramName, param]: [string, any]) => (
                          <div
                            key={paramName}
                            className="flex items-center gap-2 text-xs bg-background rounded px-2 py-1"
                          >
                            <span className="font-mono text-primary">{paramName}</span>
                            <span className="text-muted-foreground">{param.type}</span>
                            {param.required && (
                              <span className="text-destructive">*</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Configuration */}
                  {tool.configuration_schema && Object.keys(tool.configuration_schema).length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs font-semibold mb-2">Configuration:</p>
                      <div className="bg-background rounded p-2">
                        <pre className="text-xs font-mono text-muted-foreground overflow-x-auto">
                          {JSON.stringify(tool.configuration_schema, null, 2)}
                        </pre>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2 h-6 text-xs"
                          onClick={() =>
                            copyToClipboard(
                              JSON.stringify(tool.configuration_schema, null, 2),
                              `tool-${tool.name}-config`
                            )
                          }
                        >
                          {copiedItem === `tool-${tool.name}-config` ? (
                            <>
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                              Copied!
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3 mr-1" />
                              Copy Schema
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Tags */}
                  {tool.tags && tool.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {tool.tags.map((tag) => (
                        <Badge key={tag} variant="outline" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Dependencies Section */}
        <div className="space-y-2">
          <SectionHeader
            section="dependencies"
            title="Dependencies"
            icon={Package}
            count={dependencies.length}
          />
          {expandedSections.has("dependencies") && (
            <div className="p-4 rounded-lg bg-muted/30">
              {dependencies.length > 0 ? (
                <div className="space-y-2">
                  {dependencies.map((dep: DependencySpec, index: number) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 rounded bg-background"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm">{dep.name}</span>
                        <Badge variant="outline" className="text-xs">
                          {dep.version}
                        </Badge>
                      </div>
                      {dep.optional && (
                        <Badge variant="secondary" className="text-xs">
                          Optional
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No dependencies specified
                </p>
              )}
            </div>
          )}
        </div>

        {/* Configuration Schema Section */}
        <div className="space-y-2">
          <SectionHeader
            section="configuration"
            title="Configuration Schema"
            icon={Settings}
            count={Object.keys(configurationSchema).length}
            badge={Object.keys(defaultConfiguration).length > 0 ? "Has Defaults" : undefined}
          />
          {expandedSections.has("configuration") && (
            <div className="p-4 rounded-lg bg-muted/30 space-y-3">
              {Object.keys(configurationSchema).length > 0 ? (
                <div className="space-y-2">
                  <p className="text-xs font-semibold">Schema Definition:</p>
                  <div className="bg-background rounded p-3">
                    <pre className="text-xs font-mono text-muted-foreground overflow-x-auto">
                      {JSON.stringify(configurationSchema, null, 2)}
                    </pre>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-2 h-6 text-xs"
                      onClick={() =>
                        copyToClipboard(
                          JSON.stringify(configurationSchema, null, 2),
                          "config-schema"
                        )
                      }
                    >
                      {copiedItem === "config-schema" ? (
                        <>
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Copied!
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3 mr-1" />
                          Copy Schema
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No configuration schema defined
                </p>
              )}

              {Object.keys(defaultConfiguration).length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold">Default Values:</p>
                  <div className="bg-background rounded p-3">
                    <pre className="text-xs font-mono text-muted-foreground overflow-x-auto">
                      {JSON.stringify(defaultConfiguration, null, 2)}
                    </pre>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-2 h-6 text-xs"
                      onClick={() =>
                        copyToClipboard(
                          JSON.stringify(defaultConfiguration, null, 2),
                          "default-config"
                        )
                      }
                    >
                      {copiedItem === "default-config" ? (
                        <>
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Copied!
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3 mr-1" />
                          Copy Defaults
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Lifecycle Section */}
        <div className="space-y-2">
          <SectionHeader
            section="lifecycle"
            title="Lifecycle"
            icon={Shield}
          />
          {expandedSections.has("lifecycle") && (
            <div className="p-4 rounded-lg bg-muted/30 space-y-3">
              <div className="grid md:grid-cols-2 gap-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Default Enabled:</span>
                  <Badge
                    variant={manifest?.is_default_enabled ? "default" : "secondary"}
                    className="text-xs"
                  >
                    {manifest?.is_default_enabled ? "Yes" : "No"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Can Be Disabled:</span>
                  <Badge
                    variant={manifest?.can_be_disabled ? "default" : "secondary"}
                    className="text-xs"
                  >
                    {manifest?.can_be_disabled ? "Yes" : "No"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between md:col-span-2">
                  <span className="text-muted-foreground">Requires Restart:</span>
                  <Badge
                    variant={manifest?.requires_restart ? "destructive" : "secondary"}
                    className="text-xs"
                  >
                    {manifest?.requires_restart ? "Yes" : "No"}
                  </Badge>
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
