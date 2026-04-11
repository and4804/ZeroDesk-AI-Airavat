import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "AgentFinance AI — Autonomous Loan Onboarding",
  description: "AI-powered zero-human-agent retail loan onboarding platform. Complete your loan application via a browser-based video call.",
  keywords: ["AI", "loan", "onboarding", "fintech", "autonomous"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased gradient-bg min-h-screen`}>
        {children}
      </body>
    </html>
  );
}
