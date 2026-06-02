import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import expressiveCode from 'astro-expressive-code';
import icon from 'astro-icon';
import robotsTxt from 'astro-robots-txt';
import webmanifest from 'astro-webmanifest';
import partytown from '@astrojs/partytown';
import compress from '@playform/compress';

import remarkDirective from 'remark-directive';
import remarkMath from 'remark-math';
import rehypeExternalLinks from 'rehype-external-links';
import rehypeKatex from 'rehype-katex';
import rehypeUnwrapImages from 'rehype-unwrap-images';

// Base path for GitHub Pages project site
const BASE_PATH = process.env.BASE_PATH || '/legal-research-blog/';
const START_URL = BASE_PATH.endsWith('/') ? BASE_PATH : `${BASE_PATH}/`;

export default defineConfig({
  site: 'https://chetankatke.github.io',
  base: BASE_PATH,
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'mr', 'hi', 'ta', 'bn', 'te', 'kn', 'ml', 'gu', 'pa'],
    routing: { prefixDefaultLocale: true },
    fallback: {
      mr: 'en', hi: 'en', ta: 'en', bn: 'en', te: 'en', kn: 'en', ml: 'en', gu: 'en', pa: 'en'
    }
  },
  image: {
    domains: ['webmention.io'],
  },
  output: 'static',
  build: {
    format: 'directory',
    inlineStylesheets: 'always',
  },
  integrations: [
    partytown({
      config: {
        forward: ['dataLayer.push'],
      },
    }),
    expressiveCode({
      styleOverrides: {
        borderRadius: '4px',
        codeBackground: ({ theme }) => theme.type === 'light' ? '#f0e9d6' : '#1a1715',
        codeFontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;',
        codeFontSize: '0.875rem',
        codeLineHeight: '1.7142857rem',
        codePaddingInline: '1rem',
        frames: {
          editorActiveTabBackground: ({ theme }) => theme.type === 'light' ? '#f0e9d6' : '#1a1715',
          editorTabBarBackground: ({ theme }) => theme.type === 'light' ? '#ebe3cd' : '#15120e',
          frameBoxShadowCssValue: 'none',
          terminalBackground: ({ theme }) => theme.type === 'light' ? '#f0e9d6' : '#1a1715',
          terminalTitlebarBackground: ({ theme }) => theme.type === 'light' ? '#ebe3cd' : '#15120e',
        },
        uiLineHeight: 'inherit',
      },
      themeCssSelector(theme, { styleVariants }) {
        if (styleVariants.length >= 2) {
          const baseTheme = styleVariants[0]?.theme;
          const altTheme = styleVariants.find((v) => v.theme.type !== baseTheme?.type)?.theme;
          if (theme === baseTheme || theme === altTheme) return `[data-theme='${theme.type}']`;
        }
        return `[data-theme="${theme.name}"]`;
      },
      themes: ['min-dark', 'min-light'],
      useThemedScrollbars: false,
    }),
    icon(),
    sitemap({
      changefreq: 'weekly',
      priority: 0.7,
      lastmod: new Date(),
    }),
    mdx(),
    robotsTxt(),
    webmanifest({
      name: 'Legal Research Blog',
      description: 'Indian Supreme Court and High Court judgment analyses, case summaries, and legal research',
      lang: 'en',
      icon: 'public/icon.png',
      icons: [
        { src: 'icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
        { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
        { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
      ],
      start_url: START_URL,
      background_color: '#1d1f21',
      theme_color: '#2bbc8a',
      display: 'standalone',
      config: {
        insertFaviconLinks: false,
        insertThemeColorMeta: false,
        insertManifestLink: false,
      },
    }),
    compress(),
  ],
  markdown: {
    rehypePlugins: [
      rehypeUnwrapImages,
      rehypeKatex,
      [
        rehypeExternalLinks,
        { rel: ['nofollow, noreferrer'], target: '_blank' },
      ],
    ],
    remarkPlugins: [remarkDirective, remarkMath],
    remarkRehype: {
      footnoteLabelProperties: { className: [''] },
    },
  },
  prefetch: true,
});
