import type { Metadata } from 'next';
import { releaseUrl, repositoryUrl, siteUrl } from '../site';

export const metadata: Metadata = {
  title: 'Release notes · Providence',
  description: 'Providence release notes, validation, and known limits.',
  ...(siteUrl ? { alternates: { canonical: '/releases' } } : {}),
};

export default function Releases() {
  return <main id="main" className="wrap prose release-page">
    <a className="text-link" href="/">← Back to Providence</a>
    <p className="eyebrow">RELEASE NOTES</p>
    <h1>Providence 1.0.3</h1>
    <p className="release-lede">A more personal library: keep the files you reach for, save the searches you return to, and look inside more of the formats already on your computer.</p>
    <p><a className="button small" href={releaseUrl}>Download for Windows ↗</a></p>
    <h2>What’s new</h2>
    <ul>
      <li><strong>Favorites and saved searches.</strong> Mark files, filter to favorites, and save a query together with its filters and clues.</li>
      <li><strong>Optional local evidence reranking.</strong> A deterministic word-overlap pass can add filename and passage evidence after retrieval. It makes no cloud requests and downloads no conversational model.</li>
      <li><strong>More formats.</strong> EPUB, OpenDocument text/spreadsheets/slides, Jupyter notebooks, legacy Office files through local LibreOffice, and HEIC/HEIF images.</li>
    </ul>
    <h2>Validation and limits</h2>
    <p>The source suite passed 101 tests with one symlink-permission skip. Legacy Office extraction requires a local LibreOffice installation. Formula calculation, notebook rich outputs, image no-match calibration, and trained-model reranking are outside this release’s guarantees.</p>
    <p>Providence remains offline-first: originals stay unchanged, extracted content stays in the local Providence index, and the desktop app does not send files to cloud inference.</p>
    <p><a className="text-link" href={`${repositoryUrl}/blob/main/docs/releases/1.0.3.md`}>Read the full release summary on GitHub ↗</a></p>
  </main>;
}
