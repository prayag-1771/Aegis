import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Aegis — Public Safety Command Centre",
  description:
    "Unified digital public safety intelligence: scam detection, counterfeit currency, fraud rings — fused on one crime map.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased text-zinc-200">{children}</body>
    </html>
  );
}
