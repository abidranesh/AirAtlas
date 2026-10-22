# web

AirAtlas frontend: Next.js 16 + TypeScript + Tailwind v4, Leaflet/OpenStreetMap, Recharts.
Design notes and verification: [docs/phase-5-frontend.md](../docs/phase-5-frontend.md).

```bash
npm install
echo API_ORIGIN=http://127.0.0.1:8000 > .env.local   # local API: python ../api/dev_server.py
npm run dev        # http://localhost:3000
npm test           # vitest
npm run typecheck && npm run lint && npm run build
```

`src/lib/` holds the API types and client, formatting (local time zones, contrast), scale handling and map
styling rules (unit-tested). `src/components/` holds the views. Pages in `src/app/` are thin static shells.
