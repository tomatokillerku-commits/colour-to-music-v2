import { useState, useEffect, useRef, useCallback } from "react";
import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode } from "react";

// ─── Constants ────────────────────────────────────────────────────────────────

const GOLD = "#c9a84c";

// 小工具按钮（03 取样 / 06 分层）
const chipBtn: CSSProperties = {
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 3,
  color: "rgba(255,255,255,0.7)",
  fontSize: 9.5,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  padding: "5px 9px",
  cursor: "pointer",
};

// ─── 展陈站点（四站 + 后台） ─────────────────────────────────────────────────

const STATIONS = [
  { n: 0, label: "Look", sub: "what the painting is, and what a red–green eye loses" },
  { n: 1, label: "Translate", sub: "the painting's own motif, three rules switched on one at a time" },
  { n: 2, label: "Check", sub: "does it hold up" },
];

function StationRail({ station, onPick, onNext, nextLabel, nextDim, hint }: {
  station: number | "lab";
  onPick: (n: number | "lab") => void;
  onNext: () => void;
  nextLabel: string;
  nextDim?: boolean;
  hint?: string;
}) {
  return (
    <div style={{
      position: "fixed", left: 0, right: 0, bottom: 16, zIndex: 120,
      display: "flex", justifyContent: "center", pointerEvents: "none",
    }}>
      <div style={{
        pointerEvents: "auto", display: "flex", alignItems: "center", gap: 2,
        padding: "6px 8px", borderRadius: 999,
        background: "rgba(8,10,16,0.78)", border: "1px solid rgba(255,255,255,0.11)",
        backdropFilter: "blur(12px)", boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
        maxWidth: "calc(100vw - 24px)", overflowX: "auto",
      }}>
        {STATIONS.map((s) => {
          const on = station === s.n;
          return (
            <button
              key={s.n}
              onClick={() => onPick(s.n)}
              title={s.sub}
              aria-current={on ? "step" : undefined}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "none", border: "none", cursor: "pointer",
                padding: "5px 10px", borderRadius: 999,
                fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase",
                color: on ? GOLD : "rgba(255,255,255,0.45)",
              }}
            >
              <span style={{
                width: on ? 7 : 5, height: on ? 7 : 5, borderRadius: "50%",
                backgroundColor: on ? GOLD : "rgba(255,255,255,0.3)",
                boxShadow: on ? `0 0 10px ${GOLD}` : "none",
                transition: "all 0.3s ease",
              }} />
              {s.label}
            </button>
          );
        })}
        <span style={{
          width: 1, height: 14, margin: "0 6px",
          backgroundColor: "rgba(255,255,255,0.14)",
        }} />
        <button
          onClick={() => onPick("lab")}
          title="the rules, the citations, the calibration"
          style={{
            background: "none", border: "none", cursor: "pointer",
            padding: "5px 9px", fontSize: 8.5, letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: station === "lab" ? GOLD : "rgba(255,255,255,0.36)",
          }}
        >
          lab
        </button>
        <button
          onClick={onNext}
          disabled={nextDim}
          style={{
            marginLeft: 6, padding: "6px 13px", borderRadius: 999,
            border: `1px solid ${nextDim ? "rgba(255,255,255,0.14)" : `${GOLD}88`}`,
            background: nextDim ? "transparent" : `${GOLD}1a`,
            color: nextDim ? "rgba(255,255,255,0.32)" : GOLD,
            fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase",
            cursor: nextDim ? "default" : "pointer", whiteSpace: "nowrap",
            transition: "all 0.25s ease",
          }}
        >
          {nextLabel} →
        </button>
      </div>
      {hint && (
        <div style={{
          position: "absolute", bottom: 52, left: 0, right: 0, textAlign: "center",
          fontSize: 10, color: "rgba(255,255,255,0.5)", letterSpacing: "0.04em",
          pointerEvents: "none", animation: "fadeIn 0.6s ease both",
        }}>
          {hint}
        </div>
      )}
    </div>
  );
}

// ─── 术语浮层 ────────────────────────────────────────────────────────────────
// 页面上技术词密度高，非本行读者会在这里停下。点一下给一句人话。

const GLOSSARY: Record<string, string> = {
  "L*": "CIELAB 明度，0 = 黑，100 = 白。比 HSV 的 V 更接近人眼看到的「亮」，所以音高用它而不是用 V。",
  "S": "饱和度的 0–1 平均。0 是灰，1 是最纯的颜色。它决定响度：越纯越响。",
  "spectral centroid": "频谱重心：声音的能量集中在多高的频率。数值越高听起来越「亮」，和音高不是一回事。",
  "dBFS": "数字音频的响度单位，0 是满刻度，负数越小越轻。这里的 −25.3 dBFS 是整段音频的 RMS。",
  "pitch anchor": "音高锚点：整段旋律围绕它上下浮动，由画面的平均明度决定。",
  "MIDI": "音高的编号，60 = 中央 C，每 +12 是八度。36–84 覆盖 C2–C6。",
  "RMS": "均方根，衡量一段声音的平均能量，用来近似「听起来多响」。",
};

function Term({ k, children }: { k: string; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const note = GLOSSARY[k];
  if (!note) return <>{children || k}</>;
  return (
    <span>
      <span
        role="button"
        tabIndex={0}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((v) => !v); } }}
        style={{
          borderBottom: "1px dotted rgba(255,255,255,0.36)",
          cursor: "help", color: open ? GOLD : undefined,
        }}
      >
        {children || k}
      </span>
      {open && (
        <span style={{
          display: "block", margin: "6px 0 2px", paddingLeft: 9,
          borderLeft: `1px solid ${GOLD}66`,
          fontSize: 10.5, lineHeight: 1.7, color: "rgba(255,255,255,0.62)",
        }}>
          {note}
        </span>
      )}
    </span>
  );
}

// ─── 映射标尺 ────────────────────────────────────────────────────────────────
// 十幅画放在同三条轴上：看得出这幅在哪，也看得出哪两幅其实叠在一起。

interface RulerItem {
  id: string; title: string; artist: string; thumb: string; file?: string;
  mean_L: number; mean_S: number; anchor_midi: number; note: string;
  loudness_db: number; centroid_hz: number; bpm: number; is_you?: boolean;
}

function Ruler({ items, currentId, onPick }: {
  items: RulerItem[]; currentId?: string; onPick?: (id: string) => void;
}) {
  const cur = items.find((i) => i.id === currentId);
  if (!cur) return null;

  const rows = [
    { label: "L*", lo: 0, hi: 100, val: cur.mean_L, get: (i: RulerItem) => i.mean_L, fmt: (v: number) => v.toFixed(0) },
    { label: "S", lo: 0, hi: 1, val: cur.mean_S, get: (i: RulerItem) => i.mean_S, fmt: (v: number) => v.toFixed(2) },
    { label: "Hz", lo: 700, hi: 3500, val: cur.centroid_hz, get: (i: RulerItem) => i.centroid_hz, fmt: (v: number) => String(Math.round(v)) },
  ];

  const near = items
    .filter((i) => i.id !== cur.id)
    .map((i) => ({ i, ds: Math.abs(i.anchor_midi - cur.anchor_midi), dh: Math.abs(i.centroid_hz - cur.centroid_hz) }))
    .sort((a, b) => (a.ds + a.dh / 300) - (b.ds + b.dh / 300))[0];
  const collide = near && near.ds <= 0.5 && near.dh <= 80;

  const pct = (v: number, lo: number, hi: number) =>
    `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`;

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        fontSize: 9, letterSpacing: "0.22em", textTransform: "uppercase",
        color: "rgba(255,255,255,0.44)", marginBottom: 8,
      }}>
        Mapping ruler · this painting among the nine
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {rows.map((r) => (
          <div key={r.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 20, fontSize: 9.5, fontFamily: "monospace", color: "rgba(255,255,255,0.5)" }}>{r.label}</span>
            <div style={{ position: "relative", flex: 1, height: 18 }}>
              <div style={{
                position: "absolute", top: 8, left: 0, right: 0, height: 1,
                backgroundColor: "rgba(255,255,255,0.14)",
              }} />
              {items.map((i) => {
                const v = r.get(i);
                if (v === undefined || v === null) return null;
                const on = i.id === cur.id;
                return (
                  <span
                    key={i.id}
                    title={`${i.title} · ${i.artist} · ${r.fmt(v)}`}
                    onClick={() => on && onPick ? onPick(i.id) : (onPick && onPick(i.id))}
                    style={{
                      position: "absolute", left: pct(v, r.lo, r.hi), top: on ? 5 : 7,
                      transform: "translate(-50%, 0)",
                      width: i.is_you ? 11 : (on ? 9 : 5), height: i.is_you ? 11 : (on ? 9 : 5),
                      borderRadius: "50%",
                      backgroundColor: i.is_you ? "transparent" : (on ? GOLD : "rgba(255,255,255,0.26)"),
                      border: i.is_you ? "1.5px solid #8fd0e8" : "none",
                      boxShadow: i.is_you ? "0 0 10px rgba(143,208,232,0.55)"
                        : (on ? `0 0 0 3px ${GOLD}22, 0 0 8px ${GOLD}88` : "none"),
                      animation: i.is_you ? "youPulse 2.4s ease-in-out infinite" : undefined,
                      cursor: "pointer", transition: "all 0.15s",
                    }}
                  />
                );
              })}
            </div>
            <span style={{
              width: 52, textAlign: "right", fontFamily: "monospace", fontSize: 10,
              color: GOLD,
            }}>
              {r.fmt(r.val)}
            </span>
          </div>
        ))}
      </div>

      <p style={{ fontSize: 9.5, lineHeight: 1.7, color: "rgba(255,255,255,0.5)", marginTop: 8 }}>
        {cur.is_you ? "your image" : cur.note} · {cur.bpm} BPM.
        {collide && near ? (
          <>
            {" "}Closest neighbour: <span style={{ color: "rgba(255,255,255,0.78)" }}>{near.i.title}</span>{" "}
            — Δ{near.ds.toFixed(1)} semitone / {Math.round(near.dh)} Hz.
            <span style={{ color: "#d98c8c" }}> Those two paintings are audibly the same sound.</span>
          </>
        ) : near ? (
          <> Nearest: {near.i.title} — Δ{near.ds.toFixed(1)} semitone.</>
        ) : null}
      </p>
    </div>
  );
}

// ─── 画廊卡片上的参数指纹 ────────────────────────────────────────────────────

function Fingerprint({ item }: { item: RulerItem }) {
  const bars = [
    { v: item.mean_L, lo: 0, hi: 100, c: "#e8d9b8" },
    { v: item.mean_S, lo: 0, hi: 1, c: "#c9a84c" },
    { v: item.centroid_hz, lo: 700, hi: 3500, c: "#8fb8c9" },
  ];
  return (
    <div style={{ display: "flex", gap: 3, alignItems: "flex-end", height: 10 }}>
      {bars.map((b, i) => (
        <span key={i} style={{
          width: 3, height: 10, backgroundColor: "rgba(255,255,255,0.12)", position: "relative", overflow: "hidden",
        }}>
          <span style={{
            position: "absolute", bottom: 0, left: 0, right: 0,
            height: `${Math.max(6, Math.min(100, ((b.v - b.lo) / (b.hi - b.lo)) * 100))}%`,
            backgroundColor: b.c, opacity: 0.85,
          }} />
        </span>
      ))}
    </div>
  );
}

// ─── 钢琴卷帘（piano roll）──────────────────────────────────────────────────
// 播放头跟着 MiniPlayer 走；音高在纵轴、时间在横轴，声音和画面有了同一根时间线。

function PianoRoll({ notes, seconds, ratio, voices }: {
  notes: { start_s: number; midi: number }[];
  seconds: number;
  ratio: number;
  voices?: number;
}) {
  if (!notes || notes.length === 0) return null;
  const midis = notes.map((n) => n.midi);
  const lo = Math.min(...midis) - 2;
  const hi = Math.max(...midis) + 2;
  const H = voices ? 62 : 48;

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{
        position: "relative", height: H,
        border: "1px solid rgba(255,255,255,0.1)", borderRadius: 2,
        background: "rgba(255,255,255,0.02)", overflow: "hidden",
      }}>
        {/* 八度刻度 */}
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{
            position: "absolute", left: 0, right: 0, top: `${(i / 4) * 100}%`,
            height: 1, backgroundColor: "rgba(255,255,255,0.045)",
          }} />
        ))}
        {/* 音符 */}
        {notes.map((n, i) => {
          const left = Math.max(0, Math.min(100, (n.start_s / seconds) * 100));
          const w = Math.max(1.2, (1.5 / seconds) * 100);
          const top = 4 + (1 - (n.midi - lo) / Math.max(1, hi - lo)) * (H - 16);
          return (
            <span key={i} style={{
              position: "absolute", left: `${left}%`, top,
              width: `${Math.min(w, 100 - left)}%`, height: 5,
              backgroundColor: GOLD, opacity: 0.82, borderRadius: 1,
            }} />
          );
        })}
        {/* 取样声部：整段长音，单独一行 */}
        {voices ? (
          <span style={{
            position: "absolute", left: 0, right: 0, bottom: 3, height: 3,
            backgroundColor: "rgba(140,200,220,0.55)",
          }} />
        ) : null}
        {/* 播放头 */}
        <div style={{
          position: "absolute", top: 0, bottom: 0, left: `${ratio * 100}%`,
          width: 1, backgroundColor: "rgba(255,255,255,0.75)",
          transition: "left 0.12s linear",
        }} />
      </div>
      <div style={{
        display: "flex", justifyContent: "space-between", marginTop: 4,
        fontSize: 8.5, fontFamily: "monospace", color: "rgba(255,255,255,0.42)",
      }}>
        <span>{notes.length} notes · {lo + 2}–{hi - 2} MIDI</span>
        <span>{seconds}s</span>
      </div>
    </div>
  );
}

// ─── 定位自测：听 2 秒片段，指出它来自画面的哪一段 ─────────────────────────
// 为什么是这个测试：上传者知道自己传了什么，不需要"认出是哪幅画"。
// 需要验证的是「声音和画面有没有对齐」。x → 时间 是这里唯一声称的映射，
// 所以让它可以被本人当场核对。机会水平 = 两个均匀点的平均距离 ≈ 33%。

