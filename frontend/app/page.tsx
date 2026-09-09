import Link from "next/link";
import styles from "./page.module.css";

type Tool = {
  id: string;
  icon: string;
  title: string;
  desc: string;
  href?: string;
  status: "ready" | "soon";
  badge?: string;
};

const tools: Tool[] = [
  {
    id: "server",
    icon: "💬",
    title: "Auto Komen & Like Instagram",
    desc: "via server",
    href: "/auto-comment",
    status: "ready",
    badge: "Tersedia",
  },
  {
    id: "pc",
    icon: "🖥️",
    title: "Auto Komen & Like Instagram",
    desc: "via PC",
    href: "/auto-comment?mode=pc",
    status: "ready",
    badge: "Tersedia",
  },
];

export default function Home() {
  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <span className={styles.brand}>IG · TOOLS</span>
        <span className={styles.headStatus}>Semua alat di satu tempat</span>
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <h1>Pilih Tools Kamu</h1>
        </section>

        <section className={styles.grid}>
          {tools.map((tool) =>
            tool.status === "ready" && tool.href ? (
              <Link key={tool.id} href={tool.href} className={styles.card}>
                <span className={styles.cardTop}>
                  <span className={styles.icon}>{tool.icon}</span>
                  <span className={styles.badge}>{tool.badge}</span>
                </span>
                <h2>{tool.title}</h2>
                <p>{tool.desc}</p>
                <span className={styles.cta}>
                  Buka
                  <span className={styles.arrow}>→</span>
                </span>
              </Link>
            ) : (
              <div key={tool.id} className={`${styles.card} ${styles.soonCard}`} aria-disabled="true">
                <span className={styles.cardTop}>
                  <span className={`${styles.icon} ${styles.soonIcon}`}>{tool.icon}</span>
                  <span className={`${styles.badge} ${styles.soonBadge}`}>Coming Soon</span>
                </span>
                <h2>{tool.title}</h2>
                <p>{tool.desc}</p>
                <span className={`${styles.cta} ${styles.soonCta}`}>Segera hadir</span>
              </div>
            )
          )}
        </section>

        <footer className={styles.footer}>
          <span>Pakai dengan bijak.</span>
        </footer>
      </main>
    </div>
  );
}
