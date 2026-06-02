import type { SiteConfig } from '@/types';

export const siteConfig: SiteConfig = {
  author: 'Chetan Katke',
  date: {
    locale: 'en-US',
    options: {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    },
  },
  description:
    'Indian Supreme Court and High Court judgment analyses, case summaries, and legal research on constitutional law, criminal law, human rights, and landmark Indian legal precedents.',
  lang: 'en-US',
  ogLocale: 'en_US',
  sortPostsByUpdatedDate: false,
  title: 'Legal Research Blog',
  hideThemeCredit: false,
  profile: {
    name: 'Chetan Katke',
    email: 'chetankatke@users.noreply.github.com',
    github: 'https://github.com/chetankatke',
    jobTitle: 'Legal Researcher',
  },
};

export const menuLinks: { path: string; title: string }[] = [
  { path: '/', title: 'Home' },
  { path: '/posts/', title: 'Posts' },
  { path: '/about/', title: 'About' },
];

export const locales = [
  { code: 'en', label: 'English', native: 'English' },
  { code: 'mr', label: 'Marathi', native: 'मराठी' },
  { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
  { code: 'ta', label: 'Tamil', native: 'தமிழ்' },
  { code: 'bn', label: 'Bengali', native: 'বাংলা' },
  { code: 'te', label: 'Telugu', native: 'తెలుగు' },
  { code: 'kn', label: 'Kannada', native: 'ಕನ್ನಡ' },
  { code: 'ml', label: 'Malayalam', native: 'മലയാളം' },
  { code: 'gu', label: 'Gujarati', native: 'ગુજરાતી' },
  { code: 'pa', label: 'Punjabi', native: 'ਪੰਜਾਬੀ' },
];
