import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Life Easy — Personal AI Assistant",
  description: "Your AI workspace for job discovery and career outreach."
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
