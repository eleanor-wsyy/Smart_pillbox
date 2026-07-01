import { useState } from "react";
import {
  Home, Camera, Bell, Settings, CalendarDays,
  Phone, RefreshCw, ChevronRight, CheckCircle2,
  AlertOctagon, AlertTriangle, Info, X, Clock,
  Wifi, User, Activity, Check, Shield,
} from "lucide-react";

// ─── Design tokens ────────────────────────────────────────────────
const C = {
  bg: "linear-gradient(160deg, #E0EFF0 0%, #E8E7E2 48%, #E8E4F0 100%)",
  card: "rgba(255,255,255,0.72)",
  cardSolid: "#FFFFFF",
  teal: "#3A8882",
  tealBg: "rgba(234,244,243,0.85)",
  tealLight: "#C4E4E1",
  fg: "#182530",
  fgMid: "#3D5060",
  fgMuted: "#7A909E",
  border: "rgba(255,255,255,0.75)",
  borderSubtle: "rgba(24,38,47,0.07)",

  green: "#17A876",
  greenBg: "rgba(237,251,245,0.82)",

  amber: "#CC8A0A",
  amberBg: "rgba(254,248,236,0.82)",

  orange: "#C96500",
  orangeBg: "rgba(254,242,232,0.82)",

  red: "#C43030",
  redBg: "rgba(254,241,241,0.82)",
  redBorder: "#F5AAAA",
  orangeBorder: "#F5BF9A",
  amberBorder: "#F5D990",
  greenBorder: "#A8E5CC",
};

// ─── Glass styles ────────────────────────────────────────────────
const GLASS: React.CSSProperties = {
  background: C.card,
  backdropFilter: "blur(20px) saturate(180%)",
  WebkitBackdropFilter: "blur(20px) saturate(180%)",
  border: `1px solid ${C.border}`,
  boxShadow: "0 4px 28px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.04), inset 0 1px 0 rgba(255,255,255,0.9)",
};

const GLASS_DARK: React.CSSProperties = {
  background: "rgba(0,0,0,0.16)",
  backdropFilter: "blur(12px) saturate(150%)",
  WebkitBackdropFilter: "blur(12px) saturate(150%)",
  border: "1px solid rgba(255,255,255,0.22)",
};

const GLASS_TEAL: React.CSSProperties = {
  background: "rgba(234,244,243,0.75)",
  backdropFilter: "blur(14px)",
  WebkitBackdropFilter: "blur(14px)",
  border: "1px solid rgba(255,255,255,0.65)",
};

type Screen = "dashboard" | "live" | "alerts" | "history" | "settings";

const ALERTS = [
  {
    severity: "严重", sevColor: C.red, sevBg: C.redBg, sevBorder: C.redBorder,
    iconType: "octagon", title: "错误药格锁定",
    desc: "当前是早上时段，Roboflow 检测到晚上药格药丸移动，系统已阻断成功记录",
    time: "08:02", slot: "晚上药格",
    action: "立即放回药丸，等待系统恢复", resolved: false,
  },
  {
    severity: "警告", sevColor: C.orange, sevBg: C.orangeBg, sevBorder: C.orangeBorder,
    iconType: "triangle", title: "剂量异常",
    desc: "早上处方预期 2 粒，视觉检出 1 粒，暂不记录成功服药",
    time: "07:55", slot: "早上药格",
    action: "请检查药格，确认实际数量", resolved: false,
  },
  {
    severity: "提醒", sevColor: C.amber, sevBg: C.amberBg, sevBorder: C.amberBorder,
    iconType: "info", title: "动作闭环未完成",
    desc: "药格变空后等待 hand_to_mouth 与 swallow 双重确认",
    time: "07:58", slot: "早上药格",
    action: "提醒老人完成服药动作", resolved: false,
  },
  {
    severity: "待确认", sevColor: C.amber, sevBg: C.amberBg, sevBorder: C.amberBorder,
    iconType: "info", title: "视觉不确定",
    desc: "检测置信度低或摄像头画面被遮挡，系统暂停成功/失败判定",
    time: "08:04", slot: "摄像头画面",
    action: "调整药盒位置或摄像头角度", resolved: false,
  },
  {
    severity: "已解决", sevColor: C.green, sevBg: C.greenBg, sevBorder: C.greenBorder,
    iconType: "check", title: "错误药格已恢复",
    desc: "药丸已放回，系统从 RECOVERY 回到 MONITORING",
    time: "昨天 12:03", slot: "中午药格",
    action: "", resolved: true,
  },
];

const SAFETY_STATES = [
  { key: "MONITORING", label: "监控中", color: C.teal, bg: C.tealBg },
  { key: "LOCKED_WRONG_SLOT", label: "错误药格锁定", color: C.red, bg: C.redBg },
  { key: "WARNING_DOSAGE", label: "剂量异常", color: C.orange, bg: C.orangeBg },
  { key: "UNCERTAIN", label: "视觉不确定", color: C.amber, bg: C.amberBg },
  { key: "RECOVERY", label: "恢复流程", color: C.green, bg: C.greenBg },
];

// ─── Blob background per screen ──────────────────────────────────

function ScreenBlobs({ screen }: { screen: Screen }) {
  type Blob = { w: number; h: number; color: string; s: React.CSSProperties };
  const sets: Record<Screen, Blob[]> = {
    dashboard: [
      { w: 260, h: 260, color: "rgba(58,136,130,0.32)", s: { top: -100, left: -100 } },
      { w: 200, h: 200, color: "rgba(23,168,118,0.24)", s: { top: 260, right: -80 } },
      { w: 180, h: 180, color: "rgba(204,138,10,0.18)", s: { bottom: 40, left: 60 } },
    ],
    live: [
      { w: 280, h: 280, color: "rgba(20,90,120,0.28)", s: { top: -100, left: -80 } },
      { w: 200, h: 200, color: "rgba(58,136,130,0.22)", s: { top: 340, right: -80 } },
      { w: 160, h: 160, color: "rgba(30,214,154,0.18)", s: { bottom: 60, left: 30 } },
    ],
    alerts: [
      { w: 240, h: 240, color: "rgba(196,48,48,0.22)", s: { top: -80, right: -80 } },
      { w: 200, h: 200, color: "rgba(201,101,0,0.2)", s: { top: 260, left: -60 } },
      { w: 160, h: 160, color: "rgba(23,168,118,0.16)", s: { bottom: 30, right: -40 } },
    ],
    history: [
      { w: 240, h: 240, color: "rgba(58,136,130,0.26)", s: { top: -80, left: -60 } },
      { w: 200, h: 200, color: "rgba(23,168,118,0.2)", s: { bottom: 60, right: -70 } },
    ],
    settings: [
      { w: 220, h: 220, color: "rgba(58,136,130,0.24)", s: { top: -60, right: -60 } },
      { w: 200, h: 200, color: "rgba(100,110,200,0.18)", s: { bottom: 80, left: -70 } },
      { w: 160, h: 160, color: "rgba(23,168,118,0.15)", s: { top: 360, left: 80 } },
    ],
  };
  return (
    <>
      {sets[screen].map((b, i) => (
        <div key={i} style={{
          position: "absolute", width: b.w, height: b.h,
          borderRadius: "50%", background: b.color,
          filter: "blur(70px)", pointerEvents: "none", ...b.s,
        }} />
      ))}
    </>
  );
}

