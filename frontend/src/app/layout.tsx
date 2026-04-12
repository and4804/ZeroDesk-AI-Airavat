import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "AgentFinance AI — Sovereign Intelligence",
  description: "AI-powered zero-human-agent retail loan onboarding platform. Live AI evaluation and autonomous decision system.",
  keywords: ["AI", "loan", "onboarding", "fintech", "autonomous", "sovereign intelligence"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} ${spaceGrotesk.variable} antialiased min-h-screen`} style={{ background: 'var(--bg-base, #0B0B0C)' }}>
        {children}
      </body>
    </html>
  );
}
