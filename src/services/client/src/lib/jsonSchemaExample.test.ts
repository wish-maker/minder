import { describe, expect, it } from "vitest";

import { exampleForSchema } from "./jsonSchemaExample";

describe("exampleForSchema", () => {
  it("returns an empty object for a schema with no properties", () => {
    expect(exampleForSchema(undefined)).toEqual({});
    expect(exampleForSchema({ type: "object" })).toEqual({});
  });

  it("fills type-appropriate placeholders per property", () => {
    const result = exampleForSchema({
      type: "object",
      properties: {
        name: { type: "string" },
        count: { type: "integer" },
        active: { type: "boolean" },
      },
    });
    expect(result).toEqual({ name: "", count: 0, active: false });
  });

  it("prefers an explicit example, then default, then the first enum value", () => {
    const result = exampleForSchema({
      type: "object",
      properties: {
        withExample: { type: "string", example: "bitcoin" },
        withDefault: { type: "number", default: 42 },
        withEnum: { type: "string", enum: ["low", "medium", "high"] },
      },
    });
    expect(result).toEqual({
      withExample: "bitcoin",
      withDefault: 42,
      withEnum: "low",
    });
  });

  it("recurses into array items and nested objects", () => {
    const result = exampleForSchema({
      type: "object",
      properties: {
        tags: { type: "array", items: { type: "string" } },
        nested: {
          type: "object",
          properties: { inner: { type: "boolean" } },
        },
      },
    });
    expect(result).toEqual({ tags: [""], nested: { inner: false } });
  });
});
