import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "../styles/globals.css";
// import { ClerkProvider } from "@clerk/nextjs"; // TEMPORARILY DISABLED
import Navbar from "@/components/navigation/Navbar";
import { Providers } from "@/components/providers/Providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Minder Plugin Marketplace",
  description: "Discover, install, and manage plugins for the Minder platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // <ClerkProvider> // TEMPORARILY DISABLED
      <html lang="en" className="dark">
        <body className={inter.className}>
          <Providers>
            <Navbar />
            {children}
          </Providers>
        </body>
      </html>
    // </ClerkProvider> // TEMPORARILY DISABLED
  );
}