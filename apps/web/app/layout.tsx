import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Dev Office",
  description: "Multi-agent developer workspace control room",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-base text-slate-200 antialiased">
        {children}
      </body>
    </html>
  );
}