'use client';

import { useState } from 'react';
import { releaseUrl } from './site';

export function Navigation() {
  const [open, setOpen] = useState(false);
  return <header className="header"><a className="brand" href="#" aria-label="Providence home"><img src="/icon.png" alt="" width="30" height="30" />Providence<span className="brand-dot">.</span></a>
    <button className="menu-toggle" aria-expanded={open} aria-controls="navigation" onClick={() => setOpen(!open)}>{open ? 'Close' : 'Menu'}</button>
    <nav id="navigation" className={open ? 'navigation open' : 'navigation'} aria-label="Main navigation">
      <a href="#features" onClick={() => setOpen(false)}>Features</a><a href="#how-it-works" onClick={() => setOpen(false)}>How it works</a><a href="/releases" onClick={() => setOpen(false)}>Release notes</a><a href="#faq" onClick={() => setOpen(false)}>FAQ</a><a className="button small" href={releaseUrl}>Download <span aria-hidden="true">↗</span></a>
    </nav></header>;
}

const examples = [
  { label: 'A half-remembered document', query: 'the database proposal I wrote last semester', name: 'final_v3.pdf', folder: 'Documents / University', excerpt: 'A proposal for a library database, with tables for books, members, and loans.', type: 'PDF', why: 'Meaning + exact text' },
  { label: 'Text inside a scan', query: 'the receipt for my monitor', name: 'desk-upgrade.jpg', folder: 'Pictures / Receipts', excerpt: '27-inch monitor · Order summary · Equipment for the home office.', type: 'JPG', why: 'Scanned text + meaning' },
  { label: 'An exact detail', query: 'invoice ZX92847', name: 'april-invoice.docx', folder: 'Documents / Accounts', excerpt: 'Invoice ZX92847 · Design services · April project delivery.', type: 'DOCX', why: 'Exact text' },
];

export function SearchDemo() {
  const [selected, setSelected] = useState(0);
  const example = examples[selected];
  return <div className="demo"><div className="demo-tabs" role="group" aria-label="Choose an illustrative search example">
    {examples.map((item, index) => <button key={item.label} aria-pressed={selected === index} onClick={() => setSelected(index)}>{item.label}</button>)}
  </div><div className="demo-content" aria-live="polite"><div className="query"><span aria-hidden="true">⌕</span>{example.query}<span className="enter" aria-hidden="true">↵</span></div>
    <div className="demo-result"><span className="file-badge">{example.type}</span><div><span className="result-path">{example.folder}</span><h3>{example.name}</h3><p>{example.excerpt}</p><span className="match"><span aria-hidden="true">✦</span> {example.why}</span></div><span className="result-arrow" aria-hidden="true">↗</span></div>
  </div><p className="demo-caption">Illustrative examples with fictional files. Your searches run in the desktop app.</p></div>;
}

export function AppPreview() {
  const [dark, setDark] = useState(false);
  return <div className="product-window"><div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span>Providence / Your library</span><button aria-pressed={dark} onClick={() => setDark(!dark)}>{dark ? '☀ Light preview' : '◐ Dark preview'}</button></div>
    <img src={`/images/library-${dark ? 'dark' : 'light'}.png`} alt={`Providence desktop in ${dark ? 'dark' : 'light'} mode showing a file library and document preview with fictional demo paths`} width="1450" height="860" fetchPriority="high" />
  </div>;
}
