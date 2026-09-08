import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Qualto — No fill, no claim",
  description:
    "Qualto binds every AI trading claim to a live Binance order. If the exchange can't prove the claim, the agent can't trade. No fill, no claim.",
  openGraph: {
    title: "Qualto — No fill, no claim",
    description:
      "Claim-bound orders on Binance Agent OS. Every trade claim is proved against the exchange itself, or the session locks.",
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
