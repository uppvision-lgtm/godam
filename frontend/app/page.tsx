"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import styles from "./page.module.css";

type LiveStatus = {
  token: string;
  status: string;
  message: string;
  logs: string[];
  result?: {
    comments_posted?: number;
    posts_processed?: number;
  };
};

type FormValues = {
  username: string;
  session_id: string;
  target: string;
  comment_count: number;
  max_posts: number;
};

const initialValues: FormValues = {
  username: "",
  session_id: "",
  target: "",
  comment_count: 1,
  max_posts: 3,
};

export default function Home() {
  const [values, setValues] = useState(initialValues);
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");
  const [logs, setLogs] = useState<string[]>([]);
  const [result, setResult] = useState<LiveStatus["result"] | null>(null);
  const [frameUrl, setFrameUrl] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const frameRef = useRef<HTMLImageElement | null>(null);

  const isTerminal = status === "completed" || status === "error";

  useEffect(() => {
    if (!token) return;
    let stopped = false;

    async function pollStatus() {
      try {
        const res = await fetch(`/api/live/${token}/status`, { cache: "no-store" });
        const data: LiveStatus = await res.json();
        if (stopped) return;
        setStatus(data.status);
        setMessage(data.message || "");
        if (Array.isArray(data.logs)) setLogs(data.logs);
        if (data.result) setResult(data.result);
      } catch {
        // sementara
      }
    }

    pollStatus();
    const statusTimer = window.setInterval(pollStatus, 1000);

    const refreshFrame = () => {
      setFrameUrl(`/api/live/${token}/frame?t=${Date.now()}`);
    };
    refreshFrame();
    const frameTimer = window.setInterval(refreshFrame, 600);

    return () => {
      stopped = true;
      window.clearInterval(statusTimer);
      window.clearInterval(frameTimer);
    };
  }, [token]);

  function updateField(field: keyof FormValues, value: string | number) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function startJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!values.username.trim() || !values.session_id.trim() || !values.target.trim()) {
      setError("Nama akun, Session ID, dan Channel wajib diisi.");
      return;
    }
    if (!Number.isInteger(values.comment_count) || values.comment_count < 1 || values.comment_count > 10) {
      setError("Jumlah komentar harus angka 1-10.");
      return;
    }
    if (!Number.isInteger(values.max_posts) || values.max_posts < 1 || values.max_posts > 50) {
      setError("Jumlah postingan harus angka 1-50.");
      return;
    }
    setStarting(true);
    setLogs([]);
    setResult(null);
    try {
      const res = await fetch("/api/live/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Gagal memulai.");
      setToken(data.token);
      setStatus("starting");
      setMessage("Menyiapkan browser...");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal memulai.");
    } finally {
      setStarting(false);
    }
  }

  async function stopLive() {
    if (!token) return;
    try {
      await fetch(`/api/live/${token}/close`, { method: "POST" });
    } catch {
      // abaikan
    }
    setToken("");
    setStatus("");
    setMessage("");
    setLogs([]);
    setResult(null);
    setFrameUrl("");
  }

  // Tutup Chromium di backend otomatis saat halaman ditutup/di-refresh,
  // supaya browser tidak menggantung & memori tidak menumpuk.
  useEffect(() => {
    if (!token) return;
    const closeOnUnload = () => {
      try {
        navigator.sendBeacon(`/api/live/${token}/close`, "");
      } catch {
        // abaikan
      }
    };
    window.addEventListener("beforeunload", closeOnUnload);
    return () => {
      window.removeEventListener("beforeunload", closeOnUnload);
    };
  }, [token]);

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <span className={styles.brand}>IG · AUTO COMMENT</span>
        <span className={styles.headStatus}>{status || "idle"}</span>
      </header>

      <main className={styles.main}>
        <section className={styles.panelRow}>
          {/* KIRI: form */}
          <form className={styles.form} onSubmit={startJob}>
            <h1>Jalankan Bot</h1>
            <p className={styles.formSub}>Login otomatis cukup pakai Session ID — tanpa CAPTCHA.</p>
            <label>
              <span>Nama akun Instagram</span>
              <input
                value={values.username}
                onChange={(e) => updateField("username", e.target.value)}
                placeholder="mis. topmengudara"
                autoComplete="off"
              />
            </label>
            <label>
              <span>Session ID</span>
              <input
                value={values.session_id}
                onChange={(e) => updateField("session_id", e.target.value)}
                placeholder="tempel sessionid cookie"
                autoComplete="off"
              />
            </label>
            <label>
              <span>Channel target</span>
              <input
                value={values.target}
                onChange={(e) => updateField("target", e.target.value)}
                placeholder="mis. tv.mediagaul"
                autoComplete="off"
              />
            </label>
            <label>
              <span>Jumlah komentar / postingan</span>
              <input
                type="number"
                min={1}
                max={10}
                value={values.comment_count}
                onChange={(e) => updateField("comment_count", Number(e.target.value))}
              />
            </label>
            <label>
              <span>Postingan terbaru yang dikomentari</span>
              <input
                type="number"
                min={1}
                max={50}
                value={values.max_posts}
                onChange={(e) => updateField("max_posts", Number(e.target.value))}
              />
            </label>
            {error && <p className={styles.error} role="alert">{error}</p>}
            <button className={styles.startBtn} type="submit" disabled={starting || !!token}>
              {starting ? "Menyiapkan..." : token ? "Berjalan..." : "Mulai"}
            </button>
          </form>

          {/* KANAN: log */}
          <aside className={styles.logPanel}>
            <div className={styles.logHeader}>
              <h2>Log</h2>
              <span className={`${styles.statusBadge} ${status ? styles[status] || "" : ""}`}>
                {status || "idle"}
              </span>
            </div>
            <div className={styles.logBody}>
              {logs.length === 0 ? (
                <p className={styles.logEmpty}>Belum ada log.</p>
              ) : (
                logs.map((line, i) => (
                  <p key={i} className={styles.logLine}>{line}</p>
                ))
              )}
            </div>
            {result && (
              <div className={styles.result}>
                <strong>{result.comments_posted ?? 0}</strong>
                <span>komentar</span>
                <strong>{result.posts_processed ?? 0}</strong>
                <span>postingan</span>
              </div>
            )}
          </aside>
        </section>

        {/* BAWAH: chrome live sampai selesai */}
        {token && (
          <section className={styles.livePanel}>
            <div className={styles.liveHeader}>
              <h2>Chrome Live</h2>
              <p>{message}</p>
              {!isTerminal && (
                <button className={styles.stopBtn} onClick={stopLive} disabled={starting}>
                  Stop
                </button>
              )}
              {isTerminal && (
                <button className={styles.closeBtn} onClick={stopLive}>Tutup</button>
              )}
            </div>
            <div className={styles.liveStage}>
              {frameUrl ? (
                <img
                  ref={frameRef}
                  src={frameUrl}
                  alt="Chrome live"
                  className={styles.liveFrame}
                  draggable={false}
                />
              ) : (
                <p className={styles.liveHint}>Menunggu frame...</p>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
