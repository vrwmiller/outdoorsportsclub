import type { Metadata } from "next";
import "./globals.css";
import ConfigureAmplify from "@/components/ConfigureAmplify";

export const metadata: Metadata = {
  title: "Outdoor Sports Club",
  description: "Member portal for Outdoor Sports Club",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 min-h-screen text-gray-800 text-base">
        <ConfigureAmplify />
        {children}
      </body>
    </html>
  );
}
