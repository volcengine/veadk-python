'use client';

import { useEffect } from 'react';

// Static-export friendly root redirect to the default locale.
// Uses a relative path so it works under a GitHub Pages base path.
export default function RootRedirect() {
  useEffect(() => {
    window.location.replace('cn/');
  }, []);

  return (
    <noscript>
      <meta httpEquiv="refresh" content="0; url=cn/" />
    </noscript>
  );
}
