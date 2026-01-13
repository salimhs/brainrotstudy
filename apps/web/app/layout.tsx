import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BrainRotStudy - Turn Slides into Study Videos",
  description: "Generate TikTok-style study videos from PDFs, slides, or topics in seconds",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
