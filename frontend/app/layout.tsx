import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MCAP Log Manager",
  description: "Upload and manage MCAP telemetry logs for Formula SAE",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
