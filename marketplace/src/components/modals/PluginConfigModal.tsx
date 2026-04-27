"use client";

import { useState, useEffect } from "react";
import { X, CheckCircle2, Loader2, Save } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { pluginsManagementApi } from "@/lib/api/plugins-management";
import { Plugin } from "@/lib/types/plugin";

interface PluginConfigModalProps {
  plugin: Plugin;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export default function PluginConfigModal({ plugin, isOpen, onClose, onSuccess }: PluginConfigModalProps) {
  const [config, setConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (isOpen && plugin.configuration_schema?.default_configuration) {
      setConfig(plugin.configuration_schema.default_configuration);
    }
  }, [isOpen, plugin]);

  if (!isOpen) return null;

  const handleSave = async () => {
    setLoading(true);
    setError(null);

    try {
      await pluginsManagementApi.configurePlugin(plugin.id, config);
      setSuccess(true);
      setTimeout(() => {
        onClose();
        onSuccess?.();
      }, 1500);
    } catch (err: any) {
      setError(err.message || "Configuration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleConfigChange = (key: string, value: any) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-lg shadow-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div>
            <h2 className="text-2xl font-bold">Configure {plugin.display_name}</h2>
            <p className="text-sm text-muted-foreground mt-1">Update plugin settings and preferences</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="p-6">
          {success ? (
            <div className="text-center py-12">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-500/20 text-green-400 mb-4">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <h3 className="text-xl font-semibold mb-2">Configuration Saved!</h3>
              <p className="text-muted-foreground">Plugin configuration has been updated successfully.</p>
            </div>
          ) : (
            <>
              {/* Configuration Fields */}
              {plugin.configuration_schema?.fields && plugin.configuration_schema.fields.length > 0 ? (
                <div className="space-y-4">
                  {plugin.configuration_schema.fields.map((field) => (
                    <div key={field.name}>
                      <Label htmlFor={field.name}>
                        {field.label || field.name}
                        {field.required && <span className="text-destructive ml-1">*</span>}
                      </Label>

                      {field.type === "text" && (
                        <Input
                          id={field.name}
                          type="text"
                          placeholder={field.placeholder || `Enter ${field.label || field.name}`}
                          value={config[field.name] || ""}
                          onChange={(e) => handleConfigChange(field.name, e.target.value)}
                        />
                      )}

                      {field.type === "password" && (
                        <Input
                          id={field.name}
                          type="password"
                          placeholder={field.placeholder || `Enter ${field.label || field.name}`}
                          value={config[field.name] || ""}
                          onChange={(e) => handleConfigChange(field.name, e.target.value)}
                        />
                      )}

                      {field.type === "number" && (
                        <Input
                          id={field.name}
                          type="number"
                          placeholder={field.placeholder || `Enter ${field.label || field.name}`}
                          value={config[field.name] || ""}
                          onChange={(e) => handleConfigChange(field.name, parseFloat(e.target.value))}
                        />
                      )}

                      {field.type === "boolean" && (
                        <select
                          id={field.name}
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          value={config[field.name]?.toString() || ""}
                          onChange={(e) => handleConfigChange(field.name, e.target.value === "true")}
                        >
                          <option value="">Select...</option>
                          <option value="true">True</option>
                          <option value="false">False</option>
                        </select>
                      )}

                      {field.description && (
                        <p className="text-xs text-muted-foreground mt-1">{field.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <p>This plugin does not require any configuration.</p>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="mt-4 bg-destructive/10 border border-destructive/50 rounded-lg p-4">
                  <p className="text-sm text-destructive">{error}</p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!success && (
          <div className="flex justify-end gap-2 p-6 border-t border-border">
            <Button variant="outline" onClick={onClose} disabled={loading}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Save Configuration
                </>
              )}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
