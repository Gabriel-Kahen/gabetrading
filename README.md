# gabetrading

Source for `gabetrading.com`.

## Structure

- `src/`: the current live `gabetrading` site built with Vite.
- `gabejaytrading/`: the legacy `gabejaytrading` frontend source.
- `backend/`: the FastAPI paper-trading backend that powers the live dashboard.

The root site deploys at `/`.

The legacy app is built from `gabejaytrading/` and published at `/old/`.

## Local development

Install dependencies in both apps:

```bash
npm install
npm --prefix gabejaytrading install
```

Run the current site locally:

```bash
npm run dev
```

Run the backend locally:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Run the legacy site locally:

```bash
npm --prefix gabejaytrading start
```

## Build and deploy

Build both sites into the final Pages bundle:

```bash
npm run build
```

This does two things:

- builds the Vite app into `dist/`
- builds the legacy CRA app into `gabejaytrading/build/` and copies it into `dist/old/`

Deploy to GitHub Pages:

```bash
npm run deploy
```

The custom domain for this repo is `gabetrading.com`.