// ─── Shared primitives ────────────────────────────────────────────

function GlassCard({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ borderRadius: 18, overflow: "hidden", ...GLASS, ...style }}>
      {children}
    </div>
  );
}

function Dot({ color, pulse }: { color: string; pulse?: boolean }) {
  return (
    <span style={{
      width: 7, height: 7, borderRadius: "50%", background: color,
      flexShrink: 0, display: "inline-block",
      animation: pulse ? "blink 1.5s ease-in-out infinite" : "none",
    }} />
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button onClick={onChange} style={{
      width: 46, height: 27, borderRadius: 14, border: "none", cursor: "pointer",
      background: on ? C.teal : "rgba(180,190,195,0.8)", position: "relative",
      transition: "background 0.2s", flexShrink: 0, padding: 0,
      backdropFilter: "blur(8px)",
      WebkitBackdropFilter: "blur(8px)",
    }}>
      <span style={{
        position: "absolute", top: 3, left: on ? 22 : 3,
        width: 21, height: 21, borderRadius: "50%", background: "white",
        boxShadow: "0 1px 6px rgba(0,0,0,0.28)", transition: "left 0.2s", display: "block",
      }} />
    </button>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 700, letterSpacing: "0.07em",
      color: C.fgMuted, textTransform: "uppercase", padding: "0 18px 8px",
    }}>
      {children}
    </div>
  );
}

function Chip({ children, color, bg }: { children: React.ReactNode; color: string; bg: string }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "3px 10px",
      borderRadius: 99, fontSize: 11, fontWeight: 500, color, background: bg,
      backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
      border: "1px solid rgba(255,255,255,0.6)",
    }}>
      {children}
    </span>
  );
}

function AlertIcon({ type, color, size = 16 }: { type: string; color: string; size?: number }) {
  if (type === "octagon") return <AlertOctagon size={size} color={color} />;
  if (type === "triangle") return <AlertTriangle size={size} color={color} />;
  if (type === "info") return <Info size={size} color={color} />;
  return <CheckCircle2 size={size} color={color} />;
}

// ─── Status bar ──────────────────────────────────────────────────

function StatusBar() {
  return (
    <div style={{
      height: 50, position: "relative", zIndex: 3,
      display: "flex", alignItems: "flex-end",
      justifyContent: "space-between", padding: "0 22px 10px",
    }}>
      <span style={{ fontSize: 15, fontWeight: 700, color: C.fg }}>9:41</span>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <svg width="16" height="11" viewBox="0 0 16 11">
          <rect x="0" y="7" width="2.5" height="4" rx="0.8" fill={C.fg} />
          <rect x="4" y="5" width="2.5" height="6" rx="0.8" fill={C.fg} />
          <rect x="8" y="2.5" width="2.5" height="8.5" rx="0.8" fill={C.fg} />
          <rect x="12" y="0" width="2.5" height="11" rx="0.8" fill={C.fg} opacity="0.25" />
        </svg>
        <Wifi size={13} color={C.fg} />
        <svg width="25" height="12" viewBox="0 0 25 12" fill="none">
          <rect x="0.5" y="0.5" width="20" height="11" rx="2.5" stroke={C.fg} strokeWidth="1" />
          <rect x="2" y="2" width="16.5" height="8" rx="1.5" fill={C.fg} />
          <path d="M21.5 4v4c1.1-.8 1.1-3.2 0-4Z" fill={C.fg} />
        </svg>
      </div>
    </div>
  );
}

// ─── Bottom navigation ────────────────────────────────────────────

function BottomNav({ current, onChange }: { current: Screen; onChange: (s: Screen) => void }) {
  const tabs: { id: Screen; label: string; Icon: React.ComponentType<{ size: number; strokeWidth: number }> }[] = [
    { id: "dashboard", label: "首页", Icon: Home },
    { id: "live", label: "实时", Icon: Camera },
    { id: "alerts", label: "提醒", Icon: Bell },
    { id: "history", label: "记录", Icon: CalendarDays },
    { id: "settings", label: "设置", Icon: Settings },
  ];
  return (
    <div style={{
      height: 78, flexShrink: 0, position: "relative", zIndex: 3,
      background: "rgba(240,239,234,0.82)",
      backdropFilter: "blur(24px) saturate(180%)",
      WebkitBackdropFilter: "blur(24px) saturate(180%)",
      borderTop: "1px solid rgba(255,255,255,0.7)",
      boxShadow: "0 -1px 0 rgba(24,38,47,0.06)",
      display: "flex", alignItems: "flex-start", paddingTop: 6,
    }}>
      {tabs.map(({ id, label, Icon }) => {
        const active = current === id;
        return (
          <button key={id} onClick={() => onChange(id)} style={{
            flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
            background: "none", border: "none", cursor: "pointer",
            color: active ? C.teal : C.fgMuted, padding: "6px 0", position: "relative",
          }}>
            {id === "alerts" && (
              <span style={{
                position: "absolute", top: 2, right: "calc(50% - 18px)",
                width: 7, height: 7, borderRadius: "50%", background: C.red,
                border: "2px solid rgba(240,239,234,0.9)",
              }} />
            )}
            <Icon size={21} strokeWidth={active ? 2.2 : 1.8} />
            <span style={{ fontSize: 10, fontWeight: active ? 600 : 400, lineHeight: 1 }}>{label}</span>
            {active && (
              <span style={{
                position: "absolute", bottom: 0, left: "50%", transform: "translateX(-50%)",
                width: 18, height: 2.5, borderRadius: 2, background: C.teal,
              }} />
            )}
          </button>
        );
      })}
    </div>
  );
}

// ─── Screen 1 · Dashboard ────────────────────────────────────────

