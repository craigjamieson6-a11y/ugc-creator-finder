import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UGC Creator Finder",
  description: "Find and rank the best UGC creators aged 40-60",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <nav className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <a href="/" className="text-xl font-bold text-indigo-600">
              UGC Creator Finder
            </a>
            <div className="flex gap-6">
              <a href="/" className="text-gray-600 hover:text-gray-900">
                Search
              </a>
              <a
                href="/campaigns"
                className="text-gray-600 hover:text-gray-900"
              >
                Campaigns
              </a>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
