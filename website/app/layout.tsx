import type { Metadata, Viewport } from 'next';
import { siteUrl } from './site';
import './globals.css';

const title = 'Providence — Offline AI File Search for Windows';
const description = 'Find local documents by what you remember. Providence combines offline AI search, scanned-document OCR, automatic indexing, and clear previews in a free Windows desktop app.';
export const metadata: Metadata = {
  title, description,
  ...(siteUrl ? { metadataBase: new URL(siteUrl), alternates: { canonical: '/' } } : {}),
  applicationName: 'Providence',
  robots: { index: Boolean(siteUrl), follow: Boolean(siteUrl) },
  openGraph: { title, description, type: 'website', locale: 'en_US', siteName: 'Providence',
    ...(siteUrl ? { url: siteUrl, images: [{ url: '/images/providence-cover.png', width: 2172, height: 724, alt: 'Providence — Your files, within reach.' }] } : {}) },
  twitter: { card: 'summary_large_image', title, description,
    ...(siteUrl ? { images: ['/images/providence-cover.png'] } : {}) },
  icons: { icon: '/icon.png', apple: '/icon.png' },
};
export const viewport: Viewport = { themeColor: '#f8faf5', width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#main">Skip to content</a>{children}</body></html>;
}
