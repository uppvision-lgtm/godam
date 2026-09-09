import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";

const poppins = Poppins({
  weight: ["400", "600", "700", "800"],
  subsets: ["latin"],
  variable: "--font-poppins",
});

export const metadata: Metadata = {
  title: "IG Tools — Alat Bantu Instagram",
  description: "Kumpulan alat bantu Instagram: auto comment, auto like, dan lainnya.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="id" className={`${poppins.variable}`}>
      <body>{children}</body>
    </html>
  );
}
