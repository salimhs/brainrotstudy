import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BrainRotStudy",
  description:
    "Turn PDFs, slides, or a topic into a 60-second vertical study video.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
