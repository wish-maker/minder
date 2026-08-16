import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AutoRouterStatsCard } from "./RagPipelinesPage";

// AutoRouterStatsCard is a pure presentational component (GET /v1/rag/decision-stats
// analytics, #707) — test its state branches directly by prop, no page mount needed.
describe("AutoRouterStatsCard", () => {
  afterEach(() => cleanup());

  it("renders nothing when stats are absent (deploy-skew graceful null)", () => {
    const { container } = render(<AutoRouterStatsCard stats={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when the auto engine is unavailable", () => {
    const { container } = render(
      <AutoRouterStatsCard
        stats={{
          available: false,
          total_decisions: 0,
          strategy_distribution: {},
          complexity_distribution: {},
          avg_confidence: null,
        }}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the empty note when available but no auto queries ran yet", () => {
    render(
      <AutoRouterStatsCard
        stats={{
          available: true,
          total_decisions: 0,
          strategy_distribution: {},
          complexity_distribution: {},
          avg_confidence: null,
        }}
      />,
    );
    expect(screen.getByText(/No/i)).toBeTruthy();
    expect(screen.getByText(/0 decisions recorded/i)).toBeTruthy();
  });

  it("renders the distributions and avg confidence when populated", () => {
    render(
      <AutoRouterStatsCard
        stats={{
          available: true,
          total_decisions: 3,
          strategy_distribution: { hybrid: 2, standard: 1 },
          complexity_distribution: { moderate: 2, simple: 1 },
          avg_confidence: 0.8,
        }}
      />,
    );
    expect(screen.getByText(/3 decisions recorded/i)).toBeTruthy();
    expect(screen.getByText("hybrid: 2")).toBeTruthy();
    expect(screen.getByText("standard: 1")).toBeTruthy();
    expect(screen.getByText("moderate: 2")).toBeTruthy();
    // avg_confidence 0.8 → "80%"
    expect(screen.getByText("80%")).toBeTruthy();
  });
});
