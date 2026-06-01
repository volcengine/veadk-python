import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { appName, assetPath, gitConfig } from './shared';

export function baseOptions(locale: string): BaseLayoutProps {
  return {
    nav: {
      title: (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={assetPath('/assets/images/volcengine-color.svg')}
            alt="Volcengine"
            width={20}
            height={20}
          />
          {appName}
        </>
      ),
      url: `/${locale}`,
    },
    githubUrl: `https://github.com/${gitConfig.user}/${gitConfig.repo}`,
  };
}