function DashboardScreen({ onNav }: { onNav: (s: Screen) => void }) {
  const r = 52, circ = 2 * Math.PI * r;

  return (
    <div style={{ paddingBottom: 20 }}>
      {/* Gradient teal header */}
      <div style={{
        background: "linear-gradient(135deg, #3E9890 0%, #2F7A74 55%, #3A8A90 100%)",
        padding: "20px 18px 36px",
        position: "relative", overflow: "hidden",
      }}>
        {/* Decorative circle */}
        <div style={{
          position: "absolute", right: -60, top: -60,
          width: 200, height: 200, borderRadius: "50%",
          background: "rgba(255,255,255,0.08)",
        }} />
        <div style={{
          position: "absolute", right: -20, top: 40,
          width: 100, height: 100, borderRadius: "50%",
          background: "rgba(255,255,255,0.05)",
        }} />

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", position: "relative" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <div style={{
                width: 30, height: 30, borderRadius: "50%",
                ...GLASS_DARK,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <User size={15} color="white" />
              </div>
              <span style={{ fontSize: 13, color: "rgba(255,255,255,0.72)" }}>监护对象</span>
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "white", lineHeight: 1.1 }}>外婆</div>
            <div style={{ fontSize: 13, color: "rgba(255,255,255,0.68)", marginTop: 5 }}>V4 安全状态机 · 早晨服药时段</div>
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            ...GLASS_DARK,
            borderRadius: 20, padding: "5px 12px",
          }}>
            <Dot color="#7FFCE0" pulse />
            <span style={{ fontSize: 12, color: "white", fontWeight: 500 }}>设备在线</span>
          </div>
        </div>
      </div>

      {/* Progress card — overlaps header */}
      <div style={{ padding: "0 16px", marginTop: -22 }}>
        <GlassCard style={{ padding: "18px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <svg width={108} height={108} viewBox="0 0 108 108" style={{ flexShrink: 0 }}>
              {/* Track glow */}
              <circle cx="54" cy="54" r={r} fill="none" stroke="rgba(58,136,130,0.12)" strokeWidth="13" />
              <circle cx="54" cy="54" r={r} fill="none" stroke="rgba(220,220,215,0.6)" strokeWidth="9" />
              <circle
                cx="54" cy="54" r={r} fill="none"
                stroke={C.teal} strokeWidth="9"
                strokeDasharray={`${circ / 3} ${(circ * 2) / 3}`}
                strokeLinecap="round"
                transform="rotate(-90 54 54)"
                style={{ filter: "drop-shadow(0 0 5px rgba(58,136,130,0.5))" }}
              />
              <text x="54" y="50" textAnchor="middle" fill={C.fg} fontSize="22" fontWeight="700" fontFamily="inherit">1/3</text>
              <text x="54" y="66" textAnchor="middle" fill={C.fgMuted} fontSize="10.5" fontFamily="inherit">今日服药</text>
            </svg>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: C.fgMuted, marginBottom: 4 }}>当前状态</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: C.fg, marginBottom: 12 }}>MONITORING</div>
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                ...GLASS_TEAL, borderRadius: 12, padding: "8px 12px",
              }}>
                <Clock size={13} color={C.amber} style={{ flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 11, color: C.fgMuted }}>下次提醒</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: C.amber }}>08:00</div>
                </div>
              </div>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Slot cards */}
      <div style={{ padding: "14px 16px 0" }}>
        <SectionHeader>今日药格状态</SectionHeader>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[
            { label: "早上", en: "AM", count: 2, total: 2, status: "已准备", color: C.green, bg: C.greenBg, filled: true },
            { label: "中午", en: "PM", count: 1, total: 1, status: "待时段", color: C.amber, bg: C.amberBg, filled: false },
            { label: "晚上", en: "EVE", count: 3, total: 3, status: "待时段", color: C.amber, bg: C.amberBg, filled: false },
          ].map((s, i) => (
            <GlassCard key={i} style={{ padding: "13px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 13,
                  background: s.filled ? "rgba(234,244,243,0.9)" : "rgba(242,241,238,0.7)",
                  border: "1px solid rgba(255,255,255,0.7)",
                  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                  flexShrink: 0,
                }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: s.filled ? C.teal : C.fgMuted }}>{s.label}</span>
                  <span style={{ fontSize: 9, color: s.filled ? C.teal : C.fgMuted, opacity: 0.7 }}>{s.en}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: C.fg }}>{s.count} / {s.total} 粒</span>
                    <span style={{
                      fontSize: 12, fontWeight: 500, color: s.color,
                      background: s.bg, padding: "2px 10px", borderRadius: 99,
                      backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
                      border: "1px solid rgba(255,255,255,0.5)",
                    }}>{s.status}</span>
                  </div>
                  <div style={{ height: 4, background: "rgba(220,218,214,0.6)", borderRadius: 2 }}>
                    <div style={{
                      width: s.filled ? "100%" : "0%", height: "100%",
                      background: s.filled ? `linear-gradient(90deg, ${C.green}, #22C97E)` : "transparent",
                      borderRadius: 2, transition: "width 0.5s",
                      boxShadow: s.filled ? "0 0 6px rgba(23,168,118,0.5)" : "none",
                    }} />
                  </div>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      </div>

      <div style={{ padding: "14px 16px 0" }}>
        <SectionHeader>V4 安全状态</SectionHeader>
        <GlassCard style={{ padding: "13px 14px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {SAFETY_STATES.map((s) => (
              <div key={s.key} style={{
                background: s.bg,
                border: "1px solid rgba(255,255,255,0.65)",
                borderRadius: 12,
                padding: "9px 10px",
                minHeight: 56,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <Dot color={s.color} pulse={s.key === "MONITORING"} />
                  <span style={{ fontSize: 11, color: s.color, fontWeight: 700 }}>{s.key}</span>
                </div>
                <div style={{ fontSize: 12, color: C.fgMid, lineHeight: 1.25 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* Alert strip */}
      <div style={{ padding: "14px 16px 0" }}>
        <GlassCard style={{ padding: "12px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 11,
              background: C.greenBg, border: "1px solid rgba(255,255,255,0.6)",
              backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
              display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            }}>
              <CheckCircle2 size={17} color={C.green} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, color: C.fgMuted }}>感知后端</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: C.fg }}>Roboflow YOLO + OpenCV ROI</div>
            </div>
            <button onClick={() => onNav("alerts")} style={{ background: "none", border: "none", cursor: "pointer", color: C.fgMuted }}>
              <ChevronRight size={18} />
            </button>
          </div>
        </GlassCard>
      </div>

      {/* Quick actions */}
      <div style={{ padding: "14px 16px 0", display: "flex", gap: 10 }}>
        <button onClick={() => onNav("live")} style={{
          flex: 2, padding: "13px",
          background: "linear-gradient(135deg, #3E9890, #2F7A74)",
          color: "white", border: "none", borderRadius: 14,
          fontSize: 14, fontWeight: 600, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          boxShadow: "0 4px 16px rgba(58,136,130,0.35), 0 1px 3px rgba(0,0,0,0.1)",
        }}>
          <Camera size={15} />查看实时画面
        </button>
        <button style={{
          flex: 1, padding: "13px", ...GLASS,
          borderRadius: 14, fontSize: 14, fontWeight: 600, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
          color: C.fg,
        }}>
          <Phone size={15} />联系
        </button>
      </div>
    </div>
  );
}

