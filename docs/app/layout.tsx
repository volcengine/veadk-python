import type { ReactNode } from 'react';
import './global.css';

// Root layout. The locale-aware provider lives in `app/[lang]/layout.tsx`.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">{children}</body>
    </html>
  );
}
