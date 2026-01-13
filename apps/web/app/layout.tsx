import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

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
      <body className={`${inter.variable} min-h-screen bg-background text-foreground antialiased font-sans`}>
        {children}
      </body>
    </html>
  );
}