// ─── Pillbox camera SVG ───────────────────────────────────────────

function PillboxCamera() {
  return (
    <svg viewBox="0 0 350 196" width="100%" height="100%" style={{ display: "block" }}>
      <defs>
        <radialGradient id="vig" cx="50%" cy="50%" r="70%">
          <stop offset="0%" stopColor="transparent" />
          <stop offset="100%" stopColor="rgba(0,0,0,0.55)" />
        </radialGradient>
        <filter id="glow-green">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="glow-amber">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <rect width="350" height="196" fill="#0C1720" />
      {[1,2,3,4,5,6].map(i => (
        <line key={`h${i}`} x1="0" y1={i*28} x2="350" y2={i*28} stroke="#111E28" strokeWidth="0.5" />
      ))}
      {[1,2,3,4,5,6,7,8,9].map(i => (
        <line key={`v${i}`} x1={i*39} y1="0" x2={i*39} y2="196" stroke="#111E28" strokeWidth="0.5" />
      ))}

      {/* Pillbox body */}
      <rect x="22" y="40" width="306" height="122" rx="13" fill="#182635" stroke="#243545" strokeWidth="1.5" />
      <line x1="124" y1="52" x2="124" y2="150" stroke="#243545" strokeWidth="1" />
      <line x1="226" y1="52" x2="226" y2="150" stroke="#243545" strokeWidth="1" />

      {/* Morning slot */}
      <text x="73" y="60" textAnchor="middle" fill="#456070" fontSize="9.5" fontFamily="system-ui">早上</text>
      <circle cx="73" cy="104" r="33" fill="#0D1B26" stroke="#1E3040" strokeWidth="1" />
      <circle cx="59" cy="104" r="10.5" fill="#4A8BE8" opacity="0.88" />
      <line x1="59" y1="96" x2="59" y2="112" stroke="rgba(255,255,255,0.18)" strokeWidth="0.8" />
      <circle cx="87" cy="104" r="10.5" fill="#4A8BE8" opacity="0.88" />
      <line x1="87" y1="96" x2="87" y2="112" stroke="rgba(255,255,255,0.18)" strokeWidth="0.8" />
      {/* Green glow detection box */}
      <rect x="36" y="67" width="74" height="74" rx="3" fill="rgba(30,214,154,0.06)" stroke="#1ED69A" strokeWidth="1.5" strokeDasharray="5,3" filter="url(#glow-green)" />
      <rect x="36" y="67" width="60" height="15" rx="2.5" fill="#1ED69A" />
      <text x="39" y="78" fill="white" fontSize="8.5" fontFamily="monospace" fontWeight="600">早上 · 0.93 ✓</text>
      <text x="36" y="152" fill="#1ED69A" fontSize="8" fontFamily="monospace">tablets × 2</text>

      {/* Noon slot */}
      <text x="175" y="60" textAnchor="middle" fill="#456070" fontSize="9.5" fontFamily="system-ui">中午</text>
      <circle cx="175" cy="104" r="33" fill="#0D1B26" stroke="#1E3040" strokeWidth="1" />
      <circle cx="175" cy="104" r="11.5" fill="#E8A840" opacity="0.88" />
      <line x1="175" y1="95.5" x2="175" y2="112.5" stroke="rgba(255,255,255,0.18)" strokeWidth="0.8" />
      <rect x="138" y="67" width="74" height="74" rx="3" fill="rgba(245,168,32,0.06)" stroke="#F5A820" strokeWidth="1.5" strokeDasharray="5,3" filter="url(#glow-amber)" />
      <rect x="138" y="67" width="60" height="15" rx="2.5" fill="#F5A820" />
      <text x="141" y="78" fill="white" fontSize="8.5" fontFamily="monospace" fontWeight="600">中午 · 0.91 ●</text>
      <text x="138" y="152" fill="#F5A820" fontSize="8" fontFamily="monospace">tablets × 1</text>

      {/* Evening slot */}
      <text x="277" y="60" textAnchor="middle" fill="#456070" fontSize="9.5" fontFamily="system-ui">晚上</text>
      <circle cx="277" cy="104" r="33" fill="#0D1B26" stroke="#1E3040" strokeWidth="1" />
      <rect x="262" y="89" width="24" height="10" rx="5" fill="#C85868" opacity="0.86" />
      <line x1="274" y1="89" x2="274" y2="99" stroke="rgba(0,0,0,0.2)" strokeWidth="0.8" />
      <rect x="262" y="102" width="24" height="10" rx="5" fill="#C85868" opacity="0.86" />
      <line x1="274" y1="102" x2="274" y2="112" stroke="rgba(0,0,0,0.2)" strokeWidth="0.8" />
      <rect x="262" y="115" width="24" height="10" rx="5" fill="#C85868" opacity="0.86" />
      <line x1="274" y1="115" x2="274" y2="125" stroke="rgba(0,0,0,0.2)" strokeWidth="0.8" />
      <rect x="240" y="67" width="74" height="74" rx="3" fill="rgba(245,168,32,0.06)" stroke="#F5A820" strokeWidth="1.5" strokeDasharray="5,3" filter="url(#glow-amber)" />
      <rect x="240" y="67" width="60" height="15" rx="2.5" fill="#F5A820" />
      <text x="243" y="78" fill="white" fontSize="8.5" fontFamily="monospace" fontWeight="600">晚上 · 0.89 ●</text>
      <text x="240" y="152" fill="#F5A820" fontSize="8" fontFamily="monospace">capsules × 3</text>

      <rect width="350" height="196" fill="url(#vig)" />

      {/* Corners */}
      <g stroke="#2A4A5E" strokeWidth="1.3" opacity="0.65">
        <line x1="0" y1="0" x2="14" y2="0" /><line x1="0" y1="0" x2="0" y2="14" />
        <line x1="336" y1="0" x2="350" y2="0" /><line x1="350" y1="0" x2="350" y2="14" />
        <line x1="0" y1="182" x2="0" y2="196" /><line x1="0" y1="196" x2="14" y2="196" />
        <line x1="336" y1="196" x2="350" y2="196" /><line x1="350" y1="182" x2="350" y2="196" />
      </g>
    </svg>
  );
}

// ─── Screen 2 · Live Camera ───────────────────────────────────────

