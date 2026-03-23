import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Gini",
  description: "AI Assistant System",
  viewport: { width: "device-width", initialScale: 1, maximumScale: 1 },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="bg-zinc-950 text-zinc-100 min-h-screen antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
