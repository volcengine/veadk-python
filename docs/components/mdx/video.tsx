import type { ComponentProps } from 'react';
import { cn } from '@/lib/cn';

/**
 * Replacement for the MkDocs `![type:video](url)` plugin syntax.
 * Renders a responsive, muted-by-default HTML5 video player.
 */
export function Video({ src, className, ...props }: ComponentProps<'video'>) {
  return (
    <video
      src={src}
      controls
      muted
      playsInline
      className={cn(
        'my-6 w-full rounded-xl border border-fd-border shadow-lg',
        className,
      )}
      {...props}
    >
      <track kind="captions" />
    </video>
  );
}