function LiveScreen() {
  const [refreshing, setRefreshing] = useState(false);

  return (
    <div style={{ paddingBottom: 20 }}>
      <div style={{ padding: "16px 16px 10px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: C.fg, margin: 0 }}>实时监控</h2>
          <div style={{ fontSize: 12, color: C.fgMuted, marginTop: 2 }}>Memory Echo Pillbox</div>
        </div>
        <button
          onClick={() => { setRefreshing(true); setTimeout(() => setRefreshing(false), 1500); }}
          style={{
            ...GLASS_TEAL, borderRadius: 11, padding: "7px 13px",
            color: C.teal, cursor: "pointer", border: "1px solid rgba(255,255,255,0.65)",
            display: "flex", alignItems: "center", gap: 5, fontSize: 13, fontWeight: 500,
          }}
        >
          <RefreshCw size={13} style={{ animation: refreshing ? "spin 0.8s linear infinite" : "none" }} />
          刷新画面
        </button>
      </div>

      {/* Camera */}
      <div style={{ margin: "0 16px" }}>
        <div style={{
          borderRadius: 18, overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.3)",
          position: "relative", background: "#0C1720", lineHeight: 0,
          boxShadow: "0 8px 32px rgba(0,0,0,0.25)",
        }}>
          <PillboxCamera />

          <div style={{
            position: "absolute", left: 0, right: 0, height: 2, pointerEvents: "none",
            background: "linear-gradient(90deg, transparent, rgba(30,214,154,0.65), transparent)",
            animation: "scanLine 3s ease-in-out infinite", top: 0,
          }} />

          <div style={{ position: "absolute", top: 10, left: 12, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              background: "rgba(196,48,48,0.88)", color: "white",
              fontSize: 10, fontWeight: 800, letterSpacing: "0.1em",
              padding: "2px 7px", borderRadius: 4,
              backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
            }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "rgba(255,180,180,0.95)", animation: "blink 1.2s ease-in-out infinite", display: "inline-block" }} />
              LIVE
            </span>
            <span style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(8px)", color: "#6A8FA0", fontSize: 10, fontFamily: "monospace", padding: "2px 7px", borderRadius: 4 }}>
              08:01:32
            </span>
          </div>

          <div style={{ position: "absolute", bottom: 18, left: 10, right: 10, display: "flex", justifyContent: "space-between" }}>
            <span style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(8px)", color: "#4ABFA0", fontSize: 9.5, fontFamily: "monospace", padding: "2px 7px", borderRadius: 4 }}>
              Roboflow · pill-detection-fnftd/3
            </span>
            <span style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(8px)", color: "#6A8FA0", fontSize: 9.5, fontFamily: "monospace", padding: "2px 7px", borderRadius: 4 }}>
              Morning · MONITORING
            </span>
          </div>
        </div>
      </div>

      {/* Status chips */}
      <div style={{ display: "flex", gap: 7, padding: "10px 16px 0", flexWrap: "wrap" }}>
        <Chip color={C.teal} bg="rgba(234,244,243,0.8)">检测后端: Roboflow YOLO</Chip>
        <Chip color={C.fgMid} bg="rgba(242,241,238,0.8)">空间映射: OpenCV ROI</Chip>
        <Chip color={C.amber} bg={C.amberBg}>状态机: MONITORING</Chip>
      </div>

      {/* Detection results */}
      <div style={{ padding: "12px 16px 0" }}>
        <SectionHeader>视觉检测结果</SectionHeader>
        <GlassCard>
          {[
            { slot: "早上", type: "tablets", count: 2, conf: 0.93, ok: true, state: "ready" },
            { slot: "中午", type: "tablets", count: 1, conf: 0.91, ok: false, state: "not current" },
            { slot: "晚上", type: "capsules", count: 3, conf: 0.89, ok: false, state: "not current" },
          ].map((row, i) => (
            <div key={i} style={{
              padding: "11px 16px",
              borderBottom: i < 2 ? "1px solid rgba(255,255,255,0.5)" : "none",
              display: "flex", alignItems: "center", gap: 12,
            }}>
              <Dot color={row.ok ? C.green : C.amber} />
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: C.fg }}>{row.slot}</span>
                  <span style={{
                    fontSize: 11, color: row.ok ? C.green : C.amber,
                    background: row.ok ? C.greenBg : C.amberBg,
                    padding: "1px 9px", borderRadius: 99,
                    backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
                    border: "1px solid rgba(255,255,255,0.5)",
                  }}>{row.ok ? "已准备" : "待时段"}</span>
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 3 }}>
                  <span style={{ fontSize: 12, color: C.fgMuted }}>{row.type} · {row.count} 粒</span>
                  <span style={{ fontSize: 12, fontFamily: "monospace", color: C.teal }}>conf {row.conf}</span>
                  <span style={{ fontSize: 12, fontFamily: "monospace", color: C.fgMuted }}>{row.state}</span>
                </div>
              </div>
            </div>
          ))}
        </GlassCard>
      </div>

      {/* Event log */}
      <div style={{ padding: "12px 16px 0" }}>
        <SectionHeader>事件日志</SectionHeader>
        <GlassCard style={{ padding: "4px 0" }}>
          {[
            { time: "07:58", text: "Roboflow 检测到早上药格 tablets × 2", color: C.green },
            { time: "08:00", text: "OpenCV ROI 映射到 Morning，等待 hand_to_mouth", color: C.amber },
            { time: "08:01", text: "成功条件：正确药格 + 剂量匹配 + hand_to_mouth + swallow", color: C.teal },
          ].map((ev, i) => (
            <div key={i} style={{
              padding: "9px 16px",
              borderBottom: i === 0 ? "1px solid rgba(255,255,255,0.5)" : "none",
              display: "flex", alignItems: "center", gap: 10,
            }}>
              <span style={{ fontSize: 11, fontFamily: "monospace", color: C.fgMuted, flexShrink: 0 }}>{ev.time}</span>
              <Dot color={ev.color} />
              <span style={{ fontSize: 13, color: C.fg, lineHeight: 1.4 }}>{ev.text}</span>
            </div>
          ))}
        </GlassCard>
      </div>

      {/* Actions */}
      <div style={{ padding: "14px 16px 0", display: "flex", gap: 10 }}>
        <button style={{
          flex: 2, padding: "13px",
          background: "linear-gradient(135deg, #3E9890, #2F7A74)",
          color: "white", border: "none", borderRadius: 14,
          fontSize: 14, fontWeight: 600, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          boxShadow: "0 4px 16px rgba(58,136,130,0.35)",
        }}>
          <Phone size={15} />联系家属
        </button>
        <button style={{
          flex: 1, padding: "13px", ...GLASS,
          borderRadius: 14, fontSize: 14, fontWeight: 600, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 7, color: C.fg,
        }}>
          <Activity size={15} />日志
        </button>
      </div>
    </div>
  );
}

