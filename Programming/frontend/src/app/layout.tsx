import type { Metadata } from "next";

import { AccountBar } from "@/features/auth/components/AccountBar";
import { AuthProvider } from "@/features/auth/AuthContext";

import "./globals.css";

export const metadata: Metadata = {
  title: "AIMS",
  description: "AIMS customer product catalog and checkout",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <AuthProvider>
          <AccountBar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
