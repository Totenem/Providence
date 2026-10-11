# Providence website

Next.js marketing site with app screenshots, an interactive fictional search demo, feature descriptions, FAQ, privacy page, and download CTAs linking to the latest GitHub release. The site clearly separates released v1.0.1 features from upcoming v1.0.2 work.

## Run locally

Start Docker Desktop using Linux containers. From the repository root:

```sh
docker compose -f website/compose.yaml up --build -d --wait
```

Open http://localhost:3000. On Windows, `./scripts/start-website.ps1` runs the same command. Node.js and `node_modules` stay inside Docker; no host Node installation is required. The website has its own Compose project and does not start the desktop app containers. Re-run the command after editing the source to rebuild the site.

```sh
docker compose -f website/compose.yaml logs -f website
docker compose -f website/compose.yaml down
```

The website is separate from the desktop application. It never reads local documents or runs the AI models. No analytics, external fonts, account system, or tracking scripts are included.

## When a domain is available

Copy `.env.example` to `.env` in this directory, set `NEXT_PUBLIC_SITE_URL` to the final HTTPS origin, and rebuild with `docker compose --env-file website/.env -f website/compose.yaml up --build -d --wait` from the repository root. The URL is supplied at build time. This enables canonical URLs, the sitemap, social preview URLs, and search indexing. Without a domain, the local site intentionally sends `noindex` and disallows crawling.

Edit `app/site.ts` for FAQs and GitHub destinations. Screenshot files in `public/images` use fictional demo paths. Responsive layouts, visible keyboard focus, skip navigation, native expandable FAQs, and reduced-motion preferences are supported.
