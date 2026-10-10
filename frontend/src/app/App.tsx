/// <reference types="vite/client" />
import { useCallback, useEffect, useState } from "react";
import { Home, Camera, Bell, CalendarDays, Settings, Users, FileText, PackageCheck, Pill, RefreshCw, AlertTriangle, CheckCircle2, ArrowLeft, ArrowRight } from "lucide-react";
import { createWorker } from "tesseract.js";
import { LoadingScreen } from "./LoadingScreen";
import { blank, expiryDays, expiryState, labels, load, logEvent, newId, save, slots, type Data, type Handover, type Medicine, type Plan, type SlotKey } from "./store";

type Screen = "dashboard" | "live" | "alerts" | "history" | "settings" | "family" | "records" | "review" | "inventory";
type ApiEvent = { id: string; time: string; kind: string; message: string };
type ApiSlot = { key: SlotKey; label: string; pill_count: number; expected_count: number; confidence: number; status: string; status_label: string; present: boolean };
type Status = { online: boolean; current_period: SlotKey; current_period_label: string; system_state: string; updated_at: string; slots: Record<SlotKey, ApiSlot>; next_reminder: { label: string; time: string } };
type Feed = { id: string; at: number; text: string; category: "device" | "family" | "plan" | "review" | "expiry" | "inventory"; severity?: string; timeLabel: string };
const base = import.meta.env.VITE_API_BASE ?? "";
const palette = { ink: "#30392f", muted: "#566353", teal: "#3e6651", pale: "#edf2df", warning: "#8b602e", error: "#aa504b" };
const card: React.CSSProperties = { background: "rgba(255, 255, 251, .84)", border: "1px solid rgba(255,255,255,.75)", borderRadius: 16, padding: 18, boxShadow: "0 8px 24px rgba(84,80,65,.045)", marginBottom: 12 };
const field: React.CSSProperties = { width: "100%", padding: "10px 12px", border: "1px solid #d6ddce", borderRadius: 9, background: "rgba(255,255,252,.9)", font: "inherit", color: palette.ink, margin: "6px 0" };
const button: React.CSSProperties = { border: 0, borderRadius: 9, background: palette.teal, color: "white", padding: "10px 14px", font: "inherit", fontWeight: 600, cursor: "pointer" };
const secondary: React.CSSProperties = { ...button, background: palette.pale, color: palette.teal };
const small: React.CSSProperties = { fontSize: 12, color: palette.muted, lineHeight: 1.55 };
function dateLabel(value: string | number) { const d = new Date(value); return Number.isNaN(d.getTime()) ? "时间未知" : d.toLocaleString("zh-CN", { hour12: false }); }
function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) { return <section className={`surface-card ${className}`} style={card}>{children}</section>; }
function Title({ title, desc }: { title: string; desc?: string }) { return <header className="page-title"><h2>{title}</h2>{desc && <p>{desc}</p>}</header>; }
function Empty({ children }: { children: React.ReactNode }) { return <p style={{ ...small, margin: "10px 0" }}>{children}</p>; }
function useDevice() {
  const [status, setStatus] = useState<Status | null>(null);
  const [events, setEvents] = useState<ApiEvent[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([fetch(`${base}/api/status`, { cache: "no-store" }), fetch(`${base}/api/events`, { cache: "no-store" })]);
      if (!s.ok || !e.ok) throw new Error(`HTTP ${s.status}/${e.status}`);
      const next = await s.json(); const eventBody = await e.json();
      if (!next.slots || !Array.isArray(eventBody.events)) throw new Error("接口响应格式错误");
      setStatus(next); setEvents(eventBody.events); setError("");
      return next as Status;
    } catch (e) { setStatus(null); setEvents([]); setError(`后端连接失败：${e instanceof Error ? e.message : "网络错误"}`); return null; }
  }, []);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => { void refresh(); }, 1800); return () => clearInterval(timer); }, [refresh]);
  const post = async (path: string, body?: unknown) => {
    setBusy(true);
    try {
      const r = await fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await refresh(); return true;
    } catch (e) { setError(`操作失败：${e instanceof Error ? e.message : "网络错误"}`); return false; }
    finally { setBusy(false); }
  };
  return { status, events, error, busy, refresh, post };
}
function merged(events: ApiEvent[], data: Data): Feed[] {
  const remote: Feed[] = events.map(e => ({ id: `api-${e.id}`, at: /^\d{16,}$/.test(e.id) ? Number(e.id) / 1e6 : 0, text: e.message, category: "device", severity: e.kind, timeLabel: e.time }));
  const local: Feed[] = data.events.map(e => ({ id: e.id, at: new Date(e.at).getTime(), text: e.message, category: e.type, timeLabel: dateLabel(e.at) }));
  return [...remote, ...local].sort((a, b) => b.at - a.at);
}
function FeedRows({ items }: { items: Feed[] }) { return items.length ? <>{items.map(e => <Panel key={e.id}><div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><strong style={{ color: e.severity === "critical" ? palette.error : e.severity === "warning" ? palette.warning : palette.ink, fontSize: 13, overflowWrap: "anywhere" }}>{e.text}</strong></div><div style={small}>{e.category === "device" ? "设备事件" : ({ family: "家庭圈", plan: "用药计划", review: "装药记录", expiry: "保质期", inventory: "药品库存" } as Record<string,string>)[e.category]} · {e.timeLabel}</div></Panel>)}</> : <Panel><Empty>暂无真实记录。</Empty></Panel>; }
const counts = (plans: Plan[]) => Object.fromEntries(slots.map(s => [s, plans.filter(p => p.slot === s).reduce((sum, p) => sum + p.count, 0)])) as Record<SlotKey,number>;
function Dashboard({ data, status, navigate, alerts }: { data: Data; status: Status | null; navigate: (s: Screen) => void; alerts: number }) {
  const current = data.handovers.find(h => h.confirmedAt && !h.endedAt);
  const caretaker = current ? `${current.toName}（临时）` : data.members.find(m => m.role === "primary")?.name || "未设置";
  const expiring = data.medicines.filter(m => !m.handledAt && expiryState(m) !== "ok").length;
  const shortcuts = ([ ["家庭圈", "family", Users], ["病历录入", "records", FileText], ["装药记录", "review", PackageCheck], ["药品保质期", "inventory", Pill] ] as const);
  return <>
    <header className="dashboard-hero">
      <div className="eyebrow">SMART PILLBOX <span aria-hidden="true">/</span> 家庭照看</div>
      <h1>用药看护</h1>
      <p>让每一次照看，都更有把握。</p>
      <div className="hero-meta"><span><Users size={15} aria-hidden="true" />照看人：{caretaker}</span><span className={status ? "device-connected" : "device-disconnected"}>{status ? <CheckCircle2 size={15} aria-hidden="true" /> : <AlertTriangle size={15} aria-hidden="true" />}{status ? `设备已连接 · ${status.current_period_label}药格` : "设备未连接"}</span></div>
    </header>
    <main className="dashboard-content">
      <div className="section-label"><h2>当前药格</h2><span>设备实时状态</span></div>
      <Panel className="slot-panel">
        {status ? slots.map(k => <div className="slot-row" key={k}>
          <div className="slot-row-heading"><strong>{labels[k]}</strong><span className="slot-status">{status.slots[k].status_label}</span></div>
          <div className="slot-quantity">检测到 <strong>{status.slots[k].pill_count}</strong> 粒<span>计划 {status.slots[k].expected_count} 粒</span></div>
        </div>) : <Empty>连接后才能查看药格实时数据。</Empty>}
        <p className="support-note">药格数量变化只表示取药，不代表已经吞服。</p>
      </Panel>
      <div className="section-label"><h2>用药计划</h2><span>已人工核对</span></div>
      <Panel className="plan-panel">{data.plans.length ? data.plans.map(p => <div className="plan-row" key={p.id}><span className="plan-slot">{labels[p.slot]}</span><div><strong>{p.name}</strong><small>{p.dose} · {p.count} 粒</small></div></div>) : <Empty>暂无已人工核对的用药计划。</Empty>}</Panel>
      <div className="section-label"><h2>待关注</h2></div>
      <Panel className="attention-panel"><div className="attention-summary"><div><strong>{alerts}</strong><span>设备警报</span></div><div><strong>{expiring}</strong><span>临期/过期库存</span></div></div><button className="attention-action" style={secondary} onClick={() => navigate("alerts")}>查看提醒 <ArrowRight size={17} aria-hidden="true" /></button></Panel>
      <div className="section-label"><h2>常用功能</h2></div>
      <div className="quick-actions">{shortcuts.map(([label, to, Icon]) => <button className="quick-action" key={to} onClick={() => navigate(to)}><Icon size={21} strokeWidth={1.8} aria-hidden="true" /><span>{label}</span><ArrowRight size={15} aria-hidden="true" /></button>)}</div>
    </main>
  </>;
}
function Family({ data, status, change }: { data: Data; status: Status | null; change: (next: Data) => void }) {
  const [name, setName] = useState(""); const [role, setRole] = useState<"primary" | "temporary">("temporary");
  const [fromId, setFrom] = useState(""); const [toId, setTo] = useState(""); const [actor, setActor] = useState(""); const [note, setNote] = useState(""); const [message, setMessage] = useState("");
  const primary = data.members.filter(m => m.role === "primary"); const helpers = data.members.filter(m => m.role === "temporary");
  const pending = data.handovers.find(h => !h.confirmedAt && !h.endedAt);
  const active = data.handovers.find(h => h.confirmedAt && !h.endedAt);
  function add(e: React.FormEvent) { e.preventDefault(); const n = name.trim(); if (!n || (role === "primary" && primary.length)) { setMessage("请填写昵称；主照顾人只能设置一位。"); return; } change(logEvent({ ...data, members: [...data.members, { id: newId(), name: n, role }] }, "family", `添加家庭成员：${n}（${role === "primary" ? "主照顾人" : "临时照顾人"}）`)); setName(""); setMessage(""); }
  function create() {
    const from = primary.find(m => m.id === fromId); const to = helpers.find(m => m.id === toId);
    if (!from || !to || !status || pending || active) { setMessage("请选择双方；设备需连接，且不能存在未结束的交接。"); return; }
    const reminders = [...data.plans.map(p => `${labels[p.slot]}：${p.name} ${p.dose}（${p.count} 粒）`), ...data.medicines.filter(m => !m.handledAt && expiryState(m) !== "ok").map(m => `${m.name}：${expiryState(m) === "expired" ? "已过期" : "临期"}`)];
    const h: Handover = { id: newId(), fromId: from.id, fromName: from.name, toId: to.id, toName: to.name, createdAt: new Date().toISOString(), note: note.trim(), planSnapshot: data.plans.map(p => ({ ...p })), slotSnapshot: slots.map(slot => ({ slot, count: status.slots[slot].pill_count, expected: status.slots[slot].expected_count, status: status.slots[slot].status_label })), reminders };
    change(logEvent({ ...data, handovers: [h, ...data.handovers] }, "family", `${from.name}发起交接给${to.name}，等待接手人确认`)); setNote(""); setMessage("");
  }
  function confirm(h: Handover) { if (actor !== h.toId) { setMessage("请先选择交接单指定的接手人；本机演示不提供身份认证。"); return; } const at = new Date().toISOString(); change(logEvent({ ...data, handovers: data.handovers.map(x => x.id === h.id ? { ...x, confirmedAt: at } : x) }, "family", `${h.toName}已确认接手${h.fromName}的照看任务`)); setMessage(""); }
  return <><Title title="家庭圈" desc="单机共享设备演示：身份由操作人选择，无法验证真实身份。交接前请当面核对。" />
    <Panel><strong>家庭成员</strong>{data.members.length ? data.members.map(m => <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, fontSize: 13 }}><span>{m.name} · {m.role === "primary" ? "主照顾人" : "临时照顾人"}</span><button style={secondary} onClick={() => { if (data.handovers.some(h => !h.endedAt && (h.fromId === m.id || h.toId === m.id))) { setMessage("请先结束或处理相关交接。"); return; } change(logEvent({ ...data, members: data.members.filter(x => x.id !== m.id) }, "family", `删除成员：${m.name}`)); }}>删除</button></div>) : <Empty>暂无家庭成员。</Empty>}
    <form onSubmit={add}><input aria-label="成员昵称" placeholder="成员昵称" style={field} value={name} onChange={e => setName(e.target.value)} maxLength={30} /><select aria-label="成员角色" style={field} value={role} onChange={e => setRole(e.target.value as typeof role)}><option value="primary">主照顾人</option><option value="temporary">临时照顾人</option></select><button style={button}>添加成员</button></form></Panel>
    <Panel><strong>发起照看交接</strong><select aria-label="发起人" style={field} value={fromId} onChange={e => setFrom(e.target.value)}><option value="">选择发起人（主照顾人）</option>{primary.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select><select aria-label="接手人" style={field} value={toId} onChange={e => setTo(e.target.value)}><option value="">选择接手人</option>{helpers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select><textarea aria-label="注意事项" placeholder="注意事项（由家属填写，可留空）" style={{ ...field, minHeight: 64 }} value={note} onChange={e => setNote(e.target.value)} /><button style={button} onClick={create}>生成交接单</button></Panel>
    {data.handovers.map(h => <Panel key={h.id}><strong>{h.fromName} → {h.toName}</strong><div style={small}>发起：{dateLabel(h.createdAt)} · {h.endedAt ? `结束：${dateLabel(h.endedAt)}` : h.confirmedAt ? `确认：${dateLabel(h.confirmedAt)}` : "等待接手确认"}</div><p style={{ fontSize: 13 }}>注意事项：{h.note || "未填写"}</p><div style={{ fontSize: 13 }}>计划快照：{h.planSnapshot.length ? h.planSnapshot.map(p => `${labels[p.slot]} ${p.name} ${p.dose} ${p.count}粒`).join("；") : "暂无已核对计划"}</div><div style={{ fontSize: 13, marginTop: 6 }}>药格快照：{h.slotSnapshot?.map(s => `${labels[s.slot]} ${s.count}/${s.expected}粒（${s.status}）`).join("；") || "未连接，无法读取"}</div><div style={{ fontSize: 13, marginTop: 6 }}>待办提醒：{h.reminders.join("；") || "暂无已录入提醒"}</div>{!h.confirmedAt && !h.endedAt && <><select aria-label="当前操作人" style={field} value={actor} onChange={e => setActor(e.target.value)}><option value="">选择当前操作人</option>{data.members.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select><button style={button} onClick={() => confirm(h)}>我已了解，确认接手</button></>}{h.confirmedAt && !h.endedAt && <div style={{ marginTop: 10 }}><button style={secondary} onClick={() => change(logEvent({ ...data, handovers: data.handovers.map(x => x.id === h.id ? { ...x, endedAt: new Date().toISOString() } : x) }, "family", `${h.toName}结束临时照看，交回${h.fromName}`))}>结束交接</button></div>}</Panel>)}
    {message && <p role="alert" style={{ color: palette.error }}>{message}</p>}
  </>;
}
function parseOcrLine(line: string) {
  const text = line.trim();
  const doseMatch = text.match(/^(.{1,60}?)\s+(\d+(?:\.\d+)?\s*(?:片|粒|毫克|mg|tablets?|capsules?))/i);
  const freq = text.match(/(?:每日|每天|一日)\s*[一二三四1-4]\s*次?|once daily|twice daily/i);
  return { name: (doseMatch?.[1] || text).slice(0, 80), dose: doseMatch?.[2] || "", count: doseMatch ? Number(doseMatch[2].match(/^\d+/)?.[0] || 1) : 1, frequency: freq?.[0] || "" };
}
function Records({ data, change, post, connected }: { data: Data; change: (d: Data) => void; post: (p: string, body: unknown) => Promise<boolean>; connected: boolean }) {
  const [photo, setPhoto] = useState<File | null>(null); const [preview, setPreview] = useState(""); const [raw, setRaw] = useState(""); const [working, setWorking] = useState(false); const [msg, setMsg] = useState("");
  const [editing, setEditing] = useState(""); const [slot, setSlot] = useState<SlotKey | "">(""); const [name, setName] = useState(""); const [dose, setDose] = useState(""); const [count, setCount] = useState(1); const [frequency, setFrequency] = useState("");
  useEffect(() => { if (!photo) { setPreview(""); return; } const url = URL.createObjectURL(photo); setPreview(url); return () => URL.revokeObjectURL(url); }, [photo]);
  async function recognize() {
    if (!photo) return; setWorking(true); setMsg("正在运行真实 OCR，请等待中文语言包加载……"); setRaw("");
    let worker: Awaited<ReturnType<typeof createWorker>> | undefined;
    try { worker = await createWorker("chi_sim+eng"); const result = await worker.recognize(photo); const text = result.data.text.trim(); setRaw(text); if (text) { const draft = parseOcrLine(text.split(/\r?\n/).find(line => line.trim()) || ""); setName(draft.name); setDose(draft.dose); setFrequency(draft.frequency); setCount(draft.count); } setMsg(text ? "已生成首行候选草稿；请对照原图逐项核对修改，人工确认后才会生效。" : "未识别到文字，请人工录入。影像内容不会自动生成计划。"); }
    catch (e) { setMsg(`OCR 不可用，请对照照片手工录入：${e instanceof Error ? e.message : "识别失败"}`); }
    finally { await worker?.terminate(); setWorking(false); }
  }
  async function sync(plans: Plan[]) { if (!connected) { setMsg("计划已在本机保存；设备离线，数量尚未同步。连接后点击“同步数量”。"); return; } const ok = await post("/api/medplan", { counts: counts(plans) }); setMsg(ok ? "已保存并同步数量；药品身份仍需人工核对。" : "计划已在本机保存，后端数量同步失败，请重试。"); }
  function submit(e: React.FormEvent) {
    e.preventDefault(); const nm = name.trim(), ds = dose.trim(), fr = frequency.trim();
    if (!slot || !nm || !ds || !fr || !Number.isInteger(count) || count < 1 || count > 3) { setMsg("请填写药名、频次、剂量，数量为 1–3 粒；确认前请核对医嘱。"); return; }
    const item: Plan = { id: editing || newId(), slot, name: nm, dose: ds, count, frequency: fr, confirmedAt: new Date().toISOString() };
    const next = editing ? data.plans.map(p => p.id === editing ? item : p) : [...data.plans, item];
    if (counts(next)[slot] > 3) { setMsg("该格计划合计超过设备支持的 3 粒，请核对。"); return; }
    change(logEvent({ ...data, plans: next }, "plan", `人工核对${editing ? "更新" : "确认"}计划：${labels[slot]} ${nm} ${ds}，${count} 粒`));
    setEditing(""); setSlot(""); setName(""); setDose(""); setFrequency(""); setCount(1); void sync(next);
  }
  return <><Title title="病历拍照录入" desc="AI 仅转写原文；药名、频次、剂量和药格需家属逐项核对确认，不能作为处方使用。" />
    <Panel><label style={{ fontSize: 13, fontWeight: 600 }}>拍照或上传病历/用药说明<input aria-label="选择病历图片" type="file" accept="image/*" capture="environment" style={field} onChange={e => { setPhoto(e.target.files?.[0] || null); setRaw(""); }} /></label>{preview && <img alt="待核对的病历照片" src={preview} style={{ width: "100%", maxHeight: 240, objectFit: "contain", borderRadius: 12 }} />}<div style={small}>照片仅在当前页面临时预览，不会上传服务器或永久保存；OCR 语言包首次使用需联网。</div><button style={button} disabled={!photo || working} onClick={() => void recognize()}>{working ? "识别中……" : "真实 OCR 识别"}</button>{raw && <><div style={{ ...small, marginTop: 12 }}>OCR 原文（未经医学验证，可选择一行带入候选草稿，再逐项核对修改）：</div><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12, background: palette.pale, padding: 10 }}>{raw}</pre>{raw.split(/\r?\n/).filter(s => s.trim()).slice(0, 30).map((line, i) => <button key={i} style={{ ...secondary, margin: "0 6px 6px 0", fontSize: 11 }} onClick={() => { const draft = parseOcrLine(line); setName(draft.name); if (draft.dose) { setDose(draft.dose); setCount(draft.count); } if (draft.frequency) setFrequency(draft.frequency); }}>带入第 {i + 1} 行</button>)}</>}</Panel>
    <Panel><strong>{editing ? "修改并重新确认计划" : "结构化草稿 · 人工核对"}</strong><form onSubmit={submit}><select aria-label="用药时段" style={field} value={slot} onChange={e => setSlot(e.target.value as SlotKey)}><option value="">请选择药格</option>{slots.map(s => <option key={s} value={s}>{labels[s]}药格</option>)}</select><input aria-label="药名" style={field} placeholder="药名（对照原件填写）" value={name} onChange={e => setName(e.target.value)} maxLength={80} /><input aria-label="频次" style={field} placeholder="频次（例如：按医嘱填写）" value={frequency} onChange={e => setFrequency(e.target.value)} maxLength={80} /><input aria-label="剂量" style={field} placeholder="剂量（按医嘱填写）" value={dose} onChange={e => setDose(e.target.value)} maxLength={80} /><label style={small}>该格装药数量（粒）<input aria-label="该格数量" type="number" min="1" max="3" step="1" style={field} value={count} onChange={e => setCount(Number(e.target.value))} /></label><p style={small}>我已逐项对照原件核对；检测到取药并不等于已经服药。</p><button style={button}>人工核对并确认</button></form></Panel>
    <Panel><strong>已确认计划</strong>{data.plans.length ? data.plans.map(p => <div key={p.id} style={{ borderTop: "1px solid #e5e9dd", padding: "10px 0", fontSize: 13 }}>{labels[p.slot]} · {p.name} · {p.frequency} · {p.dose} · {p.count} 粒<div style={small}>确认：{dateLabel(p.confirmedAt)}</div><button style={{ ...secondary, margin: "6px 6px 0 0" }} onClick={() => { setEditing(p.id); setSlot(p.slot); setName(p.name); setDose(p.dose); setCount(p.count); setFrequency(p.frequency); }}>修改</button><button style={secondary} onClick={() => { const next = data.plans.filter(x => x.id !== p.id); change(logEvent({ ...data, plans: next }, "plan", `删除计划：${p.name}`)); void sync(next); }}>删除</button></div>) : <Empty>尚未确认任何用药计划。</Empty>}<button style={secondary} onClick={() => void sync(data.plans)}>同步数量到设备</button><div style={small}>当前 /api/period 仅切换时段；经人工确认的三个时段数量通过新增 /api/medplan 同步。</div></Panel>
    {msg && <p role="status" style={{ color: palette.warning, fontSize: 13 }}>{msg}</p>}
  </>;
}
function Inventory({ data, change }: { data: Data; change: (d: Data) => void }) {
  const [name, setName] = useState(""); const [quantity, setQuantity] = useState(1); const [expiry, setExpiry] = useState(""); const [error, setError] = useState("");
  function submit(e: React.FormEvent) { e.preventDefault(); if (!name.trim() || !expiry || !Number.isInteger(quantity) || quantity < 0) { setError("请填写药名、非负整数库存数量和有效期。"); return; } const med: Medicine = { id: newId(), name: name.trim(), quantity, expiry }; change(logEvent({ ...data, medicines: [med, ...data.medicines] }, "inventory", `录入库存：${med.name}，${med.quantity} 粒，有效期 ${med.expiry}`)); setName(""); setExpiry(""); setQuantity(1); setError(""); }
  return <><Title title="保质期管理" desc="过期药不可用于装药；临期（含当天，≤30 天）需人工复核。" /><Panel><strong>添加药品库存</strong><form onSubmit={submit}><input aria-label="库存药名" placeholder="药名" style={field} value={name} onChange={e => setName(e.target.value)} /><input aria-label="库存数量" type="number" min="0" step="1" style={field} value={quantity} onChange={e => setQuantity(Number(e.target.value))} /><label style={small}>有效期<input aria-label="有效期" type="date" style={field} value={expiry} onChange={e => setExpiry(e.target.value)} /></label><button style={button}>确认录入</button></form></Panel>{error && <p role="alert" style={{ color: palette.error }}>{error}</p>}{!data.medicines.length && <Panel><Empty>暂无录入的药品库存。</Empty></Panel>}{data.medicines.map(m => <Panel key={m.id}><div style={{ color: !m.handledAt && expiryState(m) === "expired" ? palette.error : palette.ink }}><strong>{m.name}</strong> · 库存 {m.quantity} 粒</div><div style={small}>有效期：{m.expiry} · {m.handledAt ? `已处理 ${dateLabel(m.handledAt)}` : expiryState(m) === "expired" ? "已过期，禁止装药" : expiryState(m) === "soon" ? `临期，剩余 ${expiryDays(m.expiry)} 天` : "未临期"}</div>{!m.handledAt && expiryState(m) !== "ok" && <button style={{ ...secondary, marginTop: 8 }} onClick={() => change(logEvent({ ...data, medicines: data.medicines.map(x => x.id === m.id ? { ...x, handledAt: new Date().toISOString() } : x) }, "expiry", `已标记处理${expiryState(m) === "expired" ? "过期" : "临期"}药品：${m.name}`))}>建议处理 · 标记已处理</button>}</Panel>)}</>;
}
function DeviceScreen({ status, post, busy, refresh }: { status: Status | null; post: (p: string, body?: unknown) => Promise<boolean>; busy: boolean; refresh: () => Promise<Status | null> }) { return <><Title title="药盒实时状态" desc="显示后端 OpenCV 模拟检测数据；本页不提供真实视频画面，也不判断吞咽。" /><Panel><button style={secondary} onClick={() => void refresh()}><RefreshCw size={14} /> 刷新</button>{!status ? <Empty>后端未连接，无法显示实时状态。</Empty> : <><p style={small}>更新时间：{dateLabel(status.updated_at)} · 当前时段：{status.current_period_label}</p>{slots.map(s => <div style={{ borderTop: "1px solid #e5e9dd", padding: "12px 0", fontSize: 13 }} key={s}><strong>{labels[s]}药格</strong> · 检测到 {status.slots[s].pill_count} 粒 / 设备计划 {status.slots[s].expected_count} 粒<br /><span style={small}>{status.slots[s].status_label} · 置信度 {status.slots[s].confidence}</span></div>)}</>}</Panel><Panel><strong>演示操作（真实调用后端模拟接口）</strong><p style={small}>只能模拟药格数量与时段，不能模拟“已服药”。</p>{slots.map(s => <div key={s} style={{ marginBottom: 14, fontSize: 13 }}><strong>{labels[s]}：</strong><button disabled={busy || !status} style={secondary} onClick={() => void post("/api/period", { period: s })}>设为当前</button>{[0,1,2,3].map(n => <button key={n} disabled={busy || !status} onClick={() => void post("/api/simulate/set", { slot: s, count: n })} style={{ ...secondary, margin: "5px 4px 0 0", padding: "6px 9px" }}>{n}粒</button>)}</div>)}<div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><button disabled={busy || !status} style={secondary} onClick={() => void post("/api/simulate/take", { slot: status?.current_period, count: 0 })}>模拟当前药格取空</button><button disabled={busy || !status} style={secondary} onClick={() => void post("/api/reset")}>重置模拟器</button></div><p style={small}>重置会清空后端设备事件；不会删除本机已核对的计划及历史，请按需重新同步数量。</p></Panel></>; }
function SettingsScreen({ data, post, busy, status }: { data: Data; post: (p: string, body?: unknown) => Promise<boolean>; busy: boolean; status: Status | null }) { return <><Title title="设置" desc="设备时段和演示控制；成员与计划请通过首页入口管理。" /><Panel><strong>当前时段</strong><p style={small}>{status ? status.current_period_label : "设备未连接"}</p>{slots.map(s => <button key={s} disabled={busy || !status} style={{ ...secondary, marginRight: 7 }} onClick={() => void post("/api/period", { period: s })}>{labels[s]}</button>)}</Panel><Panel><strong>本机数据</strong><p style={small}>成员 {data.members.length} 位、确认计划 {data.plans.length} 项、库存 {data.medicines.length} 项；存于当前浏览器 localStorage，不跨设备同步。</p><div style={small}>后端设备事件只保留最近 50 条且重启清空；本机操作记录最多 300 条。</div></Panel></>; }
function AlertsScreen({ events, data, status, refresh }: { events: ApiEvent[]; data: Data; status: Status | null; refresh: () => Promise<Status | null> }) {
  const alarms = events.filter(e => e.kind === "critical" || e.kind === "warning");
  const stock = data.medicines.filter(m => !m.handledAt && expiryState(m) !== "ok");
  return <><Title title="用药提醒" desc="仅显示后端实际警报和已录入库存推导的临期提醒；不推断是否吞服。" /><button style={{ ...secondary, marginBottom: 12 }} onClick={() => void refresh()}>刷新设备提醒</button>{!status && <Panel><span role="alert" style={{ color: palette.error }}>设备未连接：设备警报不可用，不代表没有警报。</span></Panel>}{stock.map(m => <Panel key={m.id}><AlertTriangle size={16} color={palette.warning} /> <strong>{m.name}：{expiryState(m) === "expired" ? "已过期，禁止装药" : `临期（${expiryDays(m.expiry)} 天）`}</strong><div style={small}>库存有效期：{m.expiry} · 请到保质期管理页处理</div></Panel>)}{status && alarms.map(e => <Panel key={e.id}><strong style={{ color: e.kind === "critical" ? palette.error : palette.warning }}>{e.kind === "critical" ? "严重警报" : "设备警告"}</strong><div style={{ fontSize: 13, marginTop: 8, overflowWrap: "anywhere" }}>{e.message}</div><div style={small}>设备时间：{e.time}（后端仅提供时分秒）</div></Panel>)}{status && !alarms.length && !stock.length && <Panel><Empty>暂无设备警报或临期库存提醒。</Empty></Panel>}</>;
}
function HistoryScreen({ feed, connected }: { feed: Feed[]; connected: boolean }) { const [tab, setTab] = useState("all"); const tabs = [["all","全部"],["device","设备"],["family","家庭圈"],["plan","计划"],["review","装药"],["expiry","保质期"],["inventory","库存"]]; return <><Title title="事件记录" desc="设备事件来自 /api/events；家庭圈等来自当前浏览器的真实操作记录。" />{!connected && <Panel><span role="alert" style={{ color: palette.error }}>设备连接失败：此时只显示本机记录，设备历史暂不可用。</span></Panel>}<div style={{ display: "flex", gap: 6, overflowX: "auto", marginBottom: 13 }}>{tabs.map(([id, label]) => <button key={id} style={tab === id ? button : secondary} onClick={() => setTab(id)}>{label}</button>)}</div><FeedRows items={tab === "all" ? feed : feed.filter(e => e.category === tab)} /></>; }
const navigation: { id: Screen; label: string; Icon: typeof Home }[] = [{ id: "dashboard", label: "首页", Icon: Home }, { id: "live", label: "药盒", Icon: Camera }, { id: "alerts", label: "提醒", Icon: Bell }, { id: "history", label: "记录", Icon: CalendarDays }, { id: "settings", label: "设置", Icon: Settings }];
export default function App() {
  const [screen, setScreen] = useState<Screen>("dashboard"); const [data, setData] = useState<Data>(() => { try { return load(); } catch { return blank(); } }); const [storageError, setStorageError] = useState("");
  const device = useDevice(); const feed = merged(device.events, data);
  const change = (next: Data): boolean => { try { save(next); setData(next); setStorageError(""); return true; } catch { setStorageError("浏览器本地存储不可用，本次操作未保存。请检查隐私模式或空间。 "); return false; } };
  const alarms = device.events.filter(e => e.kind === "critical" || e.kind === "warning").length;
  return <div className="app-shell" style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", fontFamily: "'Noto Sans SC','Microsoft YaHei',system-ui,sans-serif", color: palette.ink }}>
    <div className="app-canvas" style={{ width: "min(100%, 420px)", height: "min(100dvh, 860px)", minHeight: 500, display: "flex", flexDirection: "column", boxShadow: "0 14px 48px rgba(72,77,54,.12)", overflow: "hidden", position: "relative" }}>
      <div style={{ height: 6, flexShrink: 0, background: "rgba(85,117,74,.25)" }} />
      <div className="app-scroll" style={{ flex: 1, overflowY: "auto" }} key={screen}>
        {screen !== "dashboard" && <div className="back-wrap"><button className="back-button" style={secondary} onClick={() => setScreen("dashboard")}><ArrowLeft size={17} aria-hidden="true" />返回首页</button></div>}
        {(device.error || storageError) && <div role="alert" style={{ padding: "9px 16px", background: "rgba(255,244,237,.9)", color: palette.error, fontSize: 12 }}>{device.error || storageError}</div>}
        {screen === "dashboard" ? <Dashboard data={data} status={device.status} navigate={setScreen} alerts={alarms} /> : <div style={{ padding: "8px 16px 28px" }}>
          {screen === "live" && <DeviceScreen status={device.status} post={device.post} busy={device.busy} refresh={device.refresh} />}
          {screen === "alerts" && <AlertsScreen events={device.events} data={data} status={device.status} refresh={device.refresh} />}
          {screen === "history" && <HistoryScreen feed={feed} connected={!!device.status} />}
          {screen === "settings" && <SettingsScreen data={data} status={device.status} post={device.post} busy={device.busy} />}
          {screen === "family" && <Family data={data} status={device.status} change={change} />}
          {screen === "records" && <Records data={data} change={change} post={device.post} connected={!!device.status} />}
          {screen === "review" && <LoadingScreen data={data} status={device.status} change={change} />}
          {screen === "inventory" && <Inventory data={data} change={change} />}
        </div>}
      </div>
      <nav className="bottom-nav" aria-label="主导航">{navigation.map(({ id, label, Icon }) => { const active = screen === id; return <button className="nav-button" key={id} aria-current={active ? "page" : undefined} onClick={() => setScreen(id)}><Icon size={21} strokeWidth={active ? 2.2 : 1.8} aria-hidden="true" /><span>{label}</span>{id === "alerts" && alarms > 0 && <span className="nav-alert" aria-label={`${alarms} 条设备警报`} />}</button>; })}</nav>
    </div>
  </div>;
}
