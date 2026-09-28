# FairTriage NT web app

Next.js 16 (App Router, TypeScript, Tailwind 4). A presentation layer only:
all ranking, explanation and trip planning happens in the FastAPI service in
the parent folder, reached through the `/api` rewrite in `next.config.ts`.

```bash
npm install
npm run dev                                   # http://localhost:3000, API on :8000
FAIRTRIAGE_API=http://localhost:8001 npm run dev   # another API
npm run build                                 # production build
```

- `src/lib/api.ts` typed client for every endpoint used
- `src/lib/format.ts` tier colours, dates, text helpers
- `src/components/` shared UI: `Docket` (tenant record), `RouteLine` (trip route), `CommunityPicker`
- `src/app/` pages: `report`, `track`, `coordinator` (queue, requests, trips, fairness)

Tenant text is shown exactly as the service wrote and verified it; the app
changes presentation, never wording.
