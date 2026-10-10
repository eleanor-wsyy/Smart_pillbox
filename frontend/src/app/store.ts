export type SlotKey = "Morning" | "Noon" | "Evening";
export const slots: SlotKey[] = ["Morning", "Noon", "Evening"];
export const labels: Record<SlotKey, string> = { Morning: "早上", Noon: "中午", Evening: "晚上" };
export type Member = { id: string; name: string; role: "primary" | "temporary" };
export type Plan = { id: string; slot: SlotKey; name: string; dose: string; count: number; frequency: string; confirmedAt: string };
export type Medicine = { id: string; name: string; quantity: number; expiry: string; handledAt?: string };
export type LocalEvent = { id: string; at: string; type: "family" | "plan" | "review" | "expiry" | "inventory"; message: string };
export type SlotSnapshot = { slot: SlotKey; count: number; expected: number; status: string };
export type Handover = { id: string; fromId: string; fromName: string; toId: string; toName: string; createdAt: string; confirmedAt?: string; endedAt?: string; note: string; planSnapshot: Plan[]; slotSnapshot: SlotSnapshot[] | null; reminders: string[] };
export type Review = { id: string; at: string; slot: SlotKey; count: number; expected: number; planName: string; imageName?: string; result: string; passed: boolean };
export type LoadingRecord = { id: string; at: string; actor: string; slots: { slot: SlotKey; count: number; expected: number; planName: string }[]; image: string };
export type Data = { loadings: LoadingRecord[]; members: Member[]; plans: Plan[]; medicines: Medicine[]; handovers: Handover[]; reviews: Review[]; events: LocalEvent[] };
const key = "smart-pillbox-care-v1";
export const blank = (): Data => ({ loadings: [], members: [], plans: [], medicines: [], handovers: [], reviews: [], events: [] });
export function load(): Data {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    if (!value || typeof value !== "object") return blank();
    const result = blank();
    for (const field of Object.keys(result) as (keyof Data)[]) {
      if (Array.isArray(value[field])) (result as unknown as Record<string, unknown>)[field] = value[field];
    }
    return result;
  } catch { return blank(); }
}
export function save(data: Data): void { localStorage.setItem(key, JSON.stringify(data)); }
export function newId(): string { return crypto.randomUUID(); }
export function logEvent(data: Data, type: LocalEvent["type"], message: string): Data {
  return { ...data, events: [{ id: newId(), at: new Date().toISOString(), type, message }, ...data.events].slice(0, 300) };
}
export function expiryDays(date: string): number {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const [y, m, d] = date.split("-").map(Number);
  return Math.round((new Date(y, m - 1, d).getTime() - start.getTime()) / 86400000);
}
export function expiryState(item: Medicine): "expired" | "soon" | "ok" {
  const days = expiryDays(item.expiry);
  return days < 0 ? "expired" : days <= 30 ? "soon" : "ok";
}
