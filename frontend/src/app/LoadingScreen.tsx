import { useState } from "react";
import { ImagePlus, Trash2 } from "lucide-react";
import { expiryState, labels, logEvent, newId, slots, type Data, type SlotKey } from "./store";

type SlotState = { pill_count: number; expected_count: number; confidence: number; present: boolean };
type Props = { data: Data; status: { slots: Record<SlotKey, SlotState> } | null; change: (d: Data) => boolean };
const ink = "#252c29", muted = "#777d78", green = "#315e51";
const card: React.CSSProperties = { background: "white", border: "1px solid #e9e9e2", borderRadius: 16, padding: 18, marginBottom: 12 };
const small: React.CSSProperties = { color: muted, fontSize: 12, lineHeight: 1.6 };
const btn: React.CSSProperties = { background: green, color: "white", border: 0, borderRadius: 9, padding: "12px 14px", font: "inherit", fontWeight: 600, cursor: "pointer" };
const counts = (data: Data, slot: SlotKey) => data.plans.filter(p => p.slot === slot).reduce((n,p) => n+p.count, 0);
const stamp = (at: string) => new Date(at).toLocaleString("zh-CN", { hour12: false });
async function compress(file: File): Promise<string> {
  if (!file.type.startsWith("image/")) throw new Error("请选择图片文件");
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, 960 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("浏览器无法处理图片");
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", .64);
  } finally { bitmap.close(); }
}
export function LoadingScreen({ data, status, change }: Props) {
  const [selected, setSelected] = useState<SlotKey[]>([]);
  const [photo, setPhoto] = useState("");
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const active = data.handovers.find(h => h.confirmedAt && !h.endedAt);
  const actor = active?.toName || data.members.find(m => m.role === "primary")?.name || "";
  const issues = selected.flatMap(slot => {
    if (!status) return [];
    const device = status.slots[slot], planned = counts(data, slot);
    if (!data.plans.some(p => p.slot === slot)) return [`${labels[slot]}：没有已确认计划，不能记录为已装药`];
    const expired = data.plans.filter(p => p.slot === slot).some(p => data.medicines.some(m => !m.handledAt && m.name === p.name && expiryState(m) === "expired"));
    if (expired) return [`${labels[slot]}：有对应的过期库存，请先处理`];
    if (device.expected_count !== planned) return [`${labels[slot]}：设备计划与本机计划不同步`];
    if (device.pill_count !== planned) return [`${labels[slot]}：检测 ${device.pill_count} 粒，计划 ${planned} 粒`];
    if (planned && (!device.present || device.confidence < .28)) return [`${labels[slot]}：设备识别不稳定，请检查药格`];
    return [];
  });
  const ready = !!actor && !!status && selected.length > 0 && !!photo && !working && !issues.length;
  function toggle(slot: SlotKey) { setSelected(prev => slots.filter(s => s === slot ? !prev.includes(s) : prev.includes(s))); setMessage(""); }
  async function pick(file?: File) {
    if (!file) return;
    setWorking(true); setMessage("");
    try { setPhoto(await compress(file)); }
    catch (error) { setPhoto(""); setMessage(error instanceof Error ? error.message : "图片处理失败，请重试"); }
    finally { setWorking(false); }
  }
  function commit() {
    if (!ready || !status) return;
    const record = { id: newId(), at: new Date().toISOString(), actor, slots: selected.map(slot => ({ slot, count: status.slots[slot].pill_count, expected: counts(data, slot), planName: data.plans.filter(p => p.slot === slot).map(p => p.name).join("、") || "无计划" })), image: photo };
    if (change(logEvent({ ...data, loadings: [record, ...data.loadings].slice(0, 8) }, "review", `${actor}记录装药：${selected.map(s => labels[s]).join("、")}（不代表已服药）`))) {
      setSelected([]); setPhoto(""); setMessage("装药记录已保存在本机。");
    } else setMessage("本机存储空间不足，照片未保存。请清理旧记录后重试。");
  }
  function remove(id: string) {
    if (!window.confirm("删除这条本机装药记录及照片？此操作无法撤销。")) return;
    if (change(logEvent({ ...data, loadings: data.loadings.filter(r => r.id !== id) }, "review", "删除一条本机装药记录及照片"))) setMessage("记录已删除。");
  }
  return <div style={{ color: ink }}>
    <header style={{ margin: "8px 2px 20px" }}><div style={{ ...small, color: green, letterSpacing: 1.2 }}>FAMILY CARE / 03</div><h2 style={{ fontSize: 25, margin: "6px 0" }}>装药记录</h2><p style={small}>装完拍一张照片，勾选本次装好的药格。无需填写其他信息。</p></header>
    <section style={card}><div style={{ ...small, color: green }}>01 / 选择药格</div><h3 style={{ fontSize: 17, margin: "8px 0 14px" }}>这次装了哪些？</h3><div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>{slots.map(slot => <button key={slot} type="button" aria-pressed={selected.includes(slot)} onClick={() => toggle(slot)} style={{ ...btn, background: selected.includes(slot) ? green : "#f4f5f1", color: selected.includes(slot) ? "white" : ink, border: selected.includes(slot) ? "1px solid #315e51" : "1px solid #e4e6df" }}>{labels[slot]}</button>)}</div>
      {selected.map(slot => <div key={slot} style={{ padding: "11px 0", borderBottom: "1px solid #f0f0eb", fontSize: 13 }}><strong>{labels[slot]}</strong>　{data.plans.filter(p => p.slot === slot).map(p => `${p.name} ${p.count}粒`).join("、") || "无计划，应为空"}<div style={small}>计划 {counts(data, slot)} 粒 · 设备 {status ? `${status.slots[slot].pill_count} 粒` : "未连接"}</div></div>)}
    </section>
    <section style={card}><div style={{ ...small, color: green }}>02 / 留下照片</div><h3 style={{ fontSize: 17, margin: "8px 0 14px" }}>拍下装好的药盒</h3><label style={{ display: "flex", alignItems: "center", gap: 10, padding: 14, border: "1px dashed #abbcb1", borderRadius: 10, cursor: "pointer", color: green, fontSize: 14 }}><ImagePlus size={20} />{photo ? "重新拍照或选择图片" : "拍照或选择一张图片"}<input aria-label="装药照片" type="file" accept="image/*" capture="environment" style={{ position: "absolute", width: 1, height: 1, opacity: 0 }} onChange={e => { void pick(e.target.files?.[0]); e.target.value = ""; }} /></label>{photo && <img src={photo} alt="本次装药照片预览" style={{ width: "100%", maxHeight: 240, objectFit: "contain", marginTop: 12, borderRadius: 8 }} />}<p style={small}>照片仅存当前浏览器，不上传服务器；最多保留最近 8 条。</p></section>
    <section style={card}><div style={{ ...small, color: green }}>03 / 保存记录</div><div style={{ margin: "12px 0", fontSize: 14, lineHeight: 2 }}>记录人　<strong>{actor || "未设置照看人"}</strong><br />装药格　<strong>{selected.length ? selected.map(s => labels[s]).join("、") : "待选择"}</strong><br />时间　<strong>保存时自动记录</strong></div>
      {!actor && <p role="alert" style={{ color: "#916523", fontSize: 13 }}>请先在家庭圈设置主照顾人。</p>}{!status && <p role="alert" style={{ color: "#916523", fontSize: 13 }}>设备未连接，暂不能核对数量和保存记录。</p>}{issues.map(issue => <p role="alert" key={issue} style={{ color: "#ad4942", fontSize: 13 }}>{issue}</p>)}<button style={{ ...btn, width: "100%", opacity: ready ? 1 : .55 }} disabled={!ready} onClick={commit}>{working ? "正在处理图片…" : "保存这次装药"}</button><p style={small}>记录人由当前照看人自动带入，并非登录身份验证。系统仅核对所选药格总数，不能确认药品品种、批次或是否吞服；请对照医嘱和包装人工检查。</p>
    </section>
    {message && <p role="status" style={{ color: "#916523", fontSize: 13 }}>{message}</p>}
    <h3 style={{ fontSize: 17, margin: "23px 2px 12px" }}>最近的装药记录</h3>{!data.loadings.length && <section style={card}><p style={small}>还没有装药记录。</p></section>}
    {data.loadings.map(record => <section style={card} key={record.id}><div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}><div><strong>{record.slots.map(s => labels[s.slot]).join("、")}</strong><div style={small}>{record.actor} · {stamp(record.at)}</div></div><button aria-label="删除装药记录" title="删除记录" onClick={() => remove(record.id)} style={{ ...btn, background: "#f4f5f1", color: green, padding: 8 }}><Trash2 size={16} /></button></div><div style={{ ...small, margin: "10px 0" }}>{record.slots.map(s => `${labels[s.slot]}：${s.planName} · ${s.count}/${s.expected}粒`).join("；")}</div><a href={record.image} target="_blank" rel="noreferrer" aria-label="查看装药照片"><img src={record.image} alt={`${record.actor}的装药记录照片`} style={{ width: "100%", maxHeight: 220, objectFit: "contain", borderRadius: 8, background: "#f4f4f0" }} /></a></section>)}
    {!!data.reviews.length && <section style={card}><strong>旧版逐格复核</strong><p style={small}>旧记录只保存了文件名，没有保存照片；以下仅供查看，不作为本次装药记录。</p>{data.reviews.slice(0, 5).map(r => <div key={r.id} style={{ ...small, padding: "6px 0" }}>{labels[r.slot]} · {stamp(r.at)} · {r.result}</div>)}</section>}
  </div>;
}
