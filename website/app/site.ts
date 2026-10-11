export const releaseUrl = 'https://github.com/Totenem/Providence/releases/latest';
export const repositoryUrl = 'https://github.com/Totenem/Providence';
const configured = process.env.NEXT_PUBLIC_SITE_URL;
export const siteUrl = configured ? new URL(configured).origin : undefined;

export const faqs = [
  { question: 'Does Providence send my files to a server?', answer: 'No. The desktop app extracts text, runs OCR, creates embeddings, and searches on your computer. Its bundled models work offline after setup. Your original files stay unchanged.' },
  { question: 'Which operating systems are supported?', answer: 'The downloadable portable application targets 64-bit Windows. Extract the entire ZIP, keep Providence.exe with its _internal folder, and open Providence.exe. The source repository also documents a Docker desktop preview.' },
  { question: 'Is Providence free?', answer: 'Yes. Providence is open source under the MIT license. There is no subscription or account required for the desktop app. Bundled libraries and models retain their own licenses.' },
  { question: 'Which files can I search?', answer: 'The current v1.0.1 release searches PDF, DOCX, TXT, Markdown, and OCR text in PNG/JPEG images. Other discovered files can be found by name and path. Version 1.0.2 is adding spreadsheets, presentations, programming files, visual image search, and duplicate review.' },
  { question: 'Will it search automatically while I type?', answer: 'No. Press Enter or click Search when you are ready. Indexing selected locations updates automatically in the background. Searches lasting over 20 seconds offer optional clues to help narrow the results.' },
  { question: 'Why is the download large?', answer: 'The portable release includes the application, OCR, and local AI models so it can work without a cloud service. Qwen uses more memory and CPU; MiniLM is available as a lighter option. Check GitHub Releases for the current package size.' },
  { question: 'Can I choose what gets indexed?', answer: 'Yes. Choose your library locations and edit exclusions in settings. System/application folders, caches, inaccessible locations, reparse points, and cloud placeholders are excluded by default. Extracted text is stored locally, and the index is not encrypted.' },
  { question: 'Where do I download updates or report a bug?', answer: 'Download releases and read their notes on GitHub. Report reproducible problems in the repository’s Issues tab, using fictional or anonymized files instead of private documents. The app does not automatically install updates.' },
];
