"""
MVP Plugin Manifest Schema

Minimal schema for webhook → store-vector plugins.
Manifest supplies PARAMETERS only - no code execution.
"""

# MVP Manifest Schema (JSON Schema Draft 07)
MVP_MANIFEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Minder MVP Plugin Manifest",
    "type": "object",
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {
            "type": "string",
            "enum": ["minder.dev/v1alpha1"],
            "description": "API version for the manifest",
        },
        "kind": {"type": "string", "enum": ["Plugin"], "description": "Resource kind"},
        "metadata": {
            "type": "object",
            "required": ["name", "version"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9-]*$",
                    "minLength": 2,
                    "maxLength": 63,
                    "description": "Plugin name (lowercase, alphanumeric, hyphens)",
                },
                "version": {
                    "type": "string",
                    "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+$",
                    "description": "Semantic version",
                },
                "description": {
                    "type": "string",
                    "maxLength": 500,
                    "description": "Short description",
                },
            },
        },
        "spec": {
            "type": "object",
            "required": ["trigger", "action"],
            "properties": {
                "trigger": {
                    "type": "object",
                    "required": ["type"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["webhook"],
                            "description": "Trigger type - only webhook supported in MVP",
                        },
                        "webhook": {
                            "type": "object",
                            "required": ["path"],
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "pattern": "^/[a-z0-9-/]+$",
                                    "minLength": 2,
                                    "maxLength": 100,
                                    "description": "Webhook path (e.g., /discord/webhook)",
                                },
                                "method": {
                                    "type": "string",
                                    "enum": ["POST"],
                                    "default": "POST",
                                },
                                "secretRef": {
                                    "type": "string",
                                    "pattern": "^[a-z][a-z0-9._-]*$",
                                    "description": "Reference to secret in secrets store",
                                },
                            },
                        },
                    },
                },
                "action": {
                    "type": "object",
                    "required": ["type", "store"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["store-vector"],
                            "description": "Action type - only store-vector supported in MVP",
                        },
                        "store": {
                            "type": "object",
                            "required": ["collection", "input"],
                            "description": "Vector storage configuration",
                            "properties": {
                                "collection": {
                                    "type": "string",
                                    "pattern": "^[a-z][a-z0-9-_]*$",
                                    "minLength": 3,
                                    "maxLength": 63,
                                    "description": "Qdrant collection name",
                                },
                                "input": {
                                    "type": "object",
                                    "required": ["text"],
                                    "properties": {
                                        "text": {
                                            "type": "string",
                                            "description": "Template for text to embed (e.g., {{ .content }})",
                                        },
                                        "metadata": {
                                            "type": "object",
                                            "description": "Additional metadata to store with vector",
                                        },
                                    },
                                },
                                "embedModel": {
                                    "type": "string",
                                    "enum": [
                                        "all-minilm",
                                        "nomic-embed-text",
                                        "mxbai-embed-large",
                                    ],
                                    "default": "all-minilm",
                                    "description": "Embedding model to use",
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

# Example MVP manifest
DISCORD_INGESTOR_EXAMPLE = """
apiVersion: minder.dev/v1alpha1
kind: Plugin
metadata:
  name: discord-ingestor
  version: 0.1.0
  description: Ingest Discord messages to Qdrant
spec:
  trigger:
    type: webhook
    webhook:
      path: /discord/webhook
      secretRef: discord.webhook.secret
  action:
    type: store-vector
    store:
      collection: discord-messages
      input:
        text: "{{ .content }}"
        metadata:
          author: "{{ .author.username }}"
          timestamp: "{{ .timestamp }}"
"""
