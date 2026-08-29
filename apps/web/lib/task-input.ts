/**
 * Pure helpers for turning raw Task Composer text into the TWO concepts the
 * rest of the system needs:
 *
 *   - displayTitle: a short first-line summary for UI / Activity Feed.
 *   - content:      the COMPLETE exact user task (multi-line instructions),
 *                   sent verbatim to the backend so ATLAS's planner always
 *                   receives the full content, never just the first line.
 *
 * The content is never truncated to the first line; only the display title is
 * shortened (and only for display).
 */
export interface TaskParts {
  displayTitle: string;
  content: string;
}

/** Display titles longer than this are ellipsized for the UI. */
export const TITLE_MAX = 96;

export function taskInputParts(fullText: string): TaskParts {
  const content = fullText.trim();
  const firstLine = content.split("\n")[0].trim();
  const displayTitle =
    firstLine.length > TITLE_MAX
      ? `${firstLine.slice(0, TITLE_MAX - 3)}...`
      : firstLine;
  return { displayTitle, content };
}
