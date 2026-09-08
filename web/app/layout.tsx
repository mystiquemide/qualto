import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Qualto — the verification-first AI trading agent",
  description:
    "Qualto is an AI trading agent built on Binance Agent OS. It reasons over live markets and executes real orders — and it can't claim a fill until Binance itself proves it. If Binance can't prove it, the agent can't claim it.",
  openGraph: {
    title: "Qualto — the verification-first AI trading agent",
    description:
      "An AI trading agent on Binance Agent OS that can't lie about fills. Every claim is proved against the exchange itself, or the session locks.",
    images: [
      "https://raw.githubusercontent.com/mystiquemide/qualto/main/assets/qualto-banner.png",
    ],
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
