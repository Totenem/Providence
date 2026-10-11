import type { MetadataRoute } from 'next';
import { siteUrl } from './site';
export default function sitemap(): MetadataRoute.Sitemap {
  return siteUrl ? [{ url: siteUrl, changeFrequency: 'monthly', priority: 1 }, { url: `${siteUrl}/privacy`, changeFrequency: 'yearly', priority: 0.3 }] : [];
}
