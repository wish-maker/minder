// Generates a plausible example value from a JSON Schema (the OpenAI/Ollama
// function-calling `parameters` shape every AI tool declares) so a user
// gets a runnable starting point instead of a blank form. Deliberately
// simple -- type-appropriate placeholders, not real semantic understanding
// of what a parameter means.

interface JsonSchemaProperty {
  type?: string;
  enum?: unknown[];
  default?: unknown;
  example?: unknown;
  description?: string;
  properties?: Record<string, JsonSchemaProperty>;
  items?: JsonSchemaProperty;
}

interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

function exampleForProperty(prop: JsonSchemaProperty): unknown {
  if (prop.example !== undefined) return prop.example;
  if (prop.default !== undefined) return prop.default;
  if (prop.enum && prop.enum.length > 0) return prop.enum[0];
  switch (prop.type) {
    case "string":
      return "";
    case "number":
    case "integer":
      return 0;
    case "boolean":
      return false;
    case "array":
      return prop.items ? [exampleForProperty(prop.items)] : [];
    case "object":
      return exampleForSchema({
        type: "object",
        properties: prop.properties,
      });
    default:
      return "";
  }
}

/** Builds a JSON-serializable example object for a tool's whole `parameters`
 * schema -- one key per declared property, each filled with a type-appropriate
 * placeholder (or the schema's own `example`/`default`/first `enum` value when
 * present). A tool with no properties returns `{}` -- still valid, runnable
 * input for a parameter-less action. */
export function exampleForSchema(schema: JsonSchema | undefined): Record<string, unknown> {
  if (!schema?.properties) return {};
  const out: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(schema.properties)) {
    out[key] = exampleForProperty(prop);
  }
  return out;
}
