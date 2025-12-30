import './globals.css';
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import React from 'react';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Navi Agent',
  description: 'AI Research Assistant',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
          <script src="https://cdn.tailwindcss.com"></script>
      </head>
      <body className={inter.className}>{children}</body>
    </html>
  );
}