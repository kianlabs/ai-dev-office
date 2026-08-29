import { describe, expect, it } from "vitest";

import { taskInputParts, TITLE_MAX } from "../lib/task-input";

describe("taskInputParts — full content vs display title", () => {
  it("keeps the complete multi-line content (never truncates to first line)", () => {
    const text =
      "WAJIB libatkan semua specialist secara berurutan:\n" +
      "1. SCOUT riset penyebab bug login.\n" +
      "2. FORGE perbaiki bug login.\n" +
      "3. QA jalankan test.\n" +
      "4. PULSE pantau runtime setelah perbaikan.";
    const { content } = taskInputParts(text);
    expect(content).toBe(text.trim());
    expect(content).toContain("4. PULSE pantau runtime setelah perbaikan.");
    expect(content.split("\n").length).toBe(5);
  });

  it("uses the first line as the display title without altering the content", () => {
    const text = "WAJIB libatkan semua specialist secara berurutan:\n\n1. SCOUT ...\n2. FORGE ...\n3. QA ...\n4. PULSE ...";
    const { displayTitle, content } = taskInputParts(text);
    expect(displayTitle).toBe("WAJIB libatkan semua specialist secara berurutan:");
    expect(content).toBe(text.trim());
  });

  it("ellipsizes only an over-long display title, never the content", () => {
    const firstLine = "x".repeat(TITLE_MAX + 10);
    const text = `${firstLine}\nsecond line with details`;
    const { displayTitle, content } = taskInputParts(text);
    expect(displayTitle).toEqual(`${firstLine.slice(0, TITLE_MAX - 3)}...`);
    expect(content).toBe(text.trim());
    expect(content).toContain("second line with details");
  });

  it("preserves blank lines and numbered lists in the content", () => {
    const text = "Libatkan semua specialist:\n\n\n1. SCOUT riset dulu.\n2. FORGE implementasi.\n3. QA uji.\n4. PULSE pantau.\n\n";
    const { content } = taskInputParts(text);
    expect(content).toContain("1. SCOUT");
    expect(content).toContain("4. PULSE");
  });

  it("preserves Unicode / Bahasa Indonesia characters verbatim", () => {
    const text = "Libatkan semua specialist 🔍:\nSCOUT → telusuri kode dengan hati-hati.\nQA → periksa fungsi mémoir.";
    const { content } = taskInputParts(text);
    expect(content).toBe(text.trim());
    expect(content).toContain("🔍");
    expect(content).toContain("→");
    expect(content).toContain("mémoir");
  });
});