function LocateTest({ imageUrl, wavUrl, seconds }: { imageUrl: string; wavUrl: string; seconds: number }) {
  const [idx, setIdx] = useState(0);
  const [target, setTarget] = useState<number | null>(null);
  const [errs, setErrs] = useState<number[]>([]);
  const [listening, setListening] = useState(false);
  const [replay, setReplay] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopRef = useRef<number | null>(null);
  const done = errs.length >= 3;

  const playAt = (x: number) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = Math.max(0, Math.min(seconds - 2.2, x * seconds - 1.0));
    a.play().catch(() => {});
    setListening(true);
    if (stopRef.current) window.clearTimeout(stopRef.current);
    stopRef.current = window.setTimeout(() => { a.pause(); setListening(false); }, 2000);
  };

  const next = () => {
    const x = 0.15 + Math.random() * 0.7;
    setTarget(x);
    setReplay((r) => r + 1);
    playAt(x);
  };

  const onPick = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (target == null) return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    setErrs((prev) => [...prev, Math.abs(x - target)]);
    setTarget(null);
    setIdx((i) => i + 1);
    if (audioRef.current) audioRef.current.pause();
    setListening(false);
  };

  const mean = errs.length ? errs.reduce((a, b) => a + b, 0) / errs.length : 0;
  const verdict = mean <= 0.14 ? "well above chance" : mean <= 0.24 ? "above chance" : "at chance";

  return (
    <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid rgba(255,255,255,0.1)" }}>
      <div style={{
        fontSize: 9, letterSpacing: "0.18em", textTransform: "uppercase",
        color: "rgba(255,255,255,0.5)", marginBottom: 7,
      }}>
        Self-test · can you locate what you hear
      </div>
      <p style={{ fontSize: 11, lineHeight: 1.8, color: "rgba(255,255,255,0.68)", marginBottom: 10 }}>
        Three trials. A two-second fragment is played; click the part of the painting it came from.
        The sweep maps left to right, so your error is how far off you are along that axis.
      </p>

      <audio ref={audioRef} src={wavUrl} preload="auto" />

      <div style={{
        position: "relative", lineHeight: 0, cursor: target == null ? "default" : "crosshair",
        border: "1px solid rgba(255,255,255,0.1)", borderRadius: 2, overflow: "hidden",
      }} onClick={onPick}>
        <img src={imageUrl} alt="locate the fragment" style={{
          width: "100%", height: 104, display: "block", objectFit: "fill",
        }} />
        {target != null && listening && (
          <div style={{
            position: "absolute", inset: 0,
            boxShadow: `inset 0 0 0 2px ${GOLD}55`,
            animation: "fadeIn 0.3s ease both", pointerEvents: "none",
          }} />
        )}
        {target != null && (
          <div style={{
            position: "absolute", bottom: 6, left: 8, fontFamily: "monospace", fontSize: 9,
            color: GOLD, background: "rgba(0,0,0,0.6)", padding: "2px 6px", borderRadius: 2,
          }}>
            {listening ? "listening…" : "click where it came from"}
          </div>
        )}
      </div>

      <div style={{
        display: "flex", justifyContent: "space-between", marginTop: 4,
        fontFamily: "monospace", fontSize: 8.5, color: "rgba(255,255,255,0.4)",
      }}>
        <span>left</span><span>← the strip is the whole canvas →</span><span>right</span>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
        {!done && (
          <>
            <button
              onClick={next}
              disabled={target != null}
              style={{
                ...chipBtn,
                borderColor: `${GOLD}77`, color: GOLD,
                opacity: target != null ? 0.45 : 1,
                cursor: target != null ? "default" : "pointer",
              }}
            >
              {idx === 0 ? "▶ start trial 1" : `▶ trial ${idx + 1} of 3`}
            </button>
            {target != null && (
              <button onClick={() => playAt(target)} disabled={listening} style={{ ...chipBtn, opacity: listening ? 0.45 : 1 }}>
                {listening ? "playing…" : "replay"}
              </button>
            )}
            <span style={{ fontFamily: "monospace", fontSize: 9.5, color: "rgba(255,255,255,0.45)" }}>
              {errs.length}/3 recorded
            </span>
          </>
        )}
        {done && (
          <>
            <span style={{ fontFamily: "monospace", fontSize: 11, color: GOLD }}>
              mean error {Math.round(mean * 100)}% of the width
            </span>
            <span style={{ fontSize: 9.5, color: "rgba(255,255,255,0.5)" }}>
              chance ≈ 33% · {verdict}
            </span>
            <button onClick={() => { setErrs([]); setIdx(0); setTarget(null); }} style={chipBtn}>
              again
            </button>
          </>
        )}
      </div>

      {errs.length > 0 && (
        <div style={{ display: "flex", gap: 4, marginTop: 8 }}>
          {errs.map((e2, i) => (
            <span key={i} style={{
              fontFamily: "monospace", fontSize: 9,
              color: e2 <= 0.14 ? "#8fc98f" : e2 <= 0.24 ? GOLD : "rgba(217,140,140,0.9)",
            }}>
              {Math.round(e2 * 100)}%
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── 扫描轨迹：把"从左到右的音高曲线"画出来 ───────────────────────────────

function ScanTrace({ line, seconds }: { line: { t: number; midi: number }[]; seconds: number }) {
  if (!line || line.length < 2) return null;
  const midis = line.map((p) => p.midi);
  const lo = Math.min(...midis) - 1;
  const hi = Math.max(...midis) + 1;
  const pts = line.map((p) => {
    const x = (p.t / seconds) * 100;
    const y = 100 - ((p.midi - lo) / Math.max(1, hi - lo)) * 100;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{
        position: "relative", height: 74, borderRadius: 2,
        border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.02)",
        overflow: "hidden",
      }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: "100%", height: "100%" }}>
          <polyline points={pts} fill="none" stroke={GOLD} strokeWidth="0.7" vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <div style={{
        display: "flex", justifyContent: "space-between", marginTop: 4,
        fontSize: 8.5, fontFamily: "monospace", color: "rgba(255,255,255,0.42)",
      }}>
        <span>left edge</span>
        <span>pitch traced from mean lightness, column by column</span>
        <span>right edge</span>
      </div>
    </div>
  );
}

// 观众档隐藏技术标识与数值（CSS: [data-mode="visitor"] .lab-only），只留句子和声音。

function ModeToggle() {
  const [mode, setMode] = useState<"lab" | "visitor">(() => {
    try { return (localStorage.getItem("c2m_mode") as "lab" | "visitor") || "lab"; } catch { return "lab"; }
  });
  useEffect(() => {
    document.documentElement.dataset.mode = mode;
    try { localStorage.setItem("c2m_mode", mode); } catch { /* private mode */ }
  }, [mode]);

  return (
    <div style={{
      position: "fixed", top: 14, right: 16, zIndex: 400,
      display: "flex", border: "1px solid rgba(255,255,255,0.16)",
      borderRadius: 3, overflow: "hidden", backgroundColor: "rgba(10,10,14,0.72)",
      backdropFilter: "blur(6px)",
    }}>
      {(["lab", "visitor"] as const).map((m) => (
        <button
          key={m}
          onClick={() => setMode(m)}
          aria-pressed={mode === m}
          style={{
            background: mode === m ? `${GOLD}22` : "transparent",
            border: "none", cursor: "pointer",
            padding: "5px 9px", fontSize: 8.5, letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: mode === m ? GOLD : "rgba(255,255,255,0.5)",
          }}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
const UPLOAD_BG_PALETTE = [
  "#18202e", "#221526", "#162222", "#261a08",
  "#162218", "#221428", "#102030", "#1e1a14",
  "#1a1e24", "#1e1216", "#141e2c", "#201c10",
];
const UPLOAD_BG = UPLOAD_BG_PALETTE[Math.floor(Math.random() * UPLOAD_BG_PALETTE.length)];

// ─── Types ────────────────────────────────────────────────────────────────────

interface PaletteColor { rgb: string; hex: string; ratio: number; }

interface EraStyle { label: string; hint: string; }

interface MappingRule {
  rule_id: string;
  kind: "evidence" | "design";
  sentence: string;
  input: { name: string; value: string | number; unit: string };
  output: { name: string; value: string | number; unit: string };
  refs: string[];
  note: string;
}

interface MappingBlock {
  evidence: MappingRule[];
  design: MappingRule[];
  params: Record<string, any>;
  deprecated: { id: string; old_rule: string; why: string; now: string }[];
  refs: Record<string, string>;
  notes: string[];
}

interface SaliencyRegion {
  id: number;
  area_pct: number;
  mean_L: number;
  mean_S: number;
  mean_saliency: number;
  saliency_ratio: number;
  rank_score: number;
  delta_L: number;
  delta_S: number;
  dominant_hue: string;
  hex: string;
  voice_midi: number;
  voice_note: string;
  merged_count: number;
  bbox: { x: number; y: number; w: number; h: number };
  centroid?: { x: number; y: number };
}

interface SaliencySummary {
  n_regions: number;
  area_total_pct: number;
  saliency_ratio_mean: number;
  group_L: number;
  group_S: number;
  brightest: { id: number; delta_L: number } | null;
  darkest: { id: number; delta_L: number } | null;
  most_saturated: { id: number; delta_S: number } | null;
}

interface SaliencyData {
  algorithm: string;
  agreement_with_SR: number;
  heat_url: string | null;
  focus_url?: string | null;
  regions: SaliencyRegion[];
  summary?: SaliencySummary;
  size?: { w: number; h: number };
  top_frac: number;
  notes: string[];
}

interface PreviewData {
  wav_url: string;
  mid_url: string | null;
  seconds: number;
  notes_midi: number[];
  region_voices: { region_id: number; midi: number; target_db: number; target_hz: number }[];
  measured: { rms_dbfs: number; peak_dbfs: number; spectral_centroid_hz: number; duration_s: number };
  verify: Record<string, any>;
  targets: { loudness_target_db: number; brightness_target_hz: number; pitch_anchor_midi: number };
  notes: string[];
}

interface ArtworkData {
  id: string;
  token?: string;
  gate?: {
    ok: boolean;
    verdict: string;
    failures: { key: string; value: number; min: number | null; max: number | null; why: string; fix: string }[];
    metrics: Record<string, number>;
  };
  matched_id?: string;
  file: string;
  image: string | null;
  artist: string;
  title: string;
  year: string;
  medium: string;
  dimensions: string;
  movement: string;
  era_style?: EraStyle;
  mood: string;
  valence: number;
  arousal: number;
  tension: number;
  narrative: string;
  reading?: { why: string; notes: { label: string; text: string }[]; fault: string } | null;
  musical_hint: string;
  ai_available: boolean;
  ai_error?: string;
  dominant_color: string;
  palette: PaletteColor[];
  dominant_hue: string;
  timbre: string;
  mode: string;
  pitch: string;
  mean_S: number;
  mean_V: number;
  warm_ratio: number;
  rgi: number;
  bpm: number;
  music_prompt: string;
  music_prompt_source?: string;
  mapping?: MappingBlock;
  suno_measured?: { file: string; rms_dbfs: number; spectral_centroid_hz: number; duration_s: number }[];
  style_en: string;
  audio: string | null;
}

interface GalleryItem {
  id: string; file: string; artist: string; title: string;
  year: string; movement: string; thumb_small: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function easeOut(t: number) { return 1 - Math.pow(1 - t, 3); }
function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); }
function remap(v: number, inLo: number, inHi: number) {
  return clamp((v - inLo) / (inHi - inLo), 0, 1);
}

function formatTime(s: number) {
  if (!isFinite(s) || s < 0) s = 0;
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
}

// ─── 视口宽度 (响应式: <900 走单栏) ─────────────────────────────────────────

function useViewport(breakpoint = 900) {
  const [compact, setCompact] = useState<boolean>(
    typeof window !== "undefined" ? window.innerWidth < breakpoint : false
  );
  useEffect(() => {
    const onResize = () => setCompact(window.innerWidth < breakpoint);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [breakpoint]);
  return compact;
}

// ─── 把显著性统计组成一句结论（而不是罗列参数） ──────────────────────────────

function attentionSentence(s: SaliencyData): string {
  const sm = s.summary;
  if (!sm || !sm.n_regions) return "";
  const sign = (v: number) => (v > 0 ? "+" : "");
  let where = "";
  if (sm.most_saturated && Math.abs(sm.most_saturated.delta_S) >= 0.15) {
    where = `the most saturated patch (#${sm.most_saturated.id}, S ${sign(sm.most_saturated.delta_S)}${sm.most_saturated.delta_S} vs the whole canvas)`;
  } else if (sm.brightest && sm.brightest.delta_L >= 8) {
    where = `the only bright passage (#${sm.brightest.id}, L* ${sign(sm.brightest.delta_L)}${sm.brightest.delta_L})`;
  } else if (sm.darkest) {
    where = `the darkest area (#${sm.darkest.id}, L* ${sm.darkest.delta_L})`;
  }
  const head = `${sm.n_regions} regions cover ${sm.area_total_pct}% of the canvas but average ${sm.saliency_ratio_mean}× the image's attention`;
  return where ? `${head} — the eye lands on ${where}.` : `${head}.`;
}

const TARGET_DURATION = 60; // seconds

// ─── Waveform ─────────────────────────────────────────────────────────────────

function Waveform({ playing, color, count = 40 }: { playing: boolean; color: string; count?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 28, width: "100%" }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{
          width: 1.5, borderRadius: 1,
          backgroundColor: color, opacity: 0.32,
          height: playing ? 3 : 5,
          animation: playing
            ? `audioWave 0.9s ${(i * 0.04).toFixed(2)}s ease-in-out infinite alternate`
            : "none",
          transition: "height 0.3s ease",
        }} />
      ))}
    </div>
  );
}

// ─── Section Label ────────────────────────────────────────────────────────────

// ─── Mini player（替换原生 <audio controls>，沿用金线语言） ──────────────────

function MiniPlayer({ src, onProgress }: { src: string; onProgress?: (ratio: number) => void }) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [on, setOn] = useState(false);
  const [p, setP] = useState(0);
  const [dur, setDur] = useState(0);

  useEffect(() => {
    const a = ref.current;
    if (!a) return;
    const onTime = () => {
      const r = a.duration ? a.currentTime / a.duration : 0;
      setP(r);
      if (onProgress) onProgress(r);
    };
    const onMeta = () => setDur(a.duration || 0);
    const onEnd = () => { setOn(false); setP(0); };
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("ended", onEnd);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("ended", onEnd);
    };
  }, [src]);

  const toggle = () => {
    const a = ref.current;
    if (!a) return;
    if (a.paused) a.play().then(() => setOn(true)).catch(() => {});
    else { a.pause(); setOn(false); }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <audio ref={ref} src={src} preload="metadata" />
      <button
        onClick={toggle}
        aria-label={on ? "pause preview" : "play preview"}
        style={{
          width: 30, height: 30, borderRadius: "50%", backgroundColor: GOLD,
          border: "none", cursor: "pointer", flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 10, color: "#07080e",
        }}
      >
        {on ? "⏸" : "▶"}
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ height: 2, background: "rgba(255,255,255,0.15)", position: "relative" }}>
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${p * 100}%`, background: GOLD }} />
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between", marginTop: 4,
          fontSize: 9, fontFamily: "monospace", color: "rgba(255,255,255,0.5)",
        }}>
          <span>{formatTime(p * dur)}</span>
          <span>{formatTime(dur)}</span>
        </div>
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, letterSpacing: "0.32em",
      textTransform: "uppercase" as const,
      color: "rgba(255,255,255,0.5)",
      marginBottom: 12, fontFamily: "Lora, serif",
    }}>
      {children}
    </div>
  );
}

// ─── Emotion Meter ────────────────────────────────────────────────────────────

function Meter({ label, value, min, max, color }: {
  label: string; value: number; min: number; max: number; color: string;
}) {
  const pct = clamp((value - min) / (max - min), 0, 1) * 100;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
      <span style={{
        fontSize: 10, color: "rgba(255,255,255,0.48)",
        letterSpacing: "0.1em", width: 76, flexShrink: 0,
      }}>
        {label}
      </span>
      <div style={{
        flex: 1, height: 2, backgroundColor: "rgba(255,255,255,0.1)", borderRadius: 1,
      }}>
        <div style={{
          width: `${pct}%`, height: "100%", backgroundColor: color,
          borderRadius: 1, transition: "width 0.8s cubic-bezier(0.16,1,0.3,1)",
        }} />
      </div>
      <span style={{
        fontSize: 10, color: "rgba(255,255,255,0.55)",
        fontFamily: "monospace", width: 34, textAlign: "right", flexShrink: 0,
      }}>
        {value.toFixed(2)}
      </span>
    </div>
  );
}

// ─── Loading Page ─────────────────────────────────────────────────────────────

const LOADING_MESSAGES = [
  "Analyzing color palette",
  "Extracting emotional resonance",
  "Mapping harmonic frequencies",
  "Composing sound structures",
  "Finalizing your experience",
];

// 各阶段的进度环目标: 起点 / 上限 / 逼近时长(ms)
// 进度只逼近上限、永不走满 —— 真实耗时不确定, 走满会显得"卡住"
const PHASE_RING = {
  colors: { from: 0.04, to: 0.18, ms: 700 },
  emotion: { from: 0.18, to: 0.93, ms: 26000 },
};

function LoadingPage({ phase }: { phase: "colors" | "emotion" }) {
  const [ringProgress, setRingProgress] = useState(PHASE_RING.colors.from);
  const [msgIdx, setMsgIdx] = useState(0);
  const [msgVisible, setMsgVisible] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  const label = phase === "colors"
    ? "Analyzing color palette"
    : "AI reading emotional resonance";

  useEffect(() => {
    const cfg = PHASE_RING[phase];
    const start = performance.now();
    let raf: number;

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / cfg.ms);
      // easeOut: 前期快、后期慢, 渐进逼近上限但永不抵达
      const eased = 1 - Math.pow(1 - t, 3);
      setRingProgress(cfg.from + (cfg.to - cfg.from) * eased);
      setElapsed((now - start) / 1000);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const msgInterval = setInterval(() => {
      setMsgVisible(false);
      setTimeout(() => {
        setMsgIdx((i) => (i + 1) % LOADING_MESSAGES.length);
        setMsgVisible(true);
      }, 300);
    }, 2600);

    return () => {
      cancelAnimationFrame(raf);
      clearInterval(msgInterval);
    };
  }, [phase]);

  const R = 38;
  const circ = 2 * Math.PI * R;
  const dotAngle = ringProgress * 3 * 2 * Math.PI - Math.PI / 2;
  const dotX = 48 + R * Math.cos(dotAngle);
  const dotY = 48 + R * Math.sin(dotAngle);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 300,
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      animation: "loadingColorShift 10s ease-in-out forwards",
      fontFamily: "Lora, Georgia, serif",
    }}>
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(255,255,255,0.025) 0%, transparent 70%)",
        pointerEvents: "none",
      }} />

      <svg width="96" height="96" viewBox="0 0 96 96" style={{ position: "relative", zIndex: 1 }}>
        <circle cx="48" cy="48" r={R} fill="none"
          stroke="rgba(255,255,255,0.06)" strokeWidth="0.8" />
        <circle cx="48" cy="48" r={R} fill="none"
          stroke="rgba(255,255,255,0.38)" strokeWidth="0.8"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - ringProgress)}
          transform="rotate(-90 48 48)" />
        <circle cx={dotX} cy={dotY} r="2" fill="rgba(255,255,255,0.55)" />
        <circle cx="48" cy="48" r="1.2" fill="rgba(255,255,255,0.18)" />
      </svg>

      <p style={{
        marginTop: 28, fontSize: 11,
        letterSpacing: "0.28em", textTransform: "uppercase",
        color: "rgba(255,255,255,0.62)",
        textAlign: "center",
      }}>
        {label}
      </p>

      {/* 阶段指示 */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        marginTop: 14, position: "relative", zIndex: 1,
      }}>
        {["colors", "emotion"].map((p, i) => {
          const order = ["colors", "emotion"];
          const cur = order.indexOf(phase);
          const done = i < cur;
          const active = i === cur;
          return (
            <div key={p} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 5, height: 5, borderRadius: "50%",
                backgroundColor: done ? GOLD : active ? "rgba(255,255,255,0.75)" : "rgba(255,255,255,0.18)",
                transition: "background-color 0.4s ease",
              }} />
              {i === 0 && (
                <div style={{
                  width: 22, height: 1,
                  backgroundColor: done ? `${GOLD}88` : "rgba(255,255,255,0.14)",
                  transition: "background-color 0.4s ease",
                }} />
              )}
            </div>
          );
        })}
      </div>

      <p style={{
        marginTop: 14, fontSize: 10,
        color: "rgba(255,255,255,0.5)", letterSpacing: "0.16em",
      }}>
        {phase === "colors"
          ? "Step 1 of 2 · measuring"
          : `Step 2 of 2 · ${elapsed < 12 ? "usually 10-25s" : "still working…"}`}
      </p>
    </div>
  );
}

// ─── Upload Page (with preset gallery) ────────────────────────────────────────

function UploadPage({ onFile, onSelect, initialScene = 0, initialView = "grid" }: {
  onFile: (f: File) => void;
  onSelect: (id: string) => void;
  initialScene?: number;
  initialView?: "grid" | "list";
}) {
  const [drag, setDrag] = useState(false);
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [ruler, setRuler] = useState<Record<string, RulerItem>>({});
  const [sigPlaying, setSigPlaying] = useState<string | null>(null);
  const sigAudio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    fetch("/api/ruler").then((r) => r.json()).then((d) => {
      const map: Record<string, RulerItem> = {};
      (d.items || []).forEach((i: RulerItem) => { map[i.id] = i; });
      setRuler(map);
    }).catch(() => {});
    return () => { sigAudio.current?.pause(); sigAudio.current = null; };
  }, []);

  const playSignature = (id: string) => {
    if (sigPlaying === id) {
      sigAudio.current?.pause();
      setSigPlaying(null);
      return;
    }
    sigAudio.current?.pause();
    setSigPlaying(id);
    fetch("/api/signature", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.wav_url) { setSigPlaying(null); return; }
        const a = new Audio(d.wav_url);
        sigAudio.current = a;
        a.addEventListener("ended", () => setSigPlaying(null));
        a.play().catch(() => setSigPlaying(null));
      })
      .catch(() => setSigPlaying(null));
  };
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/gallery")
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d)) setItems(d); })
      .catch(() => {});
  }, []);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) onFile(f);
  };

  // ── 场景导航（一叠幻灯片，而不是一条长滚动）────────────────────
  const TOTAL = 7;
  const [scene, setScene] = useState(initialScene);
  const [view, setView] = useState<"grid" | "list">(initialView);
  const [sel, setSel] = useState<string[]>([]);
  const toggleSel = (id: string) =>
    setSel((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id].slice(-2)));
  const go = (n: number) => setScene(Math.max(0, Math.min(TOTAL - 1, n)));
  const next = () => go(scene + 1);
  const prev = () => go(scene - 1);

  useEffect(() => {
    let lock = 0;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(e.key)) { e.preventDefault(); next(); }
      else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) { e.preventDefault(); prev(); }
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(TOTAL - 1);
    };
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) < 12) return;
      const now = Date.now();
      if (now - lock < 700) return;
      lock = now;
      if (e.deltaY > 0) next(); else prev();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("wheel", onWheel, { passive: true });
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("wheel", onWheel);
    };
  }, [scene]);

  // 触屏：上下滑
  const touchY = useRef(0);
  const onTouchStart = (e: React.TouchEvent) => { touchY.current = e.touches[0].clientY; };
  const onTouchEnd = (e: React.TouchEvent) => {
    const dy = e.changedTouches[0].clientY - touchY.current;
    if (Math.abs(dy) > 48) { if (dy < 0) next(); else prev(); }
  };

  const kickerStyle: React.CSSProperties = {
    fontSize: 9.5, letterSpacing: "0.3em", textTransform: "uppercase",
    color: "rgba(201,168,76,0.78)", marginBottom: 18,
  };
  const h2Style: React.CSSProperties = {
    fontSize: "clamp(22px, 3.4vw, 34px)", lineHeight: 1.3, fontWeight: 400,
    color: "rgba(255,255,255,0.92)", letterSpacing: "-0.01em", margin: "0 0 22px",
  };
  const bodyStyle: React.CSSProperties = {
    fontSize: 13, lineHeight: 2, color: "rgba(255,255,255,0.6)", maxWidth: 580,
  };

  const scenes: { kicker: string; node: React.ReactElement }[] = [
    // 01 · 封面
    {
      kicker: "An instrument",
      node: (
        <div style={{ textAlign: "center", maxWidth: 760 }}>
          <h1 style={{
            fontSize: "clamp(30px, 5vw, 52px)", lineHeight: 1.16, fontWeight: 400,
            color: "rgba(255,255,255,0.94)", letterSpacing: "-0.015em", margin: "0 0 26px",
          }}>
            Colour, translated —<br />with the seams showing.
          </h1>
          <p style={{ ...bodyStyle, margin: "0 auto", maxWidth: 520, color: "rgba(255,255,255,0.55)" }}>
            Reading a painting's colour as sound, with the mapping, the evidence and the failures
            all visible.
          </p>
          <div style={{ marginTop: 46, fontFamily: "monospace", fontSize: 10, letterSpacing: "0.16em", color: "rgba(255,255,255,0.32)" }}>
            → or scroll · to begin
          </div>
        </div>
      ),
    },
    // 02 · 问题：为什么不能直接说"它在听画"
    {
      kicker: "Why this exists",
      node: (
        <div style={{ maxWidth: 660 }}>
          <h2 style={h2Style}>
            Most colour-to-sound tools claim the machine hears the painting.<br />
            We tested that claim, and it did not hold.
          </h2>
          <p style={bodyStyle}>
            Three things we could measure, and did — with the numbers on the page rather than in a
            footnote.
          </p>
          <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 14 }}>
            {[
              ["1 of 3", "correct when three canvases are offered — chance level. The mapping does not identify the painting."],
              ["−23.78 / 1317", "what the music model returned when asked for −25.3 dBFS / 2733 Hz. It does not execute the parameters."],
              ["1598 vs 1000 Hz", "drift between two renders of one painting, versus the difference between two paintings. The noise is larger."],
            ].map(([n, t]) => (
              <div key={n} style={{ display: "flex", gap: 18, alignItems: "baseline" }}>
                <span style={{
                  fontFamily: "monospace", fontSize: 12, color: "rgba(217,140,140,0.85)",
                  width: 130, flexShrink: 0,
                }}>{n}</span>
                <span style={{ fontSize: 11.5, lineHeight: 1.75, color: "rgba(255,255,255,0.55)" }}>{t}</span>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    // 03 · 我们声称什么
    {
      kicker: "What we claim",
      node: (
        <div style={{ maxWidth: 720 }}>
          <h2 style={h2Style}>Three layers. Only the middle one is a claim about the painting.</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 20, marginTop: 8 }}>
            {[
              ["I", "Measurement", "L*, saturation, edge density — read off the canvas. Nothing inferred."],
              ["II", "The rule layer", "Three mappings with citations: lightness → pitch, saturation → loudness, lightness → timbre. Each render measured against its own target."],
              ["III", "The shell", "Suno turns a description into music. A reading of the painting, not a translation of it."],
            ].map(([n, t, d]) => (
              <div key={n} style={{ display: "flex", gap: 20 }}>
                <span style={{
                  fontFamily: "monospace", fontSize: 10, color: "rgba(201,168,76,0.8)",
                  width: 26, flexShrink: 0, paddingTop: 3,
                }}>{n}</span>
                <div>
                  <div style={{ fontSize: 14, letterSpacing: "0.06em", color: "rgba(255,255,255,0.86)", marginBottom: 5 }}>
                    {t}
                  </div>
                  <div style={{ fontSize: 11.5, lineHeight: 1.8, color: "rgba(255,255,255,0.5)", maxWidth: 520 }}>
                    {d}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    // 04 · 我们不声称什么
    {
      kicker: "What we do not claim",
      node: (
        <div style={{ maxWidth: 680 }}>
          <h2 style={h2Style}>Three things this instrument does not do — each one measured.</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 6 }}>
            {[
              "Recognise the painting from its sound. Three alternatives, one correct.",
              "Reproduce those numbers faithfully. Asked for −25.3 dBFS / 2733 Hz, the shell returned −23.78 / 1317.",
              "Tell nine paintings apart by ear alone — the same three-alternative test, the same chance result.",
            ].map((t2, i) => (
              <div key={i} style={{ display: "flex", gap: 14, alignItems: "baseline" }}>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: "rgba(217,140,140,0.75)", flexShrink: 0 }}>—</span>
                <span style={{ fontSize: 12, lineHeight: 1.85, color: "rgba(255,255,255,0.6)" }}>{t2}</span>
              </div>
            ))}
          </div>
          <div style={{
            marginTop: 30, paddingTop: 16, borderTop: "1px solid rgba(255,255,255,0.08)",
            fontFamily: "monospace", fontSize: 9.5, letterSpacing: "0.1em", color: "rgba(255,255,255,0.34)",
          }}>
            each "not" above is a measurement, not a caveat
          </div>
        </div>
      ),
    },
    // 05 · 怎么用
    {
      kicker: "How it works",
      node: (
        <div style={{ maxWidth: 820, width: "100%" }}>
          <h2 style={h2Style}>Open a painting and you get three stations.</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 0, marginTop: 10 }}>
            {[
              ["01", "Look", "what the machine measures first, and what a red–green eye loses"],
              ["02", "Translate", "this painting's own five-note motif, one rule at a time"],
              ["03", "Check", "a blind test, and a self-test you can run yourself"],
            ].map(([n, name, line], k) => (
              <div key={n} style={{
                padding: "22px 20px",
                borderLeft: k === 0 ? "none" : "1px solid rgba(255,255,255,0.07)",
                borderTop: "1px solid rgba(255,255,255,0.07)",
                borderBottom: "1px solid rgba(255,255,255,0.07)",
              }}>
                <div style={{ fontFamily: "monospace", fontSize: 9.5, color: "rgba(201,168,76,0.75)", marginBottom: 9 }}>{n}</div>
                <div style={{ fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.82)", marginBottom: 8 }}>{name}</div>
                <div style={{ fontSize: 10.5, lineHeight: 1.75, color: "rgba(255,255,255,0.45)" }}>{line}</div>
              </div>
            ))}
          </div>
          <p style={{ ...bodyStyle, marginTop: 24, fontSize: 11.5, color: "rgba(255,255,255,0.45)" }}>
            ← / → moves between stations · J / K moves between paintings · everything except the
            shell runs locally and costs nothing.
          </p>
        </div>
      ),
    },
    // 06 · 九幅示例（grid / list 两种看法，同屏切换）
    {
      kicker: "The nine",
      node: (
        <div style={{ maxWidth: 900, width: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
            <h2 style={{ ...h2Style, margin: 0, fontSize: "clamp(17px, 2.3vw, 23px)" }}>
              {view === "grid"
                ? "Nine paintings, chosen so the mapping can be argued with."
                : "The same nine, as parameters — the list shows what the sound is made of."}
            </h2>
            <button
              onClick={() => setView(view === "grid" ? "list" : "grid")}
              style={{
                background: "none", border: "none", cursor: "pointer", padding: 0,
                fontSize: 9.5, letterSpacing: "0.12em", textTransform: "uppercase",
                color: "rgba(255,255,255,0.5)", whiteSpace: "nowrap", marginLeft: 20,
              }}
            >
              {view === "grid" ? "as a list →" : "as a grid →"}
            </button>
          </div>

          {view === "grid" ? (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
              gap: 12, overflowY: "auto", paddingRight: 4,
            }}>
              {items.map((it) => (
                <button
                  key={it.id}
                  onClick={() => onSelect(it.id)}
                  aria-label={`open ${it.title} by ${it.artist}`}
                  style={{
                    background: "none", border: "none", padding: 0,
                    cursor: "pointer", textAlign: "left", display: "block",
                    borderRadius: 3, overflow: "hidden",
                  }}
                >
                  <div style={{
                    width: "100%", aspectRatio: "4 / 3", overflow: "hidden",
                    border: "1px solid rgba(255,255,255,0.09)", borderRadius: 3,
                    transition: "border-color 0.25s",
                  }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${GOLD}77`; }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.09)"; }}
                  >
                    <img
                      src={it.thumb_small} alt={it.title} decoding="async"
                      style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                    />
                  </div>
                  <div style={{ paddingTop: 7 }}>
                    <div style={{
                      fontSize: 10.5, lineHeight: 1.35, color: "rgba(255,255,255,0.74)",
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}>
                      {it.title}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                      <div style={{
                        fontSize: 9, color: "rgba(255,255,255,0.42)",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {it.artist} · {it.year}
                      </div>
                      <span
                        role="button" tabIndex={0}
                        title="hear this painting's sound signature"
                        aria-label={`play sound signature for ${it.title}`}
                        onClick={(e) => { e.stopPropagation(); playSignature(it.id); }}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); playSignature(it.id); } }}
                        style={{
                          width: 16, height: 16, borderRadius: "50%", flexShrink: 0,
                          border: `1px solid ${sigPlaying === it.id ? GOLD : "rgba(255,255,255,0.2)"}`,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 6, color: sigPlaying === it.id ? GOLD : "rgba(255,255,255,0.5)",
                          background: sigPlaying === it.id ? `${GOLD}18` : "transparent",
                          cursor: "pointer",
                        }}
                      >
                        {sigPlaying === it.id ? "■" : "▶"}
                      </span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <>
            <div style={{ overflowY: "auto", minHeight: 0, paddingRight: 4 }}>
              {items.map((it, i) => {
                const r = ruler[it.id];
                return (
                  <div
                    key={it.id}
                    onClick={() => onSelect(it.id)}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "26px 1fr auto auto 20px",
                      alignItems: "center", gap: 14,
                      padding: "5px 6px",
                      borderTop: "1px solid rgba(255,255,255,0.07)",
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.025)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
                  >
                    <span style={{ fontFamily: "monospace", fontSize: 9.5, color: "rgba(255,255,255,0.32)" }}>
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <span style={{
                        display: "block", fontSize: 11, color: "rgba(255,255,255,0.8)",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {it.title}
                      </span>
                      <span style={{ display: "block", fontSize: 9.5, color: "rgba(255,255,255,0.42)" }}>
                        {it.artist} · {it.year}
                      </span>
                    </span>
                    <span title="pitch note · loudness target · brightness target" style={{
                      fontFamily: "monospace", fontSize: 9.5, color: "rgba(255,255,255,0.5)",
                      whiteSpace: "nowrap",
                    }}>
                      {r ? `${r.note} · ${r.loudness_db} dBFS · ${r.centroid_hz} Hz` : "—"}
                    </span>
                    <span
                      role="button" tabIndex={0}
                      title="hear this painting's sound signature"
                      aria-label={`play sound signature for ${it.title}`}
                      onClick={(e) => { e.stopPropagation(); playSignature(it.id); }}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); playSignature(it.id); } }}
                      style={{
                        width: 20, height: 20, borderRadius: "50%",
                        border: `1px solid ${sigPlaying === it.id ? GOLD : "rgba(255,255,255,0.2)"}`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 6.5, color: sigPlaying === it.id ? GOLD : "rgba(255,255,255,0.5)",
                        background: sigPlaying === it.id ? `${GOLD}18` : "transparent",
                        cursor: "pointer",
                      }}
                    >
                      {sigPlaying === it.id ? "■" : "▶"}
                    </span>
                    <span
                      role="checkbox"
                      aria-checked={sel.includes(it.id)}
                      tabIndex={0}
                      title="add to comparison"
                      onClick={(e) => { e.stopPropagation(); toggleSel(it.id); }}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); toggleSel(it.id); } }}
                      style={{
                        width: 16, height: 16, borderRadius: 2,
                        border: `1px solid ${sel.includes(it.id) ? GOLD : "rgba(255,255,255,0.22)"}`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 8, color: GOLD, cursor: "pointer",
                        background: sel.includes(it.id) ? `${GOLD}20` : "transparent",
                      }}
                    >
                      {sel.includes(it.id) ? "✓" : ""}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* 两行并排 → 就地对比，不跳页 */}
            {sel.length > 0 && (() => {
              const a = items.find((x) => x.id === sel[0]);
              const b = items.find((x) => x.id === sel[1]);
              const ra = a ? ruler[a.id] : undefined;
              const rb = b ? ruler[b.id] : undefined;
              const ds = ra && rb ? Math.abs((ra.anchor_midi || 0) - (rb.anchor_midi || 0)) : null;
              const dh = ra && rb ? Math.abs((ra.centroid_hz || 0) - (rb.centroid_hz || 0)) : null;
              const same = ds != null && dh != null && ds <= 0.55 && dh <= 80;
              return (
                <div style={{
                  flexShrink: 0, marginTop: 10, paddingTop: 10,
                  borderTop: "1px solid rgba(255,255,255,0.08)",
                  display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
                }}>
                  {[a, b].map((it, k) => (
                    <div key={k} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                      <span style={{ fontFamily: "monospace", fontSize: 9, color: "rgba(255,255,255,0.35)" }}>
                        {k === 0 ? "A" : "B"}
                      </span>
                      <span style={{
                        fontSize: 10.5, color: it ? "rgba(255,255,255,0.72)" : "rgba(255,255,255,0.28)",
                        maxWidth: 190, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {it ? it.title : "pick one more"}
                      </span>
                      {it && (
                        <span
                          role="button" tabIndex={0}
                          aria-label={`play ${it.title}`}
                          onClick={(e) => { e.stopPropagation(); playSignature(it.id); }}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); playSignature(it.id); } }}
                          style={{
                            width: 16, height: 16, borderRadius: "50%",
                            border: `1px solid ${sigPlaying === it.id ? GOLD : "rgba(255,255,255,0.2)"}`,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 6, color: sigPlaying === it.id ? GOLD : "rgba(255,255,255,0.5)",
                            cursor: "pointer",
                          }}
                        >
                          {sigPlaying === it.id ? "■" : "▶"}
                        </span>
                      )}
                    </div>
                  ))}

                  <span style={{ flex: 1 }} />

                  {ds != null && dh != null && (
                    <span style={{
                      fontFamily: "monospace", fontSize: 9.5,
                      color: same ? "rgba(217,140,140,0.9)" : "rgba(255,255,255,0.5)",
                    }}>
                      Δ {ds.toFixed(1)} semitone · Δ {Math.round(dh)} Hz
                      {" — "}
                      {same ? "the same sound" : "different enough to hear"}
                    </span>
                  )}

                  <button
                    onClick={() => setSel([])}
                    style={{
                      background: "none", border: "none", cursor: "pointer", padding: 0,
                      fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase",
                      color: "rgba(255,255,255,0.4)",
                    }}
                  >
                    clear
                  </button>
                </div>
              );
            })()}
            </>
          )}
        </div>
      ),
    },
    // 07 · 你的画
    {
      kicker: "Now your own",
      node: (
        <div style={{ maxWidth: 620, textAlign: "center" }}>
          <h2 style={h2Style}>The nine are references. The instrument is for your image.</h2>
          <p style={{ ...bodyStyle, margin: "0 auto 30px", maxWidth: 480 }}>
            Drop a painting and the same three rules run on it — locally, in about a second,
            without touching an API. If it falls outside the supported range, it says so instead
            of inventing a result.
          </p>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            style={{
              width: "100%", maxWidth: 440, height: 148, margin: "0 auto",
              border: `1px dashed rgba(255,255,255,${drag ? "0.5" : "0.2"})`,
              borderRadius: 4,
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 14,
              cursor: "pointer",
              backgroundColor: drag ? "rgba(255,255,255,0.035)" : "rgba(255,255,255,0.012)",
              transition: "border-color 0.2s, background 0.2s",
            }}
          >
            <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
              <path d="M14 20V8M8 14l6-6 6 6" stroke="rgba(255,255,255,0.34)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <rect x="7" y="22" width="14" height="1" rx="0.5" fill="rgba(255,255,255,0.16)" />
            </svg>
            <div style={{ textAlign: "center" }}>
              <p style={{ fontSize: 14, color: "rgba(255,255,255,0.7)", letterSpacing: "0.04em", marginBottom: 6 }}>
                Drop a painting
              </p>
              <p style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>or click to browse</p>
            </div>
            <input
              ref={inputRef} type="file" accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
            />
          </div>
          <p style={{ marginTop: 14, marginBottom: 4, fontSize: 10, letterSpacing: "0.12em", color: "rgba(255,255,255,0.36)" }}>
            JPG · PNG · WEBP · GIF&nbsp;&nbsp;·&nbsp;&nbsp;runs locally, no account, no credits
          </p>
        </div>
      ),
    },
  ];

  return (
    <div
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      style={{
        position: "fixed", inset: 0, zIndex: 300,
        backgroundColor: UPLOAD_BG,
        fontFamily: "Lora, Georgia, serif",
        animation: "bgFadeIn 0.6s ease",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}
    >
      {/* 顶栏 */}
      <div style={{
        position: "relative", zIndex: 2,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "16px 30px", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
          <span style={{ fontSize: 9.5, letterSpacing: "0.34em", textTransform: "uppercase", color: "rgba(255,255,255,0.5)" }}>
            Colour · Sound
          </span>
          <span style={{ width: 1, height: 11, backgroundColor: "rgba(255,255,255,0.16)" }} />
          <div style={{ display: "flex", gap: 18 }}>
            <button
              onClick={() => { setScene(5); setView("list"); }}
              style={{
                background: "none", border: "none", cursor: "pointer", padding: 0,
                fontSize: 9.5, letterSpacing: "0.2em", textTransform: "uppercase",
                color: "rgba(255,255,255,0.62)",
              }}>Collection</button>
          </div>
        </div>
        <span style={{
          fontFamily: "monospace", fontSize: 9.5, letterSpacing: "0.14em",
          color: "rgba(255,255,255,0.34)",
        }}>
          {String(scene + 1).padStart(2, "0")} / {String(TOTAL).padStart(2, "0")}
        </span>
      </div>

      {/* 当前场景 */}
      <div style={{
        flex: 1, minHeight: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "10px 30px 0",
      }}>
        <div
          key={scene}
          style={{
            width: "100%", display: "flex", flexDirection: "column",
            alignItems: "center", maxHeight: "100%",
            animation: "fadeUpDeck 0.5s cubic-bezier(0.16,1,0.3,1) both",
          }}
        >
          <div style={{ ...kickerStyle }}>{scenes[scene].kicker}</div>
          {scenes[scene].node}
        </div>
      </div>

      {/* 翻页 */}
      <div style={{
        flexShrink: 0, padding: "14px 30px 22px",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 20,
      }}>
        <button
          onClick={prev}
          disabled={scene === 0}
          style={{
            background: "none", border: "none", padding: 0, cursor: scene === 0 ? "default" : "pointer",
            fontSize: 9.5, letterSpacing: "0.2em", textTransform: "uppercase",
            color: scene === 0 ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.55)",
          }}
        >
          ← back
        </button>

        <div style={{ display: "flex", gap: 7 }}>
          {Array.from({ length: TOTAL }).map((_, i) => (
            <button
              key={i}
              onClick={() => go(i)}
              aria-label={`scene ${i + 1}`}
              style={{
                width: i === scene ? 18 : 6, height: 6, padding: 0, border: "none",
                borderRadius: 3, cursor: "pointer",
                backgroundColor: i === scene ? GOLD : "rgba(255,255,255,0.22)",
                transition: "width 0.25s, background-color 0.25s",
              }}
            />
          ))}
        </div>

        {scene < TOTAL - 1 ? (
          <button
            onClick={next}
            style={{
              background: "none", border: "none", padding: 0, cursor: "pointer",
              fontSize: 9.5, letterSpacing: "0.2em", textTransform: "uppercase",
              color: GOLD,
            }}
          >
            next →
          </button>
        ) : (
          <button
            onClick={() => inputRef.current?.click()}
            style={{
              background: "none", border: "none", padding: 0, cursor: "pointer",
              fontSize: 9.5, letterSpacing: "0.2em", textTransform: "uppercase",
              color: GOLD,
            }}
          >
            choose a file ↑
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Compare (两幅并排：把"听起来一样"变成可以亲耳核对的事) ─────────────────

const COLLECTION_CRITERIA = [
  "Colour carries the structure or the emotion. No tint applied to a drawing.",
  "1908–1968: one century, five programmes — Fauvism, Tahitian Gauguin, Colour Field, Bauhaus, post-war abstraction.",
  "Built as a test set, not a best-of. Two extremes are in on purpose: Matisse at 47% one lightness, Rothko at 6%.",
];

// ─── Records (留档列表) ───────────────────────────────────────────────────────

interface RecordItem {
  key: string; saved_at: string; image: string; title: string; artist: string;
  identity: string; anchor: string; bpm: number | string; prompt_source: string;
  n_audio: number; has_saliency: boolean; is_gallery: boolean;
}

function RecordsPage({ onBack, onOpen }: { onBack: () => void; onOpen: (id: string) => void }) {
  const [rows, setRows] = useState<RecordItem[] | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    fetch("/api/records").then((r) => r.json())
      .then((d) => setRows(d.items || []))
      .catch(() => setRows([]));
  }, []);

  const list = (rows || []).filter((r) =>
    !filter || `${r.title} ${r.artist} ${r.image} ${r.key}`.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 300, backgroundColor: "#12100d",
      overflowY: "auto", padding: "44px 24px 60px",
      fontFamily: "Lora, Georgia, serif", color: "#e8eaf2",
      animation: "bgFadeIn 0.5s ease",
    }}>
      <div style={{ maxWidth: 860, margin: "0 auto" }}>
        <button
          onClick={onBack}
          style={{
            background: "none", border: "1px solid rgba(255,255,255,0.2)", borderRadius: 3,
            color: "rgba(255,255,255,0.65)", fontSize: 10, letterSpacing: "0.14em",
            textTransform: "uppercase", padding: "6px 12px", cursor: "pointer", marginBottom: 26,
          }}
        >
          ← back
        </button>

        <h1 style={{
          fontFamily: "Playfair Display, Georgia, serif", fontSize: 34,
          fontWeight: 400, color: "#f4ede0", marginBottom: 8,
        }}>
          Archive
        </h1>
        <p style={{ fontSize: 12, lineHeight: 1.8, color: "rgba(255,255,255,0.6)", marginBottom: 22, maxWidth: 560 }}>
          每次分析都会留一份记录：颜色测量、规则层（含参考编号）、显著区域、基础声音的目标与实测、
          prompt 及其来源、已生成的音频。
        </p>

        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter by title / artist / file"
          aria-label="filter records"
          style={{
            width: "100%", maxWidth: 320, marginBottom: 18, padding: "8px 10px",
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.16)",
            borderRadius: 3, color: "#e8eaf2", fontSize: 11, fontFamily: "monospace", outline: "none",
          }}
        />

        {rows === null && (
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>loading…</div>
        )}
        {rows !== null && list.length === 0 && (
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>no records yet</div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {list.map((r) => (
            <div
              key={r.key}
              onClick={() => r.is_gallery && onOpen(r.key)}
              role={r.is_gallery ? "button" : undefined}
              tabIndex={r.is_gallery ? 0 : undefined}
              onKeyDown={(e) => { if (r.is_gallery && (e.key === "Enter" || e.key === " ")) onOpen(r.key); }}
              style={{
                display: "flex", alignItems: "baseline", gap: 12, padding: "10px 12px",
                borderBottom: "1px solid rgba(255,255,255,0.07)",
                cursor: r.is_gallery ? "pointer" : "default",
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) => { if (r.is_gallery) e.currentTarget.style.background = "rgba(201,168,76,0.06)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              <span style={{ fontSize: 9.5, fontFamily: "monospace", color: "rgba(255,255,255,0.45)", width: 116, flexShrink: 0 }}>
                {r.saved_at.slice(5, 16)}
              </span>
              <span style={{ fontSize: 12, color: "rgba(255,255,255,0.85)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.title}
                {r.artist && <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11 }}> · {r.artist}</span>}
              </span>
              <span style={{ fontSize: 9.5, fontFamily: "monospace", color: "rgba(255,255,255,0.5)", width: 40, textAlign: "right" }}>{r.anchor}</span>
              <span style={{ fontSize: 9.5, fontFamily: "monospace", color: "rgba(255,255,255,0.4)", width: 34, textAlign: "right" }}>{r.bpm}</span>
              <span style={{
                fontSize: 8.5, letterSpacing: "0.1em", textTransform: "uppercase", width: 96, textAlign: "right",
                color: r.identity === "opencv-hash" ? "#8fc98f" : "rgba(255,255,255,0.4)",
              }}>
                {r.identity || "—"}
              </span>
              <span style={{
                fontSize: 9.5, fontFamily: "monospace", width: 52, textAlign: "right",
                color: r.n_audio > 0 ? GOLD : "rgba(255,255,255,0.3)",
              }}>
                {r.n_audio > 0 ? `♪${r.n_audio}` : "—"}
              </span>
            </div>
          ))}
        </div>

        <p style={{ marginTop: 18, fontSize: 9.5, color: "rgba(255,255,255,0.4)" }}>
          列：时间 / 作品 / anchor / BPM / 身份来源 / 音频数。点击预置画作的记录可以直接打开。
        </p>
      </div>
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [page, setPage] = useState<"upload" | "loading" | "viewer" | "records">(() => {
    if (typeof window === "undefined") return "upload";
    const path = window.location.pathname.replace(/\/+$/, "");
    if (path === "/records") return "records";
    return "upload";           // /collection 也落到 deck，用 scene 6 + list 模式
  });
  // deck 的初始屏/视图：/collection 深链直接开第 06 屏的列表
  const [deckOpts, setDeckOpts] = useState<{ scene: number; view: "grid" | "list" }>(() => {
    if (typeof window === "undefined") return { scene: 0, view: "grid" };
    return window.location.pathname.replace(/\/+$/, "") === "/collection"
      ? { scene: 5, view: "list" }
      : { scene: 0, view: "grid" };
  });
  const [phase, setPhase] = useState<"colors" | "emotion">("colors");
  const [data, setData] = useState<ArtworkData | null>(null);
  const [localImageUrl, setLocalImageUrl] = useState<string | null>(null);

  // 批次 C: 显著性 + 基础声音
  const [sal, setSal] = useState<SaliencyData | null>(null);
  const [rulerItems, setRulerItems] = useState<RulerItem[]>([]);
  const [salBusy, setSalBusy] = useState(false);
  const [showHeat, setShowHeat] = useState(false);
  const [openRef, setOpenRef] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const [prevData, setPrevData] = useState<PreviewData | null>(null);
  const [prevBusy, setPrevBusy] = useState(false);
  const [prevErr, setPrevErr] = useState("");
  const [cvd, setCvd] = useState<{ urls: Record<string, string>; labels: Record<string, string>; notes: string[] } | null>(null);
  const [layers, setLayers] = useState<{
    layer: number; label: string; wav_url: string;
    measured: { rms_dbfs: number; spectral_centroid_hz: number };
    voices: number; notes?: { start_s: number; midi: number }[]; seconds?: number;
  }[] | null>(null);
  const [layerSel, setLayerSel] = useState(3);
  const [rollRatio, setRollRatio] = useState(0);
  const [scan, setScan] = useState<{ wav_url: string; line: { t: number; midi: number }[]; seconds: number; voices: any[]; edge_mean?: number; rate_hz?: number; events?: number } | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [paletteUrl, setPaletteUrl] = useState<string>("");
  const [layerTargets, setLayerTargets] = useState<{ loudness_target_db: number; brightness_target_hz: number; pitch_anchor_midi: number } | null>(null);
  const pendingLayerRef = useRef<number | null>(null);
  const [abPick, setAbPick] = useState<"A" | "B" | null>(null);
  const [abReveal, setAbReveal] = useState(false);
  const [abSwap] = useState(() => Math.random() < 0.5);   // true: A=基础声音
  const [station, setStation] = useState<number | "lab">(0);
  const [present, setPresent] = useState<boolean>(() =>
    typeof window !== "undefined" && /[?&]present/.test(window.location.search)
  );
  const compact = useViewport(900);   // <900 单栏（手机上两栏会把正文压成一行四个字）

  // ── 演示模式: 去壳 + 全宽 + ←/→ 翻页 + Esc 退出 ──────────────
  useEffect(() => {
    document.documentElement.dataset.present = present ? "1" : "0";
  }, [present]);

  useEffect(() => {
    document.documentElement.dataset.activeStation = String(station);
  }, [station]);


  useEffect(() => {
    if (!present) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setPresent(false); return; }
      const el = rightRef.current;
      if (!el) return;
      const pageH = el.clientHeight * 0.88;
      if (e.key === "ArrowRight" || e.key === "ArrowDown" || e.key === "PageDown") {
        e.preventDefault();
        el.scrollBy({ top: pageH, behavior: "smooth" });
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp" || e.key === "PageUp") {
        e.preventDefault();
        el.scrollBy({ top: -pageH, behavior: "smooth" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [present]);

  // ── 键盘：←/→ 切站、1–4 跳站、L 后台、空格播放 ────────────────
  useEffect(() => {
    if (page !== "viewer" || present) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setStation((s) => (s === "lab" ? 0 : Math.min(2, s + 1)));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setStation((s) => (s === "lab" ? 0 : Math.max(0, s - 1)));
      } else if (["1", "2", "3"].includes(e.key)) {
        setStation(Number(e.key) - 1);
      } else if (e.key === "l" || e.key === "L") {
        setStation((s) => (s === "lab" ? 0 : "lab"));
      } else if (e.key === "j" || e.key === "J" || e.key === "k" || e.key === "K") {
        const i = rulerItems.findIndex((r) => r.id === data?.id);
        if (i >= 0 && rulerItems.length > 1) {
          e.preventDefault();
          const step = e.key === "j" || e.key === "J" ? 1 : -1;
          loadArtwork(rulerItems[(i + step + rulerItems.length) % rulerItems.length].id, true, true);
        }
      } else if (e.key === " ") {
        const btn = document.querySelector<HTMLButtonElement>('[aria-label="play preview"], [aria-label="pause preview"]');
        if (btn) { e.preventDefault(); btn.click(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [page, present, rulerItems, data?.id]);

  type MusicState = "idle" | "generating" | "playing" | "paused";
  const [musicState, setMusicState] = useState<MusicState>("idle");
  const [progress, setProgress] = useState(0);
  const playing = musicState === "playing";
  const [zoomed, setZoomed] = useState(false);
  const [revealRaw, setRevealRaw] = useState(0);
  const [rightTopPad, setRightTopPad] = useState(56);

  // 音乐生成状态
  const [genState, setGenState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [genLog, setGenLog] = useState("");
  const [genError, setGenError] = useState("");
  const [usage, setUsage] = useState<{ used: number; limit: number; enabled: boolean } | null>(null);
  const pollRef = useRef<number | null>(null);
  // 一次生成会产出 2 首, 允许切换
  const [audioList, setAudioList] = useState<string[]>([]);
  const [audioIdx, setAudioIdx] = useState(0);

  const revealRef = useRef(0);
  const pageRef = useRef<"upload" | "loading" | "viewer" | "records">("upload");
  const rafRef = useRef<number | null>(null);
  const touchStartY = useRef<number | null>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const paintingRef = useRef<HTMLImageElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const reveal = easeOut(revealRaw);

  // 是否已在本次流程中进入 viewer, 防止旧数据触发重复跳转
  const enteredRef = useRef(false);

  const resetForNewLoad = useCallback((keepStation = false) => {
    enteredRef.current = false;
    setData(null);            // 清空旧数据 —— 关键
    setLocalImageUrl(null);
    setRevealRaw(0);
    revealRef.current = 0;
    setMusicState("idle");
    setProgress(0);
    // 每幅画派生的东西都要清，否则换画时会把上一幅的显著图/取样点/声音留在屏幕上
    setSal(null);
    setCvd(null);
    setLayers(null);
    setScan(null);
    setPrevData(null);
    setShowHeat(false);
    setOpenRef(null);
    setZoomed(false);
    if (!keepStation) setStation(0);
    // 重置生成状态
    if (pollRef.current) { window.clearInterval(pollRef.current); pollRef.current = null; }
    setGenState("idle");
    setGenLog("");
    setGenError("");
    setAudioList([]);
    setAudioIdx(0);
    if (rightRef.current) rightRef.current.scrollTop = 0;
  }, []);

  // ── Load artwork from backend ────────────────────────────────
  const loadArtwork = useCallback(async (id: string, push = true, keepStation = false) => {
    if (push) {
      try { window.history.pushState({ c2m: true }, "", `/a/${encodeURIComponent(id)}`); } catch { /* ignore */ }
    }
    resetForNewLoad(keepStation);
    pageRef.current = "loading";
    setPhase("colors");
    setPage("loading");
    try {
      const r = await fetch(`/api/artwork/${encodeURIComponent(id)}`);
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      setData(d);
      // 已生成过的音频直接列出
      if (d.audio_urls?.length) {
        setAudioList(d.audio_urls);
        setAudioIdx(0);
        setGenState("done");
      }
    } catch (e) {
      console.error(e);
      pageRef.current = "upload";
      setPage("upload");
    }
  }, [resetForNewLoad]);

  // ── 路由：/a/<id> 深链、/collection、浏览器后退 ────────────────
  const sigAudioRef = useRef<HTMLAudioElement | null>(null);

  const playSignature = (id: string) => {
    sigAudioRef.current?.pause();
    fetch("/api/signature", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.wav_url) return;
        const a = new Audio(d.wav_url);
        sigAudioRef.current = a;
        a.play().catch(() => {});
      })
      .catch(() => {});
  };

  useEffect(() => {
    const onPop = () => {
      const path = window.location.pathname;
      const m = path.match(/^\/a\/(.+?)\/?$/);
      if (m) { loadArtwork(decodeURIComponent(m[1]), false); return; }
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      resetForNewLoad();
      if (path.startsWith("/collection")) {
        setDeckOpts({ scene: 5, view: "list" });
        pageRef.current = "upload"; setPage("upload"); return;
      }
      if (path.startsWith("/records")) { pageRef.current = "records"; setPage("records"); return; }
      pageRef.current = "upload";
      setPage("upload");
    };
    window.addEventListener("popstate", onPop);
    // 首次进入若带 /a/<id>，直接打开
    const m0 = window.location.pathname.match(/^\/a\/(.+?)\/?$/);
    if (m0) loadArtwork(decodeURIComponent(m0[1]), false);
    return () => window.removeEventListener("popstate", onPop);
  }, [loadArtwork, resetForNewLoad]);

  // ── Analyze uploaded file (two phases) ───────────────────────
  const handleFile = useCallback(async (file: File) => {
    resetForNewLoad();
    pageRef.current = "loading";
    setPhase("colors");
    setPage("loading");

    const objectUrl = URL.createObjectURL(file);
    const fd = new FormData();
    fd.append("file", file);

    try {
      // 阶段 1: 颜色分析 (本地计算, 通常 1-2 秒)
      const r1 = await fetch("/api/analyze", { method: "POST", body: fd });
      const c = await r1.json();
      if (c.error) throw new Error(c.error);

      setLocalImageUrl(objectUrl);
      const token: string = c.token;
      if (!token) throw new Error("no token returned");

      // 阶段 2: Gemini 情感分析 (约 8-15 秒)
      setPhase("emotion");
      let ai: any = { ai_available: false, ai_error: "" };
      try {
        const r2 = await fetch("/api/emotion", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        ai = await r2.json();
      } catch (e) {
        ai = { ai_available: false, ai_error: String(e) };
      }

      // 合并: 颜色 + AI 识别与情感 (AI 失败时用规则兜底)
      const fb = c.fallback || {};
      const merged: ArtworkData = {
        ...c,
        // AI 看图得出的作品信息 (优先于文件名)
        title: ai.title || c.title || "Untitled",
        artist: ai.artist || "Unknown",
        year: ai.year || "",
        medium: ai.medium || "",
        movement: ai.movement || "",
        // AI 识别的流派 → 对应的时代音乐风格
        era_style: ai.era_style || c.era_style,
        mood: ai.ai_available ? (ai.mood || "") : "",
        valence: ai.ai_available ? ai.valence : fb.valence ?? 0,
        arousal: ai.ai_available ? ai.arousal : fb.arousal ?? 0,
        tension: ai.ai_available ? ai.tension : 0,
        narrative: ai.ai_available ? (ai.narrative || "") : (fb.narrative || ""),
        musical_hint: ai.ai_available ? (ai.musical_hint || "") : "",
        // ⭐ 音乐 prompt 由 /api/emotion 一并返回 (以前上传图拿不到 -> 出不了歌)
        music_prompt: ai.music_prompt || c.music_prompt || "",
        music_prompt_source: ai.music_prompt_source || "",
        mapping: ai.mapping || c.mapping,
        ai_available: !!ai.ai_available,
        ai_error: ai.ai_error || ai.error || "",
      };
      setData(merged);
    } catch (e) {
      console.error(e);
      URL.revokeObjectURL(objectUrl);
      pageRef.current = "upload";
      setPage("upload");
    }
  }, [resetForNewLoad]);

  // ── When data arrives, show viewer (once per load) ───────────
  useEffect(() => {
    if (page === "loading" && data && !enteredRef.current) {
      enteredRef.current = true;
      // 单栏(手机)不做揭示动画，直接展开，避免用户以为加载卡住
      // 揭示动画只在第一次进入时播放；之后直接展开
      let already = false;
      try { already = localStorage.getItem("c2m_revealed") === "1"; } catch { already = false; }
      const skip = (typeof window !== "undefined" && window.innerWidth < 900) || already;
      setRevealRaw(skip ? 1 : 0);
      revealRef.current = skip ? 1 : 0;
      pageRef.current = "viewer";
      setPage("viewer");
    }
  }, [page, data]);

  // ── 映射标尺: 十幅画的参数一次取齐（服务端有缓存）────────────
  useEffect(() => {
    if (page !== "viewer" || rulerItems.length) return;
    let alive = true;
    const body = data?.id ? {} : { token: data?.token };
    fetch("/api/ruler", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((d) => { if (alive && d.items) setRulerItems(d.items); })
      .catch(() => {});
    return () => { alive = false; };
  }, [page, data?.id, data?.token]);

  // ── 批次 C: 显著图自动计算 (OpenCV, 本地, 不耗额度) ─────────────
  const sourceKey = data?.id || data?.token || "";

  useEffect(() => {
    if (page !== "viewer" || !sourceKey) return;
    setSal(null);
    setPrevData(null);
    setPrevErr("");
    setLayers(null);
    setCvd(null);
    setAbReveal(false);
    setAbPick(null);
    setSalBusy(true);
    let alive = true;
    const body = data?.id ? { id: data.id } : { token: data?.token };
    fetch("/api/cvd", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((d) => { if (alive && d.urls) setCvd(d); })
      .catch(() => {});
    fetch("/api/saliency", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((d) => { if (alive && !d.error) setSal(d); })
      .catch(() => {})
      .finally(() => { if (alive) setSalBusy(false); });
    return () => { alive = false; };
  }, [page, sourceKey]);

  // ── 批次 C: 基础声音 (MIDI + 合成, 15 秒, 可测量) ───────────────
  const handlePreview = () => {
    if (!data || prevBusy) return;
    setPrevBusy(true);
    setPrevErr("");
    const body = { ...(data.id ? { id: data.id } : { token: data.token }), seconds: 15 };
    fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok || d.error) throw new Error(d.error || "preview failed");
        setPrevData(d);
      })
      .catch((e) => setPrevErr(String(e.message || e)))
      .finally(() => setPrevBusy(false));
  };

  // ── 导出卡: 一张 1200×630 的 PNG，画 + 参数 + 出处 ──────────
  const exportCard = async () => {
    if (!data) return;
    const W = 1200, H = 630;
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    if (!g) return;

    g.fillStyle = "#0d0f14"; g.fillRect(0, 0, W, H);
    g.strokeStyle = "rgba(201,168,76,0.35)"; g.lineWidth = 1;
    g.strokeRect(28, 28, W - 56, H - 56);

    const img = new Image();
    img.src = imageUrl;
    await new Promise<void>((res) => { img.onload = () => res(); img.onerror = () => res(); });
    if (img.width) {
      const boxH = 470, boxW = 470;
      const s = Math.min(boxW / img.width, boxH / img.height);
      const dw = img.width * s, dh = img.height * s;
      g.drawImage(img, 70 + (boxW - dw) / 2, 80 + (boxH - dh) / 2, dw, dh);
    }

    const x = 600;
    let y = 110;
    g.fillStyle = "#f4ede0"; g.font = "38px Georgia, 'Playfair Display', serif";
    const title = data.title || "";
    const words = title.split(" ");
    let line = "";
    for (const w of words) {
      if (g.measureText(`${line} ${w}`).width > 520 && line) { g.fillText(line, x, y); y += 44; line = w; }
      else line = line ? `${line} ${w}` : w;
    }
    if (line) { g.fillText(line, x, y); y += 30; }

    g.fillStyle = "#c9a84c"; g.font = "italic 21px Georgia, serif";
    g.fillText(`${data.artist || ""}${data.year ? " · " + data.year : ""}`, x, y); y += 46;

    const p2: any = (data.mapping && data.mapping.params) || {};
    g.font = "17px 'Courier New', monospace"; g.fillStyle = "rgba(255,255,255,0.72)";
    const rows = [
      ["pitch anchor", `${p2.pitch_note || "—"} · MIDI ${p2.pitch_anchor_midi ?? "—"}`],
      ["loudness", `${p2.loudness_target_db ?? "—"} dBFS`],
      ["brightness", `${p2.brightness_target_hz ?? "—"} Hz`],
      ["tempo / mode", `${p2.bpm ?? "—"} BPM · ${p2.mode ?? "—"}`],
    ];
    for (const [k, v] of rows) {
      g.fillStyle = "rgba(255,255,255,0.45)"; g.fillText(k, x, y);
      g.fillStyle = "rgba(255,255,255,0.85)"; g.fillText(v, x + 160, y);
      y += 30;
    }

    y += 16;
    g.fillStyle = "#c9a84c"; g.font = "13px 'Courier New', monospace";
    g.fillText(`EVIDENCE R1–R3  ·  DESIGN D1–D4  ·  ${(data.mapping && data.mapping.deprecated || []).length} DEPRECATED`, x, y);
    y += 34;
    g.fillStyle = "rgba(255,255,255,0.4)"; g.font = "13px 'Courier New', monospace";
    g.fillText("colour → sound, every mapping traceable", x, y);
    g.fillText(window.location.origin, x, y + 22);

    const a = document.createElement("a");
    a.download = `colour-to-music-${data.id || "card"}.png`;
    a.href = c.toDataURL("image/png");
    a.click();
  };

  // 取样点一起奏成一个和弦（色卡即和弦）
  const playPalette = (ordered = false) => {
    if (!data) return;
    const body = { ...(data.id ? { id: data.id } : { token: data.token }), ordered };
    fetch("/api/palette", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((d) => { if (d.wav_url) setPaletteUrl(`${d.wav_url}?t=${Date.now()}`); })
      .catch(() => {});
  };

  // 用 OpenCV 显著区域做"建议点"，用户仍可清空
  // ── 分层试听（stem player）────────────────────────────────────
  const loadLayers = () => {
    if (!data || prevBusy) return;
    setPrevBusy(true);
    setPrevErr("");
    const body = { ...(data.id ? { id: data.id } : { token: data.token }), layers: true, seconds: 8 };
    fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok || d.error) throw new Error(d.error || "layers failed");
        setLayers(d.layers || []);
        setLayerTargets(d.targets || null);
        setLayerSel(pendingLayerRef.current ?? ((d.layers || []).length || 3));
        pendingLayerRef.current = null;
      })
      .catch((e) => setPrevErr(String(e.message || e)))
      .finally(() => setPrevBusy(false));
  };

  // ── 站点的「下一步」：按需触发该站的动作 ──────────────────
  const stationHint = (() => {
    if (station === 1 && !layers) return "one click renders the three layers locally (no credits)";
    return "";
  })();

  const nextLabel = (() => {
    if (station === "lab") return "back to the room";
    if (station === 0) return layers ? "hear the rules" : "render the rules";
    if (station === 1) return "does it hold up";
    return "next painting";
  })();

  const nextStep = () => {
    if (station === "lab") { setStation(0); return; }
    if (station === 0) {
      if (!layers) { loadLayers(); return; }
      setStation(1); return;
    }
    if (station === 1) { setStation(2); return;
    }
    // station 3 → 下一幅
    const idx = rulerItems.findIndex((i) => i.id === data?.id);
    const nextId = rulerItems[(idx + 1) % Math.max(1, rulerItems.length)]?.id;
    if (nextId && nextId !== data?.id) loadArtwork(nextId);
    else { pageRef.current = "upload"; setPage("upload"); }
  };

  // ── 扫描式声化：画面结构 → 时间与音区 ───────────────────
  const loadScan = () => {
    if (!data || scanBusy) return;
    setScanBusy(true);
    setPrevErr("");
    const body = { ...(data.id ? { id: data.id } : { token: data.token }), seconds: 22 };
    fetch("/api/scan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok || d.error) throw new Error(d.error || "scan failed");
        setScan({
          wav_url: d.wav_url, line: d.line || [], seconds: d.seconds || 22, voices: d.voices || [],
          edge_mean: d.edge_mean, rate_hz: d.rate_hz, events: d.events,
        });
        setLayerSel(5);
      })
      .catch((e) => setPrevErr(String(e.message || e)))
      .finally(() => setScanBusy(false));
  };

  // 盲听：A/B 的归属随机；规则层取最后一层（三层全开）
  const baseLayer = layers ? (layers[layers.length - 1] || null) : null;
  const baseClip = baseLayer?.wav_url || "";
  const baseMeasured = baseLayer?.measured || null;
  const abSrc = (k: "A" | "B") => ((k === "A") === abSwap ? baseClip : (data?.audio || ""));

  // ── Audio setup ──────────────────────────────────────────────
  const audioSrc = data?.audio ?? null;

  useEffect(() => {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    if (!audioSrc) return;
    const a = new Audio(audioSrc);
    audioRef.current = a;
    const onTime = () => {
      if (a.duration) setProgress(a.currentTime / a.duration);
    };
    const onEnd = () => { setMusicState("paused"); setProgress(0); };
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("ended", onEnd);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("ended", onEnd);
      a.pause();
    };
  }, [audioSrc]);

  // ── Play / pause ─────────────────────────────────────────────
  const handleMusicClick = () => {
    if (musicState === "generating") return;

    // No audio file yet -> show the prompt instead of pretending
    if (!audioSrc) {
      setMusicState("idle");
      return;
    }
    const a = audioRef.current;
    if (!a) return;
    if (musicState === "playing") {
      a.pause();
      setMusicState("paused");
    } else {
      a.play().then(() => setMusicState("playing")).catch(() => setMusicState("paused"));
    }
  };

  // ── 查询今日用量 ──────────────────────────────────────────────
  useEffect(() => {
    fetch("/api/usage")
      .then((r) => r.json())
      .then((d) => setUsage({ used: d.used ?? 0, limit: d.limit ?? 0, enabled: !!d.enabled }))
      .catch(() => {});
  }, []);

  // 组件卸载时停止轮询
  useEffect(() => () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
  }, []);

  // ── 生成音乐 (页面内确认, 不弹原生窗) ───────────────────────
  const handleGenerate = () => {
    if (!data?.music_prompt) return;
    if (genState === "running") return;

    setConfirmOpen(false);
    setGenState("running");
    setGenLog("Submitting…");
    setGenError("");

    fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        confirm: true,
        id: data.id || undefined,
        token: data.token || undefined,
        title: data.title,
        prompt: data.music_prompt,
      }),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok || d.error) throw new Error(d.error || "failed to start");
        setUsage((u) => u ? { ...u, used: d.used ?? u.used } : u);
        startPolling(d.task_id);
      })
      .catch((e) => {
        setGenState("error");
        setGenError(String(e.message || e));
      });
  };

  const startPolling = (taskId: string) => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const r = await fetch(`/api/task/${taskId}`);
        const t = await r.json();
        setGenLog(t.log || "");
        if (t.status === "done") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          pollRef.current = null;
          setGenState("done");
          const urls: string[] = t.audio_urls?.length
            ? t.audio_urls
            : (t.audio_url ? [t.audio_url] : []);
          setAudioList(urls);
          setAudioIdx(0);
          setData((prev) => prev ? { ...prev, audio: urls[0] ?? null } : prev);
        } else if (t.status === "error") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          pollRef.current = null;
          setGenState("error");
          setGenError(t.error || "generation failed");
        }
      } catch (e) {
        /* 网络抖动, 继续轮询 */
      }
    }, 3000);
  };

  // ── Measure painting top to align right panel ────────────────
  const measurePaintingTop = useCallback(() => {
    if (revealRaw < 0.98 || !paintingRef.current) return;
    const rect = paintingRef.current.getBoundingClientRect();
    setRightTopPad(Math.max(20, rect.top));
  }, [revealRaw]);

  useEffect(() => { measurePaintingTop(); }, [measurePaintingTop]);
  useEffect(() => {
    window.addEventListener("resize", measurePaintingTop);
    return () => window.removeEventListener("resize", measurePaintingTop);
  }, [measurePaintingTop]);

  // ── Animate reveal ───────────────────────────────────────────
  const animateRevealTo = useCallback((target: number, ms = 800) => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    const start = revealRef.current;
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = clamp((now - t0) / ms, 0, 1);
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const next = start + (target - start) * eased;
      revealRef.current = next;
      setRevealRaw(next);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const triggerReveal = () => {
    if (revealRef.current >= 1) return;
    animateRevealTo(1, 1000);
  };

  const handleBack = () => {
    if (audioRef.current) audioRef.current.pause();
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    resetForNewLoad();
    if (localImageUrl) URL.revokeObjectURL(localImageUrl);
    // 有应用内的历史条目就交给浏览器后退，让 popstate 决定回到哪里
    if (window.history.state && (window.history.state as any).c2m) {
      window.history.back();
      return;
    }
    window.history.replaceState({}, "", "/");
    pageRef.current = "upload";
    setPage("upload");
  };

  // ── Global wheel + touch ─────────────────────────────────────
  useEffect(() => {
    const SPEED = 900;
    const onWheel = (e: WheelEvent) => {
      if (pageRef.current !== "viewer") return;   // upload / records 页交给浏览器
      if (window.innerWidth < 900) return;   // 单栏布局: 交给浏览器正常滚动
      e.preventDefault();
      const rightEl = rightRef.current;
      if (revealRef.current < 1) {
        if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
        const next = clamp(revealRef.current + e.deltaY / SPEED, 0, 1);
        revealRef.current = next;
        setRevealRaw(next);
        if (next >= 1) { try { localStorage.setItem("c2m_revealed", "1"); } catch { /* ignore */ } }
      } else if (rightEl) {
        rightEl.scrollTop += e.deltaY * 0.55;
      }
    };
    const onTouchStart = (e: TouchEvent) => { touchStartY.current = e.touches[0].clientY; };
    const onTouchMove = (e: TouchEvent) => {
      if (pageRef.current === "upload" || touchStartY.current === null) return;
      if (window.innerWidth < 900 || e.touches.length !== 1) return;  // 不拦双指缩放
      const dy = touchStartY.current - e.touches[0].clientY;
      touchStartY.current = e.touches[0].clientY;
      const rightEl = rightRef.current;
      if (revealRef.current < 1) {
        e.preventDefault();
        const next = clamp(revealRef.current + dy / 400, 0, 1);
        revealRef.current = next;
        setRevealRaw(next);
      } else if (rightEl) {
        rightEl.scrollTop += dy;
      }
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
    };
  }, []);

  // ── Animation values ────────────────────────────────────────
  const leftOpacity = remap(reveal, 0.1, 0.7);
  const leftSlide = (1 - leftOpacity) * -40;
  const rightTitleOpacity = remap(reveal, 0.65, 1);
  const rightTitleSlide = (1 - rightTitleOpacity) * 12;
  const contentOpacity = remap(reveal, 0.75, 1);
  const introOpacity = clamp(1 - reveal / 0.85, 0, 1);
  const introShift = reveal * 18;
  const introScale = 1 - reveal * 0.15;

  const imageUrl = localImageUrl ?? data?.image ?? "";

  const palette = data?.palette ?? [];
  // 上传的图只有 AI 识别出的年份/材质, 尺寸未知 —— 缺项不显示
  const meta = [data?.year, data?.medium, data?.dimensions]
    .filter((x) => x && String(x).trim())
    .join("  ·  ");
  const introMeta = [data?.year, data?.movement].filter(Boolean).join("  ·  ");

  return (
    <>
      <ModeToggle />
      {page === "viewer" && (
        <button
          onClick={() => setPresent((v) => !v)}
          className="present-hide"
          aria-label="toggle presentation mode"
          title="presentation mode (Esc to exit)"
          style={{
            position: "fixed", top: 14, right: 108, zIndex: 400,
            background: present ? `${GOLD}22` : "rgba(10,10,14,0.72)",
            border: `1px solid ${present ? GOLD : "rgba(255,255,255,0.16)"}`,
            borderRadius: 3, padding: "5px 8px", cursor: "pointer",
            fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase",
            color: present ? GOLD : "rgba(255,255,255,0.5)",
            backdropFilter: "blur(6px)",
          }}
        >
          ⛶ present
        </button>
      )}
      {page === "viewer" && (
        <StationRail
          station={station}
          onPick={(n) => setStation(n)}
          onNext={nextStep}
          nextLabel={nextLabel}
          nextDim={(station === 1 && !layers)}
          hint={stationHint}
        />
      )}
      {page === "upload" && (
        <UploadPage
          key={`deck-${deckOpts.scene}-${deckOpts.view}`}
          initialScene={deckOpts.scene}
          initialView={deckOpts.view}
          onFile={handleFile}
          onSelect={loadArtwork}
        />
      )}
      {page === "records" && (
        <RecordsPage
          onBack={() => {
            window.history.pushState({}, "", "/");
            pageRef.current = "upload";
            setPage("upload");
          }}
          onOpen={(id) => {
            window.history.pushState({}, "", "/");
            loadArtwork(id);
          }}
        />
      )}
      {page === "loading" && <LoadingPage phase={phase} />}

      {/* ── Viewer ───────────────────────────────────────────── */}
      {page === "viewer" && data && <div style={{
        position: "relative", width: "100%",
        height: "100%",
        overflow: compact ? "auto" : "hidden",
        fontFamily: "Lora, Georgia, serif",
        color: "#e8eaf2",
        display: "flex",
        flexDirection: compact ? "column" : "row",
        animation: "viewerEnter 1s cubic-bezier(0.16,1,0.3,1) forwards",
      }}>
        {/* ── Background ──────────────────────────────────────── */}
        <div style={{ position: "absolute", inset: 0, zIndex: 0, overflow: "hidden" }}>
          <img src={imageUrl} alt="" aria-hidden style={{
            position: "absolute", inset: 0,
            width: "100%", height: "100%",
            objectFit: "cover",
            filter: "saturate(1.1) brightness(0.95)",
            transform: "scale(1.04)",
            animation: "bgFadeIn 1.2s ease forwards",
          }} />
          <div style={{
            position: "absolute", inset: 0,
            background: "linear-gradient(135deg, rgba(4,6,18,0.65) 0%, rgba(6,10,24,0.58) 100%)",
          }} />
        </div>

        {/* ── Left: painting (fixed) ───────────────────────────── */}
        <div className="present-hide" style={{
          position: "relative", zIndex: 10,
          width: compact ? "100%" : "52%", flexShrink: 0,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: compact ? "flex-start" : "center",
          padding: compact ? "72px 20px 20px" : "40px 32px 100px",
          overflow: "hidden",
          opacity: leftOpacity,
          transform: `translateX(${leftSlide}px)`,
          transition: "opacity 0.12s ease, transform 0.12s ease",
        }}>
          <div
            onClick={() => setZoomed(true)}
            style={{
              width: "100%", maxWidth: 600,
              filter: "drop-shadow(0 24px 64px rgba(0,0,0,0.75)) drop-shadow(0 6px 20px rgba(0,0,0,0.5))",
              cursor: "zoom-in", position: "relative",
            }}
          >
            <img
              ref={paintingRef}
              src={imageUrl}
              alt={data.title}
              style={{ display: "block", width: "100%", maxHeight: compact ? "46vh" : "calc(100vh - 200px)", objectFit: "contain" }}
              onLoad={measurePaintingTop}
            />
            <div style={{
              position: "absolute", bottom: 10, right: 10,
              width: 28, height: 28, borderRadius: "50%",
              backgroundColor: "rgba(0,0,0,0.45)",
              border: "1px solid rgba(255,255,255,0.18)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, color: "rgba(255,255,255,0.6)",
              pointerEvents: "none",
            }}>⊕</div>
          </div>

          {/* Color chips */}
          <div style={{ display: "flex", gap: 20, marginTop: 24, flexWrap: "wrap", justifyContent: "center" }}>
            {palette.map((c, i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%",
                  backgroundColor: c.rgb,
                  border: "1.5px solid rgba(255,255,255,0.18)",
                  boxShadow: `0 3px 12px ${c.rgb}66`,
                }} />
                <span style={{ fontSize: 10, color: "rgba(255,255,255,0.5)", fontFamily: "monospace" }}>
                  {c.hex}
                </span>
              </div>
            ))}
          </div>

          {/* Audio player */}
          <div style={{
            position: compact ? "static" : "absolute",
            bottom: compact ? undefined : 24,
            left: compact ? undefined : "50%",
            transform: compact ? undefined : "translateX(-50%)",
            width: compact ? "100%" : "calc(100% - 64px)",
            maxWidth: 600,
            marginTop: compact ? 20 : 0,
            display: "flex", flexDirection: "column", gap: 12,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <button
                onClick={handleMusicClick}
                title={audioSrc ? undefined : "No audio generated yet"}
                style={{
                  width: 38, height: 38, borderRadius: "50%",
                  backgroundColor: GOLD, border: "none",
                  cursor: audioSrc ? "pointer" : "default",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 12, color: "#07080e", flexShrink: 0,
                  boxShadow: playing ? `0 0 16px ${GOLD}66` : "none",
                  opacity: audioSrc ? 1 : 0.4,
                  transition: "box-shadow 0.3s, opacity 0.4s ease",
                }}
              >
                {playing ? "⏸" : "▶"}
              </button>

              <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
                <Waveform playing={playing} color={GOLD} count={75} />
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.5)", fontFamily: "monospace" }}>
                    {formatTime(progress * TARGET_DURATION)}
                  </span>
                  <div
                    style={{ flex: 1, height: 1.5, backgroundColor: "rgba(255,255,255,0.14)", borderRadius: 1, cursor: audioSrc ? "pointer" : "default" }}
                    onClick={(e) => {
                      if (!audioSrc || !audioRef.current?.duration) return;
                      const rect = e.currentTarget.getBoundingClientRect();
                      const p = clamp((e.clientX - rect.left) / rect.width, 0, 1);
                      audioRef.current.currentTime = p * audioRef.current.duration;
                      setProgress(p);
                    }}
                  >
                    <div style={{ width: `${progress * 100}%`, height: "100%", backgroundColor: GOLD, borderRadius: 1, transition: "width 0.3s linear" }} />
                  </div>
                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.50)", fontFamily: "monospace" }}>
                    {formatTime(TARGET_DURATION)}
                  </span>
                </div>
              </div>
            </div>
            {!audioSrc && (
              <p style={{
                fontSize: 10, color: "rgba(255,255,255,0.5)",
                letterSpacing: "0.08em", textAlign: "center", margin: 0,
              }}>
                Audio not generated yet — see the music prompt below
              </p>
            )}
          </div>
        </div>

        {/* ── Right: scrollable info ────────────────────────────── */}
        <div
          ref={rightRef}
          className="present-zoom panel-stations"
          tabIndex={0}
          role="region"
          aria-label="artwork analysis"
          style={{
            position: "relative", zIndex: 10,
            flex: 1,
            width: compact ? "100%" : undefined,
            overflowY: compact ? "visible" : "hidden",
            paddingTop: compact ? 12 : rightTopPad,
            paddingRight: compact ? 20 : 48,
            paddingBottom: compact ? 48 : 60,
            paddingLeft: compact ? 20 : 40,
            outline: "none",
            transition: "padding-top 0.4s ease",
          }}
        >
          <h1 style={{
            fontFamily: "Playfair Display, Georgia, serif",
            fontSize: "clamp(36px, 4.5vw, 62px)",
            fontWeight: 400, lineHeight: 1.08, letterSpacing: "-0.01em",
            color: "#f4ede0", marginBottom: 10,
            opacity: rightTitleOpacity,
            transform: `translateY(${rightTitleSlide}px)`,
            transition: "opacity 0.12s ease, transform 0.12s ease",
          }}>
            {data.title}
          </h1>

          <p style={{
            fontFamily: "Playfair Display, Georgia, serif",
            fontSize: 17, fontStyle: "italic",
            color: GOLD, letterSpacing: "0.04em", marginBottom: 6,
            opacity: rightTitleOpacity,
            transform: `translateY(${rightTitleSlide}px)`,
            transition: "opacity 0.12s ease, transform 0.12s ease",
          }}>
            {data.artist && data.artist !== "Unknown" ? data.artist : "uploaded image"}
          </p>

          <div style={{ opacity: contentOpacity, transition: "opacity 0.12s ease" }}>
            {meta && (
              <p style={{ fontSize: 12, color: "rgba(255,255,255,0.52)", letterSpacing: "0.08em", marginBottom: 22 }}>
                {meta}
              </p>
            )}

            <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />

            {/* ── Emotional reading (AI) ─────────────────────── */}
            {/* ── 输入范围闸门：越界的画，先说清楚为什么不适用 ── */}
            {data.gate && !data.gate.ok && !data.matched_id && (
              <div data-station="0" style={{
                marginBottom: 22, padding: "13px 15px", borderRadius: 3,
                border: "1px solid rgba(217,140,140,0.3)", background: "rgba(217,140,140,0.045)",
              }}>
                <div style={{
                  fontSize: 9, letterSpacing: "0.18em", textTransform: "uppercase",
                  color: "rgba(217,140,140,0.92)", marginBottom: 7,
                }}>
                  Outside the supported range
                </div>
                <p style={{ fontSize: 11, lineHeight: 1.8, color: "rgba(255,255,255,0.7)", marginBottom: 9 }}>
                  This instrument only makes claims about painterly works with a readable lightness
                  structure. This image falls outside that range, so the stations below would describe it
                  inaccurately — the map is not designed for it.
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {data.gate.failures.map((f: any) => (
                    <div key={f.key} style={{
                      fontFamily: "monospace", fontSize: 9.5, lineHeight: 1.7,
                      color: "rgba(255,255,255,0.55)",
                    }}>
                      <span style={{ color: "rgba(217,140,140,0.9)" }}>{f.key}</span>
                      {" "}{f.value}
                      {f.max != null ? ` (needs ${f.min}–${f.max})` : ` (needs ≥ ${f.min})`}
                      {" — "}{f.why}
                    </div>
                  ))}
                </div>
                <p style={{ fontSize: 10, lineHeight: 1.7, color: "rgba(255,255,255,0.45)", marginTop: 9 }}>
                  Inside: a painting with visible brushwork, contrast between areas, saturated colour,
                  and a left–right structure. Outside: flat vector art, line drawings, near-monochrome
                  images, and fine repetitive patterns that change faster than the sweep can read.
                </p>
              </div>
            )}

            <div data-station="0" style={{ marginBottom: 22 }}>
              <SectionLabel>01 · Reading</SectionLabel>
              {data.mood && (
                <p style={{
                  fontFamily: "Playfair Display, Georgia, serif",
                  fontSize: 15, fontStyle: "italic", color: GOLD, marginBottom: 14,
                }}>
                  {data.mood}
                </p>
              )}
              <Meter label="Valence" value={data.valence} min={-1} max={1} color="#7fb3d5" />
              <Meter label="Arousal" value={data.arousal} min={0} max={1} color="#d98c5f" />
              <Meter label="Tension" value={data.tension} min={0} max={1} color="#c9556e" />
              {!data.ai_available && (
                <p style={{
                  fontSize: 10, color: "rgba(255,255,255,0.5)", marginTop: 10,
                  letterSpacing: "0.06em",
                }}>
                  AI reading unavailable — showing color-derived estimates
                </p>
              )}
            </div>

            <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />

            {/* ── About the artwork (AI narrative) ───────────── */}
            {data.narrative && (
              <div data-station="0">
                <details style={{ marginBottom: 22 }}>
                  <summary style={{
                    fontSize: 9.5, letterSpacing: "0.18em", textTransform: "uppercase",
                    color: "rgba(255,255,255,0.46)", cursor: "pointer",
                  }}>
                    the model's reading · ai, unedited
                  </summary>
                  <p style={{ fontSize: 12.5, lineHeight: 1.8, color: "rgba(255,255,255,0.6)", marginTop: 9 }}>
                    {data.narrative}
                  </p>
                </details>
                <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />
              </div>
            )}

            {/* ── 作者视角解读（为什么是这幅 / 看这里 / 翻译失败在哪）── */}
            {data.reading && (
              <div data-station="0" style={{ marginBottom: 22 }}>
                <div style={{
                  fontSize: 9.5, letterSpacing: "0.18em", textTransform: "uppercase",
                  color: "rgba(255,255,255,0.5)", marginBottom: 8,
                }}>
                  Why this one
                </div>
                <p style={{ fontSize: 13, lineHeight: 1.8, color: "rgba(255,255,255,0.8)", marginBottom: 16 }}>
                  {data.reading.why}
                </p>

                <div style={{
                  fontSize: 9.5, letterSpacing: "0.18em", textTransform: "uppercase",
                  color: "rgba(255,255,255,0.5)", marginBottom: 10,
                }}>
                  Look here
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                  {(data.reading.notes || []).map((n, i) => (
                    <div key={i} style={{ display: "flex", gap: 11 }}>
                      <span style={{
                        fontFamily: "monospace", fontSize: 9.5, color: `${GOLD}aa`,
                        paddingTop: 2, flexShrink: 0,
                      }}>
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <div style={{ fontSize: 11.5, color: "rgba(255,255,255,0.9)", marginBottom: 2 }}>
                          {n.label}
                        </div>
                        <div style={{ fontSize: 11.5, lineHeight: 1.75, color: "rgba(255,255,255,0.62)" }}>
                          {n.text}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div style={{
                  marginTop: 16, paddingLeft: 12,
                  borderLeft: "1.5px solid rgba(217,140,140,0.55)",
                }}>
                  <div style={{
                    fontSize: 8.5, letterSpacing: "0.18em", textTransform: "uppercase",
                    color: "rgba(217,140,140,0.85)", marginBottom: 5,
                  }}>
                    Where this translation fails
                  </div>
                  <p style={{ fontSize: 11.5, lineHeight: 1.75, color: "rgba(255,255,255,0.68)", margin: 0 }}>
                    {data.reading.fault}
                  </p>
                </div>
              </div>
            )}

            {/* ── Color analysis ─────────────────────────────── */}
            <div data-station="0" style={{ marginBottom: 22 }}>
              <SectionLabel>01 · Colour</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                {[
                  { label: "Dominant", value: data.dominant_hue },
                  { label: "Lightness L*", value: data.mapping?.params?.mean_L },
                  { label: "Saturation S", value: data.mean_S?.toFixed(3) },
                ].filter((x) => x.value !== undefined && x.value !== "").map(({ label, value }) => (
                  <div key={label} style={{ display: "flex", alignItems: "baseline" }}>
                    <span style={{ fontSize: 10, color: "rgba(255,255,255,0.48)", letterSpacing: "0.1em", width: 72, flexShrink: 0 }}>
                      {label}
                    </span>
                    <span style={{ width: 1, height: 12, backgroundColor: "rgba(255,255,255,0.18)", marginRight: 14, flexShrink: 0, alignSelf: "center" }} />
                    <span style={{ fontSize: 13, color: "rgba(255,255,255,0.82)", lineHeight: 1.5 }}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* 三个已不参与映射的统计量：折叠起来，避免被当成"还有隐藏算法" */}
              <details style={{ marginTop: 10 }}>
                <summary style={{ fontSize: 9.5, color: "rgba(255,255,255,0.56)", cursor: "pointer", letterSpacing: "0.04em" }}>
                  for researchers · legacy statistics (not used in mapping)
                </summary>
                <div style={{ marginTop: 7, display: "flex", flexDirection: "column", gap: 4, fontFamily: "monospace", fontSize: 10, color: "rgba(255,255,255,0.5)" }}>
                  <span>V (HSV) {data.mean_V?.toFixed(3)} — 非感知明度，已改用 L*</span>
                  <span>warm ratio {data.warm_ratio?.toFixed(3)} — 旧「暖→大调」规则依据，已废弃</span>
                  <span>RGI {data.rgi?.toFixed(2)} — 旧「红绿→不协和」依据，已废弃</span>
                </div>
              </details>

              {/* 色觉模拟：把「为什么需要听觉」变成可见的 */}
              {cvd && (
                <div style={{ marginTop: 18 }}>
                  <p style={{ fontSize: 11.5, lineHeight: 1.8, color: "rgba(255,255,255,0.74)", marginBottom: 9 }}>
                    The same painting, three eyes. In red–green deficiency the hue channel
                    collapses; what survives is{" "}
                    <b style={{ fontWeight: 500, color: "rgba(255,255,255,0.92)" }}>
                      lightness, saturation and where things are
                    </b>
                    . That residue is exactly what the rules in 05 read.
                  </p>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 7 }}>
                    {(["normal", "deuteranopia", "protanopia"] as const).map((k) => (
                      <figure key={k} style={{ margin: 0 }}>
                        <img
                          src={cvd.urls[k]}
                          alt={cvd.labels[k]}
                          style={{
                            width: "100%", display: "block", borderRadius: 2,
                            border: "1px solid rgba(255,255,255,0.09)",
                            opacity: k === "normal" ? 1 : 0.95,
                          }}
                        />
                        <figcaption style={{
                          marginTop: 4, fontSize: 8, letterSpacing: "0.07em",
                          textTransform: "uppercase", lineHeight: 1.4,
                          color: k === "normal" ? "rgba(255,255,255,0.55)" : `${GOLD}cc`,
                        }}>
                          {cvd.labels[k]}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                  <details style={{ marginTop: 7 }}>
                    <summary style={{ fontSize: 9.5, color: "rgba(255,255,255,0.56)", cursor: "pointer", letterSpacing: "0.04em" }}>
                      simulation method · what this is not
                    </summary>
                    <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                      {(cvd.notes || []).map((n) => (
                        <span key={n} style={{ fontSize: 9.5, lineHeight: 1.65, color: "rgba(255,255,255,0.56)" }}>
                          · {n}
                        </span>
                      ))}
                    </div>
                  </details>
                </div>
              )}
            </div>

            <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />

            {/* ── Emotional reading (AI) ─────────────────────── */}
            {/* ── 输入范围闸门：越界的画，先说清楚为什么不适用 ── */}
            {data.gate && !data.gate.ok && !data.matched_id && (
              <div data-station="0" style={{
                marginBottom: 22, padding: "13px 15px", borderRadius: 3,
                border: "1px solid rgba(217,140,140,0.3)", background: "rgba(217,140,140,0.045)",
              }}>
                <div style={{
                  fontSize: 9, letterSpacing: "0.18em", textTransform: "uppercase",
                  color: "rgba(217,140,140,0.92)", marginBottom: 7,
                }}>
                  Outside the supported range
                </div>
                <p style={{ fontSize: 11, lineHeight: 1.8, color: "rgba(255,255,255,0.7)", marginBottom: 9 }}>
                  This instrument only makes claims about painterly works with a readable lightness
                  structure. This image falls outside that range, so the stations below would describe it
                  inaccurately — the map is not designed for it.
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {data.gate.failures.map((f: any) => (
                    <div key={f.key} style={{
                      fontFamily: "monospace", fontSize: 9.5, lineHeight: 1.7,
                      color: "rgba(255,255,255,0.55)",
                    }}>
                      <span style={{ color: "rgba(217,140,140,0.9)" }}>{f.key}</span>
                      {" "}{f.value}
                      {f.max != null ? ` (needs ${f.min}–${f.max})` : ` (needs ≥ ${f.min})`}
                      {" — "}{f.why}
                    </div>
                  ))}
                </div>
                <p style={{ fontSize: 10, lineHeight: 1.7, color: "rgba(255,255,255,0.45)", marginTop: 9 }}>
                  Inside: a painting with visible brushwork, contrast between areas, saturated colour,
                  and a left–right structure. Outside: flat vector art, line drawings, near-monochrome
                  images, and fine repetitive patterns that change faster than the sweep can read.
                </p>
              </div>
            )}

            <div data-station="0" style={{ marginBottom: 22 }}>
              <SectionLabel>01 · Reading</SectionLabel>
              {data.mood && (
                <p style={{
                  fontFamily: "Playfair Display, Georgia, serif",
                  fontSize: 15, fontStyle: "italic", color: GOLD, marginBottom: 14,
                }}>
                  {data.mood}
                </p>
              )}
              <Meter label="Valence" value={data.valence} min={-1} max={1} color="#7fb3d5" />
              <Meter label="Arousal" value={data.arousal} min={0} max={1} color="#d98c5f" />
              <Meter label="Tension" value={data.tension} min={0} max={1} color="#c9556e" />
              {!data.ai_available && (
                <p style={{
                  fontSize: 10, color: "rgba(255,255,255,0.5)", marginTop: 10,
                  letterSpacing: "0.06em",
                }}>
                  AI reading unavailable — showing color-derived estimates
                </p>
              )}
            </div>

            <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />

            {/* ── About the artwork (AI narrative) ───────────── */}
            {data.narrative && (
              <div data-station="0">
                <details style={{ marginBottom: 22 }}>
                  <summary style={{
                    fontSize: 9.5, letterSpacing: "0.18em", textTransform: "uppercase",
                    color: "rgba(255,255,255,0.46)", cursor: "pointer",
                  }}>
                    the model's reading · ai, unedited
                  </summary>
                  <p style={{ fontSize: 12.5, lineHeight: 1.8, color: "rgba(255,255,255,0.6)", marginTop: 9 }}>
                    {data.narrative}
                  </p>
                </details>
                <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />
              </div>
            )}

            {/* ── 作者视角解读（为什么是这幅 / 看这里 / 翻译失败在哪）── */}
            {data.reading && (
              <div data-station="0" style={{ marginBottom: 22 }}>
                <div style={{
                  fontSize: 9.5, letterSpacing: "0.18em", textTransform: "uppercase",
                  color: "rgba(255,255,255,0.5)", marginBottom: 8,
                }}>
                  Why this one
                </div>
                <p style={{ fontSize: 13, lineHeight: 1.8, color: "rgba(255,255,255,0.8)", marginBottom: 16 }}>
                  {data.reading.why}
                </p>

                <div style={{
                  fontSize: 9.5, letterSpacing: "0.18em", textTransform: "uppercase",
                  color: "rgba(255,255,255,0.5)", marginBottom: 10,
                }}>
                  Look here
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                  {(data.reading.notes || []).map((n, i) => (
                    <div key={i} style={{ display: "flex", gap: 11 }}>
                      <span style={{
                        fontFamily: "monospace", fontSize: 9.5, color: `${GOLD}aa`,
                        paddingTop: 2, flexShrink: 0,
                      }}>
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <div style={{ fontSize: 11.5, color: "rgba(255,255,255,0.9)", marginBottom: 2 }}>
                          {n.label}
                        </div>
                        <div style={{ fontSize: 11.5, lineHeight: 1.75, color: "rgba(255,255,255,0.62)" }}>
                          {n.text}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div style={{
                  marginTop: 16, paddingLeft: 12,
                  borderLeft: "1.5px solid rgba(217,140,140,0.55)",
                }}>
                  <div style={{
                    fontSize: 8.5, letterSpacing: "0.18em", textTransform: "uppercase",
                    color: "rgba(217,140,140,0.85)", marginBottom: 5,
                  }}>
                    Where this translation fails
                  </div>
                  <p style={{ fontSize: 11.5, lineHeight: 1.75, color: "rgba(255,255,255,0.68)", margin: 0 }}>
                    {data.reading.fault}
                  </p>
                </div>
              </div>
            )}

            {/* ── Color analysis ─────────────────────────────── */}
            <div data-station="0" style={{ marginBottom: 22 }}>
              <SectionLabel>01 · Colour</SectionLabel>
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                {[
                  { label: "Dominant", value: data.dominant_hue },
                  { label: "Lightness L*", value: data.mapping?.params?.mean_L },
                  { label: "Saturation S", value: data.mean_S?.toFixed(3) },
                ].filter((x) => x.value !== undefined && x.value !== "").map(({ label, value }) => (
                  <div key={label} style={{ display: "flex", alignItems: "baseline" }}>
                    <span style={{ fontSize: 10, color: "rgba(255,255,255,0.48)", letterSpacing: "0.1em", width: 72, flexShrink: 0 }}>
                      {label}
                    </span>
                    <span style={{ width: 1, height: 12, backgroundColor: "rgba(255,255,255,0.18)", marginRight: 14, flexShrink: 0, alignSelf: "center" }} />
                    <span style={{ fontSize: 13, color: "rgba(255,255,255,0.82)", lineHeight: 1.5 }}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* 三个已不参与映射的统计量：折叠起来，避免被当成"还有隐藏算法" */}
              <details style={{ marginTop: 10 }}>
                <summary style={{ fontSize: 9.5, color: "rgba(255,255,255,0.56)", cursor: "pointer", letterSpacing: "0.04em" }}>
                  for researchers · legacy statistics (not used in mapping)
                </summary>
                <div style={{ marginTop: 7, display: "flex", flexDirection: "column", gap: 4, fontFamily: "monospace", fontSize: 10, color: "rgba(255,255,255,0.5)" }}>
                  <span>V (HSV) {data.mean_V?.toFixed(3)} — 非感知明度，已改用 L*</span>
                  <span>warm ratio {data.warm_ratio?.toFixed(3)} — 旧「暖→大调」规则依据，已废弃</span>
                  <span>RGI {data.rgi?.toFixed(2)} — 旧「红绿→不协和」依据，已废弃</span>
                </div>
              </details>

              {/* 色觉模拟：把「为什么需要听觉」变成可见的 */}
              {cvd && (
                <div style={{ marginTop: 18 }}>
                  <p style={{ fontSize: 11.5, lineHeight: 1.8, color: "rgba(255,255,255,0.74)", marginBottom: 9 }}>
                    The same painting, three eyes. In red–green deficiency the hue channel
                    collapses; what survives is{" "}
                    <b style={{ fontWeight: 500, color: "rgba(255,255,255,0.92)" }}>
                      lightness, saturation and where things are
                    </b>
                    . That residue is exactly what the rules in 05 read.
                  </p>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 7 }}>
                    {(["normal", "deuteranopia", "protanopia"] as const).map((k) => (
                      <figure key={k} style={{ margin: 0 }}>
                        <img
                          src={cvd.urls[k]}
                          alt={cvd.labels[k]}
                          style={{
                            width: "100%", display: "block", borderRadius: 2,
                            border: "1px solid rgba(255,255,255,0.09)",
                            opacity: k === "normal" ? 1 : 0.95,
                          }}
                        />
                        <figcaption style={{
                          marginTop: 4, fontSize: 8, letterSpacing: "0.07em",
                          textTransform: "uppercase", lineHeight: 1.4,
                          color: k === "normal" ? "rgba(255,255,255,0.55)" : `${GOLD}cc`,
                        }}>
                          {cvd.labels[k]}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                  <details style={{ marginTop: 7 }}>
                    <summary style={{ fontSize: 9.5, color: "rgba(255,255,255,0.56)", cursor: "pointer", letterSpacing: "0.04em" }}>
                      simulation method · what this is not
                    </summary>
                    <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                      {(cvd.notes || []).map((n) => (
                        <span key={n} style={{ fontSize: 9.5, lineHeight: 1.65, color: "rgba(255,255,255,0.56)" }}>
                          · {n}
                        </span>
                      ))}
                    </div>
                  </details>
                </div>
              )}
            </div>

            <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />

            {/* ── Mapping: 规则与出处 (批次B) ─────────────────── */}
            {data.mapping && (
              <div data-station="lab" style={{ marginBottom: 22 }}>
                <SectionLabel>Lab · Mapping</SectionLabel>
                <button
                  onClick={() => {
                    window.history.pushState({ c2m: true }, "", "/records");
                    pageRef.current = "records";
                    setPage("records");
                  }}
                  style={{
                    background: "none", border: "none", cursor: "pointer", padding: 0,
                    marginBottom: 12, marginTop: -4, display: "block",
                    fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase",
                    color: "rgba(255,255,255,0.42)",
                  }}
                >
                  analysis records →
                </button>
                {rulerItems.length > 0 && (
                  <Ruler
                    items={rulerItems}
                    currentId={data.id || data.token}
                    onPick={(id) => {
                      if (!id || id === (data.id || data.token)) return;
                      if (rulerItems.some((r) => r.id === id && !r.is_you)) loadArtwork(id);
                    }}
                  />
                )}
                <div style={{ fontSize: 10, color: "rgba(255,255,255,0.52)", lineHeight: 1.65, marginBottom: 12 }}>
                  <span style={{ color: `${GOLD}dd` }}>Evidence</span> = 有颜色–声音实验支持的方向；
                  <span style={{ color: "rgba(255,255,255,0.55)" }}> Design</span> = 项目/AI 的编排选择。
                  <span className="lab-only">数值区间均为本项目设定，不是论文公式。</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                  {([...data.mapping.evidence, ...data.mapping.design]).map((r) => {
                    const ev = r.kind === "evidence";
                    return (
                      <div key={r.rule_id} style={{
                        borderLeft: `1.5px solid ${ev ? GOLD : "rgba(255,255,255,0.16)"}`,
                        paddingLeft: 12,
                      }}>
                        <div className="lab-only" style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 3 }}>
                          <span style={{ fontSize: 9, letterSpacing: "0.12em", fontFamily: "monospace", color: ev ? GOLD : "rgba(255,255,255,0.45)" }}>
                            {r.rule_id}
                          </span>
                          <span style={{ fontSize: 8, letterSpacing: "0.18em", textTransform: "uppercase", color: ev ? `${GOLD}cc` : "rgba(255,255,255,0.5)" }}>
                            {ev ? "evidence" : "design"}
                          </span>
                          {r.refs.length > 0 && (
                            <span style={{ display: "flex", gap: 6 }}>
                              {r.refs.map((id) => (
                                <button
                                  key={id}
                                  onClick={() => setOpenRef(openRef === id ? null : id)}
                                  aria-label={`reference ${id}`}
                                  title="show full citation"
                                  style={{
                                    background: "none", border: "none", padding: 0, cursor: "pointer",
                                    fontSize: 8, letterSpacing: "0.1em",
                                    color: openRef === id ? GOLD : "rgba(255,255,255,0.5)",
                                    textDecoration: "underline", textUnderlineOffset: 2,
                                  }}
                                >
                                  {id}
                                </button>
                              ))}
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 11.5, color: "rgba(255,255,255,0.76)", lineHeight: 1.55 }}>{r.sentence}</div>
                        {ev && ["R1", "R2", "R3"].includes(r.rule_id) ? (
                          <button
                            onClick={() => {
                              const n = Number(r.rule_id.slice(1));
                              pendingLayerRef.current = n;
                              setStation(1);
                              if (layers) setLayerSel(n); else loadLayers();
                            }}
                            style={{
                              marginTop: 5, background: "none", border: `1px solid ${GOLD}55`,
                              borderRadius: 3, padding: "3px 8px", cursor: "pointer",
                              fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase",
                              color: GOLD,
                            }}
                          >
                            ▶ hear it · L{r.rule_id.slice(1)}
                          </button>
                        ) : (
                          <div style={{ marginTop: 5, fontSize: 9, letterSpacing: "0.06em", color: "rgba(255,255,255,0.4)" }}>
                            not audible in the base sound — prompt only
                          </div>
                        )}
                        <div className="lab-only" style={{ fontSize: 10.5, color: "rgba(255,255,255,0.5)", fontFamily: "monospace", lineHeight: 1.65 }}>
                          {r.input.name} {r.input.value}
                          {r.input.unit && r.input.unit !== "—" ? ` ${r.input.unit}` : ""}
                          {" → "}
                          {r.output.name}{" "}
                          <span style={{ color: ev ? GOLD : "rgba(255,255,255,0.72)" }}>{r.output.value}</span>
                          {r.output.unit && r.output.unit !== "—" ? ` ${r.output.unit}` : ""}
                        </div>
                        {r.note && (
                          <div style={{ fontSize: 9.5, color: "rgba(255,255,255,0.5)", lineHeight: 1.55, marginTop: 2 }}>
                            {r.note}
                          </div>
                        )}
                        {!!openRef && r.refs.includes(openRef) && (
                          <div style={{
                            fontSize: 9.5, color: "rgba(255,255,255,0.72)", lineHeight: 1.6,
                            marginTop: 5, borderLeft: `1px solid ${GOLD}55`, paddingLeft: 8,
                          }}>
                            <b style={{ color: GOLD, fontWeight: 500 }}>{openRef}</b>{" "}
                            {data.mapping?.refs?.[openRef] || "(citation missing)"}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {data.mapping.deprecated && data.mapping.deprecated.length > 0 && (
                  <details style={{ marginTop: 14 }}>
                    <summary style={{ fontSize: 10, letterSpacing: "0.08em", color: "rgba(255,255,255,0.54)", cursor: "pointer" }}>
                      Removed / downgraded rules ({data.mapping.deprecated.length})
                    </summary>
                    <div style={{ marginTop: 9, display: "flex", flexDirection: "column", gap: 7 }}>
                      {data.mapping.deprecated.map((x) => (
                        <div key={x.id} style={{ fontSize: 10, color: "rgba(255,255,255,0.55)", lineHeight: 1.6 }}>
                          <span style={{ color: "rgba(217,140,140,0.85)" }}>✕ {x.old_rule}</span>
                          <br />→ {x.now}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}

            <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />
            {/* ── 06 Sound Preview (批次C / P1-4) ─────────────── */}
            <div data-station="1" style={{ marginBottom: 24 }}>
              <SectionLabel>02 · Rule-checked sound</SectionLabel>
              <div style={{ fontSize: 11.5, color: "rgba(255,255,255,0.7)", lineHeight: 1.8, marginBottom: 12 }}>
                Three rules, switched on one at a time. Every layer keeps the same melody — this
                painting's own five-note motif, read down the canvas — so only loudness and timbre
                change. Each render is measured, so you can check that the rule did what it claims.
              </div>

              {!layers ? (
                <button
                  onClick={loadLayers}
                  disabled={prevBusy}
                  style={{
                    padding: "10px 18px",
                    backgroundColor: "transparent",
                    border: `1px solid ${GOLD}66`,
                    borderRadius: 4,
                    color: prevBusy ? "rgba(201,168,76,0.5)" : GOLD,
                    fontFamily: "Lora, serif",
                    fontSize: 11, letterSpacing: "0.18em", textTransform: "uppercase",
                    cursor: prevBusy ? "default" : "pointer",
                  }}
                >
                  {prevBusy ? "Rendering…" : "Render the three rules"}
                </button>
              ) : (
                <>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 11 }}>
                    {layers.map((l) => {
                      const on = layerSel === l.layer;
                      return (
                        <button
                          key={l.layer}
                          onClick={() => setLayerSel(l.layer)}
                          style={{
                            ...chipBtn,
                            borderColor: on ? GOLD : "rgba(255,255,255,0.18)",
                            color: on ? GOLD : "rgba(255,255,255,0.66)",
                            background: on ? `${GOLD}14` : "rgba(255,255,255,0.04)",
                          }}
                        >
                          L{l.layer} · {l.label}
                        </button>
                      );
                    })}
                    <button
                      onClick={() => { if (scan) setLayerSel(5); else loadScan(); }}
                      style={{
                        ...chipBtn,
                        borderColor: layerSel === 5 ? GOLD : "rgba(255,255,255,0.18)",
                        color: layerSel === 5 ? GOLD : "rgba(255,255,255,0.66)",
                        background: layerSel === 5 ? `${GOLD}14` : "rgba(255,255,255,0.04)",
                      }}
                    >
                      {scanBusy ? "L5 · scanning…" : "L5 · surface, not identity"}
                    </button>
                  </div>


                  <div style={{ marginBottom: 12 }}>
                    <MiniPlayer
                      key={`layer-${layerSel}`}
                      src={layerSel === 5 ? (scan?.wav_url || "") : (layers.find((l) => l.layer === layerSel) || layers[0]).wav_url}
                      onProgress={setRollRatio}
                    />
                  </div>

                  {layerSel === 5 && scan ? (
                    <>
                      <ScanTrace line={scan.line} seconds={scan.seconds} />
                      {scan.edge_mean != null && (
                        <div style={{
                          display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8,
                          fontFamily: "monospace", fontSize: 10,
                          color: "rgba(255,255,255,0.55)",
                        }}>
                          <span>edge density <span style={{ color: GOLD }}>{scan.edge_mean}</span></span>
                          <span>→ <span style={{ color: GOLD }}>{scan.rate_hz}</span> events / second</span>
                          <span>→ <span style={{ color: GOLD }}>{scan.events}</span> notes in {Math.round(scan.seconds)}s</span>
                        </div>
                      )}
                      <p style={{ fontSize: 9.5, lineHeight: 1.7, color: "rgba(255,255,255,0.52)", marginTop: 8 }}>
                        The three layers share one melody — and that melody is this painting's own
                        five-note motif, read down the canvas in five horizontal bands, played twice.
                        L5 is a different reading: the sweep moves left to right instead, pitch from
                        lightness on an absolute scale, and how often a note fires from how busy the
                        surface is — a soft Rothko ticks once a second, a busy grid six times.
                        x → time and y → register are design choices (D5/D6); the evidence rules still
                        set pitch, loudness and timbre.
                      </p>
                      <div style={{
                        marginTop: 10, padding: "10px 12px", borderRadius: 3,
                        border: "1px solid rgba(217,140,140,0.28)",
                        background: "rgba(217,140,140,0.04)",
                      }}>
                        <div style={{
                          fontSize: 8.5, letterSpacing: "0.18em", textTransform: "uppercase",
                          color: "rgba(217,140,140,0.9)", marginBottom: 5,
                        }}>
                          Tested, and it does not identify the painting
                        </div>
                        <p style={{ fontSize: 10.5, lineHeight: 1.75, color: "rgba(255,255,255,0.66)", margin: 0 }}>
                          A three-alternative test on three canvases scored{" "}
                          <span style={{ color: "rgba(255,255,255,0.85)" }}>1 of 3 — chance level</span>.
                          The one correct match was the sparsest canvas; the two busy ones were swapped.
                          So this layer conveys <em>how much is happening</em>, not <em>which painting
                          it is</em>. Identity would need shape and layout, and this mapping discards both.
                        </p>
                      </div>
                    </>
                  ) : (() => {
                    const L = layers.find((l) => l.layer === layerSel) || layers[0];
                    return (
                      <PianoRoll
                        notes={L.notes || []}
                        seconds={L.seconds || 8}
                        ratio={rollRatio}
                        voices={L.voices}
                      />
                    );
                  })()}

                  <div className="lab-only" style={{ display: "flex", flexDirection: "column", fontFamily: "monospace", fontSize: 10 }}>
                    <div style={{
                      display: "flex", gap: 10, paddingBottom: 4, marginBottom: 3,
                      borderBottom: "1px solid rgba(255,255,255,0.09)",
                      fontSize: 8.5, letterSpacing: "0.09em", textTransform: "uppercase",
                      color: "rgba(255,255,255,0.44)",
                    }}>
                      <span style={{ width: 20 }}>#</span>
                      <span style={{ flex: 1 }}>layer</span>
                      <span style={{ width: 58, textAlign: "right" }}><Term k="dBFS">dBFS</Term></span>
                      <span style={{ width: 52, textAlign: "right" }}><Term k="spectral centroid">Hz</Term></span>
                      <span style={{ width: 34, textAlign: "right" }}>vox</span>
                    </div>
                    {layers.map((l) => (
                      <div
                        key={l.layer}
                        onClick={() => setLayerSel(l.layer)}
                        style={{
                          display: "flex", gap: 10, padding: "3px 0", cursor: "pointer",
                          color: layerSel === l.layer ? GOLD : "rgba(255,255,255,0.64)",
                        }}
                      >
                        <span style={{ width: 20 }}>L{l.layer}</span>
                        <span style={{ flex: 1 }}>{l.label}</span>
                        <span style={{ width: 58, textAlign: "right" }}>{l.measured.rms_dbfs.toFixed(1)}</span>
                        <span style={{ width: 52, textAlign: "right" }}>{Math.round(l.measured.spectral_centroid_hz)}</span>
                        <span style={{ width: 34, textAlign: "right" }}>{l.voices || "—"}</span>
                      </div>
                    ))}
                  </div>

                  {layerTargets && (
                    <p className="lab-only" style={{ fontSize: 9.5, lineHeight: 1.7, color: "rgba(255,255,255,0.52)", marginTop: 8 }}>
                      targets: {layerTargets.loudness_target_db} dBFS · {layerTargets.brightness_target_hz} Hz ·
                      anchor MIDI {layerTargets.pitch_anchor_midi}. Watch which column moves —
                      L2 changes only the dBFS column, L3 adds the Hz column.
                      L1 is deliberately before both rules: fixed −20 dBFS with every harmonic left in,
                      so it sounds nothing like the target.
                    </p>
                  )}

                  {layerTargets && (
                    <p className="visitor-only" style={{ fontSize: 10.5, lineHeight: 1.7, color: "rgba(255,255,255,0.6)", marginTop: 8 }}>
                      Each version was measured against the same target. Switch to LAB to see the numbers.
                    </p>
                  )}

                  <details style={{ marginTop: 10 }}>
                    <summary style={{ fontSize: 9.5, color: "rgba(255,255,255,0.56)", cursor: "pointer", letterSpacing: "0.04em" }}>
                      full 15 s render · .mid
                    </summary>
                    <div style={{ marginTop: 8 }}>
                      {!prevData ? (
                        <button
                          onClick={handlePreview}
                          disabled={prevBusy}
                          style={{ ...chipBtn, borderColor: `${GOLD}66`, color: GOLD }}
                        >
                          {prevBusy ? "rendering…" : "render 15 s"}
                        </button>
                      ) : (
                        <>
                          <MiniPlayer src={prevData.wav_url} />
                          <div style={{ display: "flex", gap: 12, marginTop: 8, alignItems: "center", fontFamily: "monospace", fontSize: 10, color: "rgba(255,255,255,0.56)" }}>
                            <span>{prevData.measured.rms_dbfs} dBFS · {prevData.measured.spectral_centroid_hz} Hz</span>
                            {prevData.mid_url && (
                              <a
                                href={prevData.mid_url}
                                download
                                style={{ color: `${GOLD}cc`, letterSpacing: "0.1em", textDecoration: "none", borderBottom: `1px solid ${GOLD}44` }}
                              >
                                .mid
                              </a>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  </details>
                </>
              )}

              {prevErr && (
                <div style={{ marginTop: 8, fontSize: 10, color: "#d98c8c" }}>{prevErr}</div>
              )}
            </div>

            <div style={{ height: 1, background: `linear-gradient(to right, ${GOLD}40, transparent)`, marginBottom: 22 }} />

            <div data-station="2" style={{ marginBottom: 24 }}>
              <SectionLabel>03 · Check</SectionLabel>

              {/* 盲听对照: 同一条规则目标，两层声音 */}
              {data.mapping && data.audio && (
                <div style={{ marginBottom: 20 }}>
                  <div style={{ fontSize: 9.5, letterSpacing: "0.16em", textTransform: "uppercase", color: "rgba(255,255,255,0.5)", marginBottom: 9 }}>
                    Blind test · the translation vs the model's reading
                  </div>
                  <p style={{ fontSize: 11.5, lineHeight: 1.8, color: "rgba(255,255,255,0.72)", marginBottom: 10 }}>
                    One of these is the rule layer — the translation itself. The other is Suno's reading
                    of a text description of the same painting. Listen first; the measurements appear
                    when you reveal.
                  </p>

                  {!baseClip ? (
                    <button
                      onClick={loadLayers}
                      disabled={prevBusy}
                      style={{ ...chipBtn, borderColor: `${GOLD}66`, color: GOLD }}
                    >
                      {prevBusy ? "rendering…" : "prepare the rule-layer clip"}
                    </button>
                  ) : (
                    <>
                      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                        {(["A", "B"] as const).map((k) => (
                          <button
                            key={k}
                            onClick={() => setAbPick(k)}
                            style={{
                              ...chipBtn,
                              minWidth: 54,
                              fontSize: 12,
                              letterSpacing: "0.2em",
                              borderColor: abPick === k ? GOLD : "rgba(255,255,255,0.18)",
                              color: abPick === k ? GOLD : "rgba(255,255,255,0.7)",
                              background: abPick === k ? `${GOLD}14` : "rgba(255,255,255,0.04)",
                            }}
                          >
                            {k}
                          </button>
                        ))}
                        {abPick && !abReveal && (
                          <button
                            onClick={() => setAbReveal(true)}
                            style={{ ...chipBtn, borderColor: `${GOLD}66`, color: GOLD }}
                          >
                            reveal
                          </button>
                        )}
                      </div>

                      {abPick && <MiniPlayer key={`ab-${abPick}`} src={abSrc(abPick)} />}

                      {abReveal && (
                        <>
                          <div style={{ display: "flex", flexDirection: "column", gap: 5, fontFamily: "monospace", fontSize: 10.5, marginTop: 12 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", color: "rgba(255,255,255,0.5)", borderBottom: "1px solid rgba(255,255,255,0.12)", paddingBottom: 5 }}>
                              <span>target (rule layer)</span>
                              <span>{data.mapping.params.loudness_target_db} dBFS · {data.mapping.params.brightness_target_hz} Hz</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", color: "rgba(255,255,255,0.75)" }}>
                              <span>{abSwap ? "A" : "B"} · the rule layer · the translation</span>
                              <span>
                                {baseMeasured ? `${baseMeasured.rms_dbfs} dBFS · ${baseMeasured.spectral_centroid_hz} Hz` : "—"}{" "}
                                {baseMeasured && (
                                  <span style={{ color: "#8fc98f" }}>✓</span>
                                )}
                              </span>
                            </div>
                            {(data.suno_measured || []).slice(0, 1).map((mm) => (
                              <div key={mm.file} style={{ display: "flex", justifyContent: "space-between", color: "rgba(255,255,255,0.75)" }}>
                                <span>{abSwap ? "B" : "A"} · suno · the model's reading</span>
                                <span>{mm.rms_dbfs} dBFS · {mm.spectral_centroid_hz} Hz</span>
                              </div>
                            ))}
                          </div>
                          <p style={{ fontSize: 9.5, color: "rgba(255,255,255,0.52)", lineHeight: 1.7, marginTop: 8 }}>
                            The rule layer lands on its targets because it is built from them. Suno receives
                            this text, motif included — and still does not carry the difference. Measured on
                            two paintings, two renders each: within one painting the spectral centroid moved{" "}
                            <span style={{ color: "rgba(255,255,255,0.72)" }}>1598 Hz</span> between renders;
                            between the two paintings it moved{" "}
                            <span style={{ color: "rgba(255,255,255,0.72)" }}>1000 Hz</span>. The wobble is
                            larger than the difference, so this is a reading of the painting, not a
                            translation of it.
                          </p>
                        </>
                      )}
                    </>
                  )}
                </div>
              )}

              {scan ? (
                <LocateTest imageUrl={imageUrl} wavUrl={scan.wav_url} seconds={scan.seconds} />
              ) : (
                <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                  <div style={{
                    fontSize: 9, letterSpacing: "0.18em", textTransform: "uppercase",
                    color: "rgba(255,255,255,0.5)", marginBottom: 7,
                  }}>
                    Self-test · can you locate what you hear
                  </div>
                  <p style={{ fontSize: 11, lineHeight: 1.8, color: "rgba(255,255,255,0.62)", marginBottom: 9 }}>
                    The test needs the scan layer. It runs locally and costs nothing.
                  </p>
                  <button onClick={loadScan} disabled={scanBusy} style={{ ...chipBtn, borderColor: `${GOLD}77`, color: GOLD }}>
                    {scanBusy ? "rendering…" : "▶ prepare the scan layer"}
                  </button>
                </div>
              )}

              <div style={{ display: "flex", gap: 8, marginTop: 18, marginBottom: 18 }}>
                <button onClick={exportCard} style={chipBtn} title="download a shareable card">
                  ⤓ export card · png
                </button>
              </div>

              {!data.audio && (
                <div style={{
                  marginBottom: 20, padding: "14px 16px", borderRadius: 4,
                  border: `1px dashed ${GOLD}55`, background: "rgba(201,168,76,0.04)",
                }}>
                  <div style={{
                    fontSize: 9, letterSpacing: "0.18em", textTransform: "uppercase",
                    color: "rgba(255,255,255,0.52)", marginBottom: 7,
                  }}>
                    No generated track yet
                  </div>
                  <p style={{ fontSize: 11.5, lineHeight: 1.8, color: "rgba(255,255,255,0.72)", margin: 0 }}>
                    Everything above works without credits — the rules and the three layers.
                    A full Suno track is the last layer: press <span style={{ color: GOLD }}>Generate music</span> at
                    the bottom of this station (1 credit · 1–3 min), then the blind test appears here.
                  </p>
                </div>
              )}

              {data.era_style?.label && (
                <p style={{
                  fontFamily: "Playfair Display, Georgia, serif",
                  fontSize: 14, color: GOLD, marginBottom: 12,
                }}>
                  {data.era_style.label}
                </p>
              )}
              {data.musical_hint && (
                <p style={{ fontSize: 12, lineHeight: 1.75, color: "rgba(255,255,255,0.7)", marginBottom: 14 }}>
                  {data.musical_hint}
                </p>
              )}
              {data.music_prompt ? (
                <div style={{ borderLeft: `1.5px solid ${GOLD}45`, paddingLeft: 16 }}>
                  <div style={{
                    fontSize: 9, letterSpacing: "0.28em", textTransform: "uppercase",
                    color: "rgba(255,255,255,0.52)", marginBottom: 8,
                  }}>
                    Music Generation Prompt
                  </div>
                  <div style={{ position: "relative" }}>
                    <p style={{
                      fontSize: 12, lineHeight: 1.75, color: "rgba(255,255,255,0.62)",
                      fontFamily: "monospace", whiteSpace: "pre-wrap",
                      maxHeight: promptOpen ? undefined : 132,
                      overflow: "hidden",
                    }}>
                      {data.music_prompt}
                    </p>
                    {!promptOpen && data.music_prompt.length > 220 && (
                      <div style={{
                        position: "absolute", left: 0, right: 0, bottom: 0, height: 48,
                        background: "linear-gradient(to bottom, rgba(8,10,18,0), rgba(8,10,18,0.92))",
                        pointerEvents: "none",
                      }} />
                    )}
                  </div>
                  {data.music_prompt.length > 220 && (
                    <button
                      onClick={() => setPromptOpen((v) => !v)}
                      style={{
                        marginTop: 6, background: "none", border: "none", padding: 0,
                        cursor: "pointer", fontSize: 9.5, letterSpacing: "0.1em",
                        color: `${GOLD}cc`, textTransform: "uppercase",
                      }}
                    >
                      {promptOpen ? "collapse" : `read full prompt · ${data.music_prompt.length} chars`}
                    </button>
                  )}
                  {data.music_prompt_source === "gemini-cached" && (
                    <p style={{ fontSize: 9.5, lineHeight: 1.6, color: "rgba(255,255,255,0.5)", marginTop: 8 }}>
                      Gemini 转译，输入为旧版规则；音区/力度以 Mapping 面板为准（新上传的图会按新规则重算）
                    </p>
                  )}
                  {data.music_prompt_source === "rule-template" && (
                    <p style={{ fontSize: 9.5, lineHeight: 1.6, color: "rgba(255,255,255,0.5)", marginTop: 8 }}>
                      规则模板生成（未调用 Gemini）；填 GEMINI_API_KEY 后会自动改为 AI 转译
                    </p>
                  )}
                </div>
              ) : (
                <p style={{
                  fontSize: 11, color: "rgba(255,255,255,0.50)",
                  fontStyle: "italic", letterSpacing: "0.04em",
                }}>
                  Music prompt pending generation
                </p>
              )}

              {/* ── 生成按钮 (消耗额度, 需确认) ────────────── */}
              {data.music_prompt && (
                <div style={{ marginTop: 18 }}>
                  {genState === "running" ? (
                    <div style={{
                      display: "flex", alignItems: "center", gap: 10,
                      padding: "10px 14px",
                      border: `1px solid ${GOLD}40`,
                      borderRadius: 4,
                      backgroundColor: "rgba(201,168,76,0.05)",
                    }}>
                      <div style={{
                        width: 12, height: 12, borderRadius: "50%",
                        border: `1.5px solid ${GOLD}40`,
                        borderTopColor: GOLD,
                        animation: "spin 0.75s linear infinite",
                        flexShrink: 0,
                      }} />
                      <span style={{ fontSize: 11, color: "rgba(255,255,255,0.62)", letterSpacing: "0.06em" }}>
                        {genLog || "Generating…"}
                      </span>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmOpen((v) => !v)}
                      aria-expanded={confirmOpen}
                      style={{
                        padding: "10px 18px",
                        backgroundColor: "transparent",
                        border: `1px solid ${GOLD}66`,
                        borderRadius: 4,
                        color: GOLD, fontFamily: "Lora, serif",
                        fontSize: 11, letterSpacing: "0.18em",
                        textTransform: "uppercase",
                        cursor: "pointer",
                        transition: "background-color 0.2s, border-color 0.2s",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = "rgba(201,168,76,0.1)";
                        e.currentTarget.style.borderColor = `${GOLD}aa`;
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = "transparent";
                        e.currentTarget.style.borderColor = `${GOLD}66`;
                      }}
                    >
                      {genState === "done" ? "Regenerate Music" : "Generate Music"}
                    </button>
                  )}

                  {data.music_prompt_source === "rule-template" && (
                    <div style={{ marginTop: 8, fontSize: 9.5, color: "rgba(255,255,255,0.55)", lineHeight: 1.6 }}>
                      ⚠ 这份 prompt 由规则模板生成（未调用 Gemini）—— 生成会花额度但结果更粗糙。
                    </div>
                  )}

                  {confirmOpen && genState !== "running" && (
                    <div style={{
                      marginTop: 12, padding: "12px 14px",
                      border: `1px solid ${GOLD}55`, borderRadius: 4,
                      backgroundColor: "rgba(201,168,76,0.06)",
                    }}>
                      <div style={{ fontSize: 11.5, color: "rgba(255,255,255,0.82)", lineHeight: 1.6, marginBottom: 4 }}>
                        Generate music for “{data.title}”?
                      </div>
                      <div style={{ fontSize: 10, color: "rgba(255,255,255,0.55)", lineHeight: 1.6, marginBottom: 11 }}>
                        Calls Suno · 1 credit · today {usage?.used ?? 0}/{usage?.limit ?? 0}
                        {(usage && usage.limit - usage.used <= 3) ? " (running low)" : ""} · 1–3 min · 2 tracks
                      </div>
                      <div style={{ display: "flex", gap: 10 }}>
                        <button
                          onClick={handleGenerate}
                          style={{
                            padding: "7px 16px", backgroundColor: `${GOLD}22`,
                            border: `1px solid ${GOLD}88`, borderRadius: 3,
                            color: GOLD, fontFamily: "Lora, serif", fontSize: 10.5,
                            letterSpacing: "0.14em", textTransform: "uppercase", cursor: "pointer",
                          }}
                        >
                          Generate
                        </button>
                        <button
                          onClick={() => setConfirmOpen(false)}
                          style={{
                            padding: "7px 14px", backgroundColor: "transparent",
                            border: "1px solid rgba(255,255,255,0.2)", borderRadius: 3,
                            color: "rgba(255,255,255,0.6)", fontFamily: "Lora, serif",
                            fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase", cursor: "pointer",
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  {/* 状态与用量提示 */}
                  <div style={{ marginTop: 10, display: "flex", gap: 14, flexWrap: "wrap" }}>
                    {genState === "error" && (
                      <span style={{ fontSize: 10, color: "#d98c8c", letterSpacing: "0.04em" }}>
                        Failed: {genError}
                      </span>
                    )}
                    {genState === "done" && !genError && (
                      <span style={{ fontSize: 10, color: `${GOLD}cc`, letterSpacing: "0.04em" }}>
                        {audioList.length > 1
                          ? `${audioList.length} tracks ready — `
                          : "Audio ready — "}
                        use the player on the left
                      </span>
                    )}
                    {/* 多首切换 */}
                    {audioList.length > 1 && (
                      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        {audioList.map((u, i) => (
                          <button
                            key={u}
                            onClick={() => {
                              setAudioIdx(i);
                              setData((prev) => prev ? { ...prev, audio: u } : prev);
                              setProgress(0);
                              setMusicState("idle");
                            }}
                            style={{
                              padding: "3px 10px", fontSize: 10,
                              fontFamily: "monospace",
                              backgroundColor: i === audioIdx ? `${GOLD}26` : "transparent",
                              border: `1px solid ${i === audioIdx ? GOLD : "rgba(255,255,255,0.2)"}`,
                              borderRadius: 3, cursor: "pointer",
                              color: i === audioIdx ? GOLD : "rgba(255,255,255,0.55)",
                              transition: "all 0.2s",
                            }}
                          >
                            {i + 1}
                          </button>
                        ))}
                      </span>
                    )}
                    {usage && genState === "idle" && (
                      <span style={{ fontSize: 10, color: "rgba(255,255,255,0.5)", letterSpacing: "0.04em" }}>
                        {usage.enabled
                          ? `Uses 1 credit · today ${usage.used}/${usage.limit}`
                          : "Music API disabled"}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div style={{ height: 20 }} />
          </div>
        </div>

        {/* ── Work navigation：在九幅里前后走，不必退回房间 ───── */}
        {(() => {
          const wi = rulerItems.findIndex((r) => r.id === data.id);
          if (wi < 0 || rulerItems.length < 2) return null;
          const prevW = rulerItems[(wi - 1 + rulerItems.length) % rulerItems.length];
          const nextW = rulerItems[(wi + 1) % rulerItems.length];
          const arrow: React.CSSProperties = {
            background: "none", border: "none", cursor: "pointer", padding: "0 2px",
            color: "rgba(255,255,255,0.78)", fontSize: 14, lineHeight: 1,
          };
          return (
            <div className="present-hide" style={{
              position: "fixed", top: 22, left: 66, zIndex: 100,
              height: 34, padding: "0 12px", borderRadius: 17,
              backgroundColor: "rgba(8,8,12,0.55)",
              border: "1px solid rgba(255,255,255,0.16)",
              backdropFilter: "blur(6px)",
              display: "flex", alignItems: "center", gap: 9,
            }}>
              <button onClick={() => loadArtwork(prevW.id, true, true)} title={`${prevW.title} · K`} aria-label="previous painting" style={arrow}>‹</button>
              <span style={{
                fontFamily: "monospace", fontSize: 10, letterSpacing: "0.06em",
                color: "rgba(255,255,255,0.82)",
              }}>
                {wi + 1} / {rulerItems.length}
              </span>
              <button onClick={() => loadArtwork(nextW.id, true, true)} title={`${nextW.title} · J`} aria-label="next painting" style={arrow}>›</button>
            </div>
          );
        })()}

        {/* ── Back button ─────────────────────────────────────── */}
        <button
          onClick={handleBack}
          style={{
            position: "fixed", top: 22, left: 22, zIndex: 100,
            width: 34, height: 34, borderRadius: "50%",
            backgroundColor: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.13)",
            color: "rgba(255,255,255,0.56)",
            fontSize: 15, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            transition: "background 0.2s, color 0.2s, border-color 0.2s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.11)";
            e.currentTarget.style.color = "rgba(255,255,255,0.75)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.25)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)";
            e.currentTarget.style.color = "rgba(255,255,255,0.45)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.13)";
          }}
        >
          ←
        </button>

        {/* ── Intro overlay ────────────────────────────────────── */}
        <div
          onClick={triggerReveal}
          style={{
            position: "fixed", inset: 0, zIndex: 40,
            pointerEvents: revealRaw >= 1 ? "none" : "all",
            opacity: introOpacity,
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center",
            cursor: revealRaw < 1 ? "pointer" : "default",
          }}
        >
          <div style={{
            textAlign: "center",
            transform: `translateX(${introShift}vw) scale(${introScale})`,
            transition: "transform 0.06s ease-out",
            padding: "0 40px",
          }}>
            <div style={{ width: 36, height: 1, backgroundColor: `${GOLD}70`, margin: "0 auto 32px" }} />
            <h1 style={{
              fontFamily: "Playfair Display, Georgia, serif",
              fontSize: "clamp(52px, 7.5vw, 100px)",
              fontWeight: 400, lineHeight: 1.04, letterSpacing: "-0.02em",
              color: "#f4ede0", marginBottom: 22,
            }}>
              {data.title}
            </h1>
            <p style={{
              fontFamily: "Playfair Display, Georgia, serif",
              fontSize: "clamp(15px, 1.8vw, 21px)",
              fontStyle: "italic", color: GOLD,
              letterSpacing: "0.06em", marginBottom: 36,
            }}>
              {data.artist}
            </p>
            <p style={{ fontSize: 10, color: "rgba(255,255,255,0.5)", letterSpacing: "0.25em", textTransform: "uppercase" }}>
              {introMeta}
            </p>
          </div>

          <div style={{
            position: "absolute", bottom: 40,
            display: "flex", flexDirection: "column", alignItems: "center", gap: 12,
            opacity: Math.max(0, 1 - revealRaw * 6),
          }}>
            <span style={{ fontSize: 10, letterSpacing: "0.28em", textTransform: "uppercase" as const, color: "rgba(255,255,255,0.56)" }}>
              Scroll or click to discover
            </span>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
              <div style={{ width: 1, height: 28, background: "linear-gradient(to bottom, transparent, rgba(255,255,255,0.28))" }} />
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.50)", animation: "scrollDrop 1.6s ease-in-out infinite" }}>↓</div>
            </div>
          </div>
        </div>

        {/* ── Zoom lightbox ─────────────────────────────────────── */}
        {zoomed && (
          <div
            onClick={() => setZoomed(false)}
            style={{
              position: "fixed", inset: 0, zIndex: 200,
              backdropFilter: "blur(18px) brightness(0.4)",
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "zoom-out",
              animation: "bgFadeIn 0.25s ease",
            }}
          >
            <img
              src={imageUrl} alt={data.title}
              style={{
                maxWidth: "88vw", maxHeight: "88vh",
                objectFit: "contain",
                boxShadow: "0 40px 120px rgba(0,0,0,0.8)",
                animation: "zoomIn 0.35s cubic-bezier(0.16,1,0.3,1)",
                pointerEvents: "none",
              }}
            />
            <button
              onClick={(e) => { e.stopPropagation(); setZoomed(false); }}
              style={{
                position: "fixed", top: 24, right: 28,
                width: 40, height: 40, borderRadius: "50%",
                backgroundColor: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.18)",
                color: "rgba(255,255,255,0.65)", fontSize: 20,
                cursor: "pointer", display: "flex",
                alignItems: "center", justifyContent: "center",
                transition: "background 0.2s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.14)")}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.06)")}
            >×</button>
          </div>
        )}
      </div>}
    </>
  );
}
