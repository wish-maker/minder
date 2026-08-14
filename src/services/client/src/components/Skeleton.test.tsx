import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Skeleton } from "./Skeleton";

describe("Skeleton", () => {
  it("renders a div by default (block-level placeholder)", () => {
    const { container } = render(<Skeleton className="h-8 w-12" />);
    expect(container.firstChild?.nodeName).toBe("DIV");
  });

  it("renders a span when inline -- required inside <p>/<h2> to avoid invalid HTML nesting", () => {
    // Regression test: HomePage's PrimaryActionCard used to nest the default
    // <div> Skeleton inside a <p>/<h2>, which is invalid HTML and triggered
    // React's validateDOMNesting warning (found via a real headless-browser
    // pass, not just code review).
    const { container } = render(<Skeleton inline className="h-4 w-72" />);
    expect(container.firstChild?.nodeName).toBe("SPAN");
  });
});
