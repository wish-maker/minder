import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { type Bundle } from "../lib/bundles";
import { BundleCard } from "./BundleCard";

function makeBundle(overrides: Partial<Bundle> = {}): Bundle {
  return {
    name: "core",
    core: true,
    enabled: true,
    claims: [],
    services: [
      { name: "postgres", active: true, claimants: ["core"], image: "postgres:16" },
      { name: "redis", active: false, claimants: ["core"], image: "redis:7" },
    ],
    ...overrides,
  };
}

/** The active/inactive dot next to each service is color-only and
 * aria-hidden -- without a text alternative a screen-reader user has no way
 * to tell which services in a bundle are actually running. */
describe("BundleCard service status text alternative", () => {
  afterEach(cleanup);

  it("exposes an 'Active'/'Inactive' text alternative for each service's status dot", () => {
    render(
      <BundleCard
        bundle={makeBundle()}
        token="tok"
        isAdmin={false}
        onChanged={() => {}}
      />,
    );
    expect(screen.getByText("Active")).toBeTruthy();
    expect(screen.getByText("Inactive")).toBeTruthy();
  });
});