// ─── Screen 3 · Alerts ───────────────────────────────────────────

function AlertsScreen({ setAlertModal }: {
  alertModal: number | null;
  setAlertModal: (i: number | null) => void;
}) {
  const active = ALERTS.filter(a => !a.resolved);

  return (
    <div style={{ paddingBottom: 20 }}>
      <div style={{ padding: "16px 16px 12px" }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: C.fg, margin: 0 }}>异常提醒</h2>
        <div style={{ fontSize: 12, color: C.fgMuted, marginTop: 2 }}>{active.length} 条未处理 · 今日</div>
      </div>

      <div style={{ padding: "0 16px" }}>
        <SectionHeader>未处理</SectionHeader>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {ALERTS.map((alert, i) => {
            if (alert.resolved) return null;
            return (
              <button key={i} onClick={() => setAlertModal(i)}
                style={{ textAlign: "left", background: "none", border: "none", padding: 0, cursor: "pointer", width: "100%" }}>
                <div style={{
                  background: alert.sevBg,
                  backdropFilter: "blur(18px) saturate(160%)",
                  WebkitBackdropFilter: "blur(18px) saturate(160%)",
                  borderRadius: 16,
                  border: `1px solid rgba(255,255,255,0.65)`,
                  boxShadow: `0 4px 20px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.8)`,
                  padding: "14px 16px 14px 20px",
                  position: "relative", overflow: "hidden",
                }}>
                  {/* Left severity bar */}
                  <div style={{
                    position: "absolute", left: 0, top: 0, bottom: 0, width: 4,
                    background: alert.sevColor,
                    boxShadow: `2px 0 8px ${alert.sevColor}55`,
                    borderRadius: "16px 0 0 16px",
                  }} />
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 7 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <AlertIcon type={alert.iconType} color={alert.sevColor} size={16} />
                      <span style={{ fontSize: 15, fontWeight: 700, color: C.fg }}>{alert.title}</span>
                    </div>
                    <span style={{
                      fontSize: 11, fontWeight: 600, color: alert.sevColor,
                      background: "rgba(255,255,255,0.8)", padding: "2px 8px", borderRadius: 99, flexShrink: 0,
                    }}>{alert.severity}</span>
                  </div>
                  <p style={{ fontSize: 13, color: C.fgMid, margin: "0 0 9px", lineHeight: 1.45 }}>{alert.desc}</p>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: C.fgMuted }}>{alert.slot} · {alert.time}</span>
                    <span style={{ fontSize: 12, color: alert.sevColor, fontWeight: 500 }}>{alert.action}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ padding: "16px 16px 0" }}>
        <SectionHeader>已解决</SectionHeader>
        {ALERTS.filter(a => a.resolved).map((alert, i) => (
          <GlassCard key={i} style={{ padding: "13px 16px", opacity: 0.75 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, background: C.greenBg, border: "1px solid rgba(255,255,255,0.6)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <CheckCircle2 size={17} color={C.green} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: C.fg }}>{alert.title}</span>
                  <span style={{ fontSize: 11, color: C.green, background: C.greenBg, padding: "1px 9px", borderRadius: 99, border: "1px solid rgba(255,255,255,0.5)" }}>已解决</span>
                </div>
                <div style={{ fontSize: 12, color: C.fgMuted, marginTop: 2 }}>{alert.desc}</div>
                <div style={{ fontSize: 11, color: C.fgMuted, marginTop: 2 }}>{alert.time}</div>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}

// Alert detail modal
function AlertModal({ index, onClose }: { index: number; onClose: () => void }) {
  const alert = ALERTS[index];
  if (!alert) return null;
  return (
    <>
      <div style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 10, backdropFilter: "blur(4px)", WebkitBackdropFilter: "blur(4px)" }} onClick={onClose} />
      <div style={{
        position: "absolute", bottom: 0, left: 0, right: 0, zIndex: 20,
        background: "rgba(240,239,234,0.88)",
        backdropFilter: "blur(28px) saturate(180%)",
        WebkitBackdropFilter: "blur(28px) saturate(180%)",
        borderRadius: "22px 22px 0 0",
        border: "1px solid rgba(255,255,255,0.8)",
        borderBottom: "none",
        padding: "0 20px 36px",
        boxShadow: "0 -8px 40px rgba(0,0,0,0.18)",
        animation: "slideUp 0.3s ease",
      }}>
        <div style={{ display: "flex", justifyContent: "center", padding: "12px 0 16px" }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: "rgba(0,0,0,0.15)" }} />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 42, height: 42, borderRadius: 13, background: alert.sevBg, border: "1px solid rgba(255,255,255,0.7)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <AlertIcon type={alert.iconType} color={alert.sevColor} size={20} />
            </div>
            <div>
              <div style={{ fontSize: 17, fontWeight: 700, color: C.fg }}>{alert.title}</div>
              <span style={{ fontSize: 12, color: alert.sevColor, fontWeight: 600 }}>{alert.severity}</span>
            </div>
          </div>
          <button onClick={onClose} style={{ background: "rgba(0,0,0,0.08)", border: "none", borderRadius: "50%", width: 32, height: 32, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <X size={16} color={C.fgMuted} />
          </button>
        </div>

        <div style={{ background: alert.sevBg, backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.6)", borderRadius: 13, padding: "14px 16px", marginBottom: 14 }}>
          <div style={{ fontSize: 14, color: C.fgMid, lineHeight: 1.55 }}>{alert.desc}</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
          {[
            { label: "触发时间", value: alert.time },
            { label: "涉及药格", value: alert.slot },
            ...(alert.action ? [{ label: "建议操作", value: alert.action }] : []),
          ].map(({ label, value }) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <span style={{ fontSize: 13, color: C.fgMuted }}>{label}</span>
              <span style={{ fontSize: 13, fontWeight: 500, color: C.fg, textAlign: "right", maxWidth: "58%" }}>{value}</span>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onClose} style={{
            flex: 2, padding: "13px",
            background: "linear-gradient(135deg, #3E9890, #2F7A74)",
            color: "white", border: "none", borderRadius: 14,
            fontSize: 14, fontWeight: 600, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            boxShadow: "0 4px 16px rgba(58,136,130,0.35)",
          }}>
            <Check size={15} />标记已处理
          </button>
          <button style={{
            flex: 1, padding: "13px", ...GLASS,
            borderRadius: 14, fontSize: 14, fontWeight: 600, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 7, color: C.fg,
          }}>
            <Phone size={15} />联系
          </button>
        </div>
      </div>
    </>
  );
}

// ─── Screen 4 · History ──────────────────────────────────────────

const HISTORY_EVENTS = [
  { time: "08:03", text: "早上服药已确认", sub: "正确药格 + 剂量匹配 + hand_to_mouth + swallow", color: C.green, iconType: "check" },
  { time: "08:01", text: "检测到 hand_to_mouth 与 swallow", sub: "动作闭环完成", color: C.teal, iconType: "activity" },
  { time: "08:00", text: "Roboflow 检测到早上药格变空", sub: "OpenCV ROI 映射通过", color: C.amber, iconType: "dot" },
  { time: "12:00", text: "中午服药待确认", sub: "时段未到", color: C.fgMuted, iconType: "clock" },
];

function HistoryScreen({ tab, setTab }: { tab: 0 | 1 | 2; setTab: (t: 0 | 1 | 2) => void }) {
  return (
    <div style={{ paddingBottom: 20 }}>
      <div style={{ padding: "16px 16px 10px" }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: C.fg, margin: 0 }}>用药记录</h2>
      </div>

      {/* Segmented control */}
      <div style={{ padding: "0 16px 14px" }}>
        <div style={{ display: "flex", background: "rgba(210,208,203,0.55)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", borderRadius: 13, padding: 3, border: "1px solid rgba(255,255,255,0.6)" }}>
          {(["今天", "昨天", "本周"] as const).map((label, i) => (
            <button key={i} onClick={() => setTab(i as 0 | 1 | 2)} style={{
              flex: 1, padding: "8px 0", borderRadius: 11,
              background: tab === i ? "rgba(255,255,255,0.85)" : "transparent",
              border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: tab === i ? 600 : 400,
              color: tab === i ? C.fg : C.fgMuted,
              boxShadow: tab === i ? "0 1px 6px rgba(0,0,0,0.1)" : "none",
              transition: "all 0.15s", backdropFilter: tab === i ? "blur(8px)" : "none",
            }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Adherence card */}
      <div style={{ padding: "0 16px 14px" }}>
        <div style={{
          background: "linear-gradient(135deg, #3E9890 0%, #2F7A74 55%, #3A8A90 100%)",
          borderRadius: 18, padding: "18px 18px 16px",
          boxShadow: "0 8px 28px rgba(58,136,130,0.3), 0 2px 8px rgba(0,0,0,0.1)",
          position: "relative", overflow: "hidden",
        }}>
          <div style={{ position: "absolute", right: -30, top: -30, width: 120, height: 120, borderRadius: "50%", background: "rgba(255,255,255,0.08)" }} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, position: "relative" }}>
            <div>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.68)", marginBottom: 2 }}>本周按时率</div>
              <div style={{ fontSize: 36, fontWeight: 800, color: "white", lineHeight: 1 }}>86%</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.68)", marginBottom: 2 }}>连续按时服药</div>
              <div style={{ fontSize: 30, fontWeight: 700, color: "white", lineHeight: 1 }}>4 次</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 5, alignItems: "flex-end", height: 34, position: "relative" }}>
            {[85, 100, 67, 100, 100, 83, 86].map((pct, i) => (
              <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                <div style={{ width: "100%", borderRadius: 4, height: (pct / 100) * 28, minHeight: 4, background: pct === 100 ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.38)", boxShadow: pct === 100 ? "0 0 6px rgba(255,255,255,0.5)" : "none" }} />
                <span style={{ fontSize: 8.5, color: "rgba(255,255,255,0.55)" }}>{["一","二","三","四","五","六","日"][i]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div style={{ padding: "0 16px" }}>
        <SectionHeader>事件时间线</SectionHeader>
        <GlassCard>
          {HISTORY_EVENTS.map((ev, i) => (
            <div key={i} style={{
              padding: "13px 16px",
              borderBottom: i < HISTORY_EVENTS.length - 1 ? "1px solid rgba(255,255,255,0.5)" : "none",
              display: "flex", alignItems: "flex-start", gap: 12, position: "relative",
            }}>
              {i < HISTORY_EVENTS.length - 1 && (
                <div style={{ position: "absolute", left: 29, top: 38, bottom: -1, width: 1.5, background: "rgba(255,255,255,0.5)" }} />
              )}
              <div style={{
                width: 28, height: 28, borderRadius: 9, flexShrink: 0, zIndex: 1,
                background: ev.iconType === "check" ? C.greenBg : ev.iconType === "clock" ? "rgba(242,241,238,0.7)" : "rgba(234,244,243,0.85)",
                border: "1px solid rgba(255,255,255,0.65)",
                display: "flex", alignItems: "center", justifyContent: "center",
                backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
              }}>
                {ev.iconType === "check" && <Check size={13} color={C.green} />}
                {ev.iconType === "activity" && <Activity size={13} color={C.teal} />}
                {ev.iconType === "dot" && <div style={{ width: 7, height: 7, borderRadius: "50%", background: C.amber }} />}
                {ev.iconType === "clock" && <Clock size={13} color={C.fgMuted} />}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3, color: ev.iconType === "clock" ? C.fgMuted : C.fg }}>{ev.text}</span>
                  <span style={{ fontSize: 12, fontFamily: "monospace", color: C.fgMuted, flexShrink: 0 }}>{ev.time}</span>
                </div>
                <div style={{ fontSize: 12, color: C.fgMuted, marginTop: 2 }}>{ev.sub}</div>
              </div>
            </div>
          ))}
        </GlassCard>
      </div>
    </div>
  );
}

// ─── Screen 5 · Settings ─────────────────────────────────────────

function SettingsScreen({
  toggles, setToggles,
}: {
  toggles: { wrongSlot: boolean; dosage: boolean; missed: boolean; uncertain: boolean };
  setToggles: React.Dispatch<React.SetStateAction<{ wrongSlot: boolean; dosage: boolean; missed: boolean; uncertain: boolean }>>;
}) {
  return (
    <div style={{ paddingBottom: 24 }}>
      <div style={{ padding: "16px 16px 12px" }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: C.fg, margin: 0 }}>药盒设置</h2>
      </div>

      <div style={{ padding: "0 16px 14px" }}>
        <SectionHeader>设备状态</SectionHeader>
        <GlassCard>
          {[
            { label: "摄像头状态", value: "在线", valueColor: C.green, dot: true },
            { label: "检测模式", value: "Roboflow YOLO", valueColor: C.teal, dot: false },
            { label: "空间映射", value: "OpenCV ROI", valueColor: C.fgMid, dot: false },
          ].map((item, i) => (
            <div key={i} style={{ padding: "13px 16px", borderBottom: i < 2 ? "1px solid rgba(255,255,255,0.5)" : "none", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 14, color: C.fg }}>{item.label}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {item.dot && <Dot color={C.green} pulse />}
                <span style={{ fontSize: 14, fontWeight: 500, color: item.valueColor }}>{item.value}</span>
              </div>
            </div>
          ))}
        </GlassCard>
      </div>

      <div style={{ padding: "0 16px 14px" }}>
        <SectionHeader>服药计划</SectionHeader>
        <GlassCard>
          {[
            { time: "早上 08:00", pills: "2 粒", type: "片剂" },
            { time: "中午 12:00", pills: "1 粒", type: "片剂" },
            { time: "晚上 20:00", pills: "3 粒", type: "胶囊" },
          ].map((s, i) => (
            <div key={i} style={{ padding: "13px 16px", borderBottom: i < 2 ? "1px solid rgba(255,255,255,0.5)" : "none", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 40, height: 40, borderRadius: 12, background: "rgba(234,244,243,0.85)", border: "1px solid rgba(255,255,255,0.65)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)" }}>
                <Clock size={16} color={C.teal} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.fg }}>{s.time}</div>
                <div style={{ fontSize: 12, color: C.fgMuted, marginTop: 1 }}>{s.pills} · {s.type}</div>
              </div>
              <ChevronRight size={16} color={C.fgMuted} />
            </div>
          ))}
        </GlassCard>
      </div>

      <div style={{ padding: "0 16px 14px" }}>
        <SectionHeader>通知设置</SectionHeader>
        <GlassCard>
          {[
            { label: "拿错药格立即通知", key: "wrongSlot" as const, desc: "检测到错误取药时" },
            { label: "剂量异常通知", key: "dosage" as const, desc: "药量与处方不符时" },
            { label: "未按时服药通知", key: "missed" as const, desc: "超时 15 分钟未服" },
            { label: "视觉不确定通知", key: "uncertain" as const, desc: "低置信度或摄像头遮挡时" },
          ].map((item, i) => (
            <div key={i} style={{ padding: "13px 16px", borderBottom: i < 2 ? "1px solid rgba(255,255,255,0.5)" : "none", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 500, color: C.fg }}>{item.label}</div>
                <div style={{ fontSize: 12, color: C.fgMuted, marginTop: 1 }}>{item.desc}</div>
              </div>
              <Toggle on={toggles[item.key]} onChange={() => setToggles(prev => ({ ...prev, [item.key]: !prev[item.key] }))} />
            </div>
          ))}
        </GlassCard>
      </div>

      <div style={{ padding: "0 16px 16px" }}>
        <SectionHeader>紧急联系人</SectionHeader>
        <GlassCard>
          {[
            { name: "女儿", role: "主要家属", initials: "女" },
            { name: "护理员", role: "专业护理", initials: "护" },
          ].map((c, i) => (
            <div key={i} style={{ padding: "13px 16px", borderBottom: i === 0 ? "1px solid rgba(255,255,255,0.5)" : "none", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(196,228,225,0.7)", border: "1px solid rgba(255,255,255,0.7)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)" }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: C.teal }}>{c.initials}</span>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.fg }}>{c.name}</div>
                <div style={{ fontSize: 12, color: C.fgMuted }}>{c.role}</div>
              </div>
              <button style={{ ...GLASS_TEAL, border: "1px solid rgba(255,255,255,0.65)", borderRadius: 9, padding: "6px 13px", color: C.teal, fontSize: 12, fontWeight: 500, cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
                <Phone size={12} />联系
              </button>
            </div>
          ))}
        </GlassCard>
      </div>

      <div style={{ padding: "0 16px" }}>
        <button style={{
          width: "100%", padding: "15px",
          background: "linear-gradient(135deg, #3E9890, #2F7A74)",
          color: "white", border: "none", borderRadius: 14,
          fontSize: 15, fontWeight: 600, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          boxShadow: "0 4px 18px rgba(58,136,130,0.38)",
        }}>
          <Shield size={16} />保存设置
        </button>
      </div>
    </div>
  );
}

// ─── App root ────────────────────────────────────────────────────

export default function App() {
  const [screen, setScreen] = useState<Screen>("dashboard");
  const [alertModal, setAlertModal] = useState<number | null>(null);
  const [historyTab, setHistoryTab] = useState<0 | 1 | 2>(0);
  const [toggles, setToggles] = useState({ wrongSlot: true, dosage: true, missed: true, uncertain: true });

  return (
    <>
      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; }
        @keyframes scanLine {
          0%   { top: 0%;   opacity: 0; }
          5%   { opacity: 1; }
          95%  { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.15; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes slideUp {
          from { transform: translateY(100%); }
          to   { transform: translateY(0); }
        }
        ::-webkit-scrollbar { display: none; }
        * { scrollbar-width: none; }
      `}</style>

      <div style={{
        minHeight: "100vh",
        background: "linear-gradient(145deg, #8CAEC0 0%, #9DBDAD 38%, #B0A8BE 72%, #A4B8B8 100%)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 24,
        fontFamily: "'Noto Sans SC', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', system-ui, sans-serif",
      }}>
        {/* Phone frame */}
        <div style={{
          width: 393, height: 852,
          background: C.bg,
          borderRadius: 52,
          border: "10px solid #0E0E0E",
          boxShadow: [
            "0 70px 140px rgba(0,0,0,0.5)",
            "0 28px 56px rgba(0,0,0,0.28)",
            "0 8px 16px rgba(0,0,0,0.15)",
            "inset 0 0 0 1px rgba(255,255,255,0.08)",
          ].join(", "),
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          position: "relative",
        }}>
          {/* Dynamic island */}
          <div style={{
            position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)",
            width: 118, height: 33, background: "#0E0E0E", borderRadius: 20, zIndex: 50,
          }} />

          <StatusBar />

          {/* Fixed blob background layer */}
          <div style={{
            position: "absolute", top: 50, left: 0, right: 0, bottom: 78,
            overflow: "hidden", pointerEvents: "none", zIndex: 0,
          }}>
            <ScreenBlobs screen={screen} />
          </div>

          {/* Scrollable content */}
          <div style={{ position: "relative", zIndex: 1, flex: 1, overflowY: "auto", overflowX: "hidden" }}>
            {screen === "dashboard" && <DashboardScreen onNav={setScreen} />}
            {screen === "live" && <LiveScreen />}
            {screen === "alerts" && <AlertsScreen alertModal={alertModal} setAlertModal={setAlertModal} />}
            {screen === "history" && <HistoryScreen tab={historyTab} setTab={setHistoryTab} />}
            {screen === "settings" && <SettingsScreen toggles={toggles} setToggles={setToggles} />}
          </div>

          <BottomNav current={screen} onChange={setScreen} />

          {alertModal !== null && (
            <AlertModal index={alertModal} onClose={() => setAlertModal(null)} />
          )}
        </div>
      </div>
    </>
  );
}
