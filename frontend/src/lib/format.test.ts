import { slugify, delta, duration, pct, pts, tokens, usd } from "./format";

describe("format helpers", () => {
  it("formats ratios as percentages", () => {
    expect(pct(0.625)).toBe("62.5%");
    expect(pct(1)).toBe("100.0%");
    expect(pct(0)).toBe("0.0%");
    expect(pct(null)).toBe("—");
  });

  it("formats points and tokens", () => {
    expect(pts(8)).toBe("8 pt");
    expect(tokens(12345)).toBe("12,345");
    expect(tokens(0)).toBe("0");
  });

  it("uses 4 decimals below one dollar and 2 from one dollar", () => {
    expect(usd(0.04)).toBe("$0.0400");
    expect(usd(0)).toBe("$0.0000");
    expect(usd(0.9999)).toBe("$0.9999");
    expect(usd(1)).toBe("$1.00");
    expect(usd(12.345)).toBe("$12.35");
  });

  it("formats durations", () => {
    expect(duration(45)).toBe("45s");
    expect(duration(125)).toBe("2m 05s");
    expect(duration(0)).toBe("0s");
    expect(duration(-3)).toBe("0s");
  });

  describe("delta", () => {
    it("is null when a value is missing", () => {
      expect(delta(null, 1, true)).toBeNull();
      expect(delta(1, null, true)).toBeNull();
    });

    it("shows numbers with a sign and a real minus", () => {
      expect(delta(7, 5, true)).toEqual({ text: "+2", direction: "up", good: true });
      expect(delta(2, 5, true)).toEqual({ text: "−3", direction: "down", good: false });
      expect(delta(5.5, 5, true)?.text).toBe("+0.50");
    });

    it("judges good and bad by the direction that is wanted", () => {
      expect(delta(1, 3, false)).toEqual({ text: "−2", direction: "down", good: true });
      expect(delta(3, 1, false)).toEqual({ text: "+2", direction: "up", good: false });
    });

    it("is flat when nothing changed", () => {
      expect(delta(5, 5, true)).toEqual({ text: "±0", direction: "flat", good: null });
      expect(delta(0.5, 0.5004, true, "ratio")?.direction).toBe("flat");
    });

    it("shows ratio changes in percentage points", () => {
      expect(delta(1, 0.625, true, "ratio")).toEqual({
        text: "+37.5 pp",
        direction: "up",
        good: true,
      });
      expect(delta(0.5, 0.75, true, "ratio")?.text).toBe("−25.0 pp");
    });

    it("shows money changes", () => {
      expect(delta(0.06, 0.04, false, "usd")).toEqual({
        text: "+$0.0200",
        direction: "up",
        good: false,
      });
    });
  });
});


describe("slugify", () => {
  it("makes a safe file name stem", () => {
    expect(slugify("Todo app")).toBe("todo-app");
    expect(slugify("  Library / Loans! ")).toBe("library-loans");
    expect(slugify("***")).toBe("project");
  });
});
