import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://chetankatke.github.io/legal-research-blog/',
  base: '/legal-research-blog',
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'mr', 'hi', 'ta', 'bn', 'te', 'kn', 'ml', 'gu', 'pa'],
    routing: { prefixDefaultLocale: true },
    fallback: {
      mr: 'en', hi: 'en', ta: 'en', bn: 'en', te: 'en', kn: 'en', ml: 'en', gu: 'en', pa: 'en'
    }
  },
  build: {
    format: 'directory'
  }
});
