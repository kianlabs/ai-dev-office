/**
 * Pure seated-delegation DIALOGUE resolver.
 *
 * Turns a delegated role into a SHORT alternating conversation between ATLAS
 * (coordinator) and the target agent — max 4 lines, one speaker at a time,
 * each line ~1.3–1.8s. The conversation is a pure projection of the role so it
 * is trivially testable and the copy lives in ONE place where it can later be
 * swapped for task-aware text (e.g. derived from the real ATLAS activity).
 *
 * Note this handles ONLY dialogue text/timeline + the "should a conversation
 * START?" decision. It does NOT move agents or touch seated behavior; the
 * seated micro-machine stays as-is.
 */
import type { HandoffRole } from "../navigation/handoff";
import { WORK_STATE } from "../navigation/handoff";
import type { AgentId } from "../navigation/waypoints";

export type DialogueSpeaker = HandoffRole | "atlas";

export interface DialogueLine {
  speaker: DialogueSpeaker;
  text: string;
  /** How long the line stays visible (seconds), within [1.3, 1.8]. */
  seconds: number;
}

export const MAX_DIALOGUE_LINES = 4;
export const MIN_LINE_SECONDS = 1.3;
export const MAX_LINE_SECONDS = 1.8;
export const DEFAULT_LINE_SECONDS = 1.5;

/** Clamp a line duration into the allowed 1.3–1.8s window. */
export function clampLineSeconds(seconds: number): number {
  if (seconds < MIN_LINE_SECONDS) return MIN_LINE_SECONDS;
  if (seconds > MAX_LINE_SECONDS) return MAX_LINE_SECONDS;
  return seconds;
}

/**
 * Role → dialogue copy (Bahasa Indonesia). Each script is exactly 4 lines
 * alternating ATLAS / target ("atlas", role, atlas, role). Replace the strings
 * here to make conversations task-aware later without touching any wiring.
 */
const DIALOGUE_SCRIPTS: Record<HandoffRole, readonly string[]> = {
  scout: [
    "Scout, coba cek bagian ini dulu.",
    "Siap, saya telusuri.",
    "Fokus ke temuan yang paling penting.",
    "Oke, nanti saya rangkum.",
  ],
  forge: [
    "Forge, lanjut implementasikan ini.",
    "Siap, saya kerjakan.",
    "Jaga perubahannya tetap fokus.",
    "Oke, saya lanjut.",
  ],
  qa: [
    "QA, coba periksa hasil Forge.",
    "Siap, saya cek.",
    "Pastikan tidak ada regresi.",
    "Oke, saya verifikasi.",
  ],
  pulse: [
    "Pulse, cek kondisi runtime.",
    "Siap, saya pantau.",
    "Kabari kalau ada masalah.",
    "Oke, saya awasi.",
  ],
};

/**
 * The full alternating conversation for a role (max MAX_DIALOGUE_LINES lines).
 * Even indexes = ATLAS speaking, odd indexes = the target agent speaking.
 */
export function roleDialogue(role: HandoffRole): DialogueLine[] {
  return DIALOGUE_SCRIPTS[role]
    .slice(0, MAX_DIALOGUE_LINES)
    .map((text, i) => ({
      speaker: i % 2 === 0 ? "atlas" : role,
      text,
      seconds: clampLineSeconds(DEFAULT_LINE_SECONDS),
    }));
}

/**
 * Cumulative display time (seconds) for finishing the Nth line, i.e. lines
 * [0, n). Returns 0 for n <= 0. Useful for scheduling the timeline.
 */
export function cumulativeDialogueSeconds(
  dialogue: DialogueLine[],
  n: number,
): number {
  let total = 0;
  for (let i = 0; i < n && i < dialogue.length; i++) total += dialogue[i].seconds;
  return total;
}

/**
 * Whether a conversation should START given the previous delegated target and
 * the next detected one. A conversation only starts on a NEW delegation: a
 * repeated (unchanged) dispatch or a cleared (null) target does NOT replay.
 * This is the pure decision the hook + tests rely on to avoid replay on
 * repeated semantic updates.
 */
export function shouldStartConversation(
  previous: HandoffRole | null,
  next: HandoffRole | null,
): boolean {
  return next !== null && next !== previous;
}

/**
 * The persistent compact work status an agent settles into AFTER its
 * conversation resolves (Meneliti... / Menulis kode... / Menguji... / Memantau...).
 * Thin wrapper over the shared WORK_STATE so dialogue tests can assert the
 * conversation's terminal status for each role.
 */
export function conversationWorkStatus(role: HandoffRole): string {
  return WORK_STATE[role as AgentId].label;
}
