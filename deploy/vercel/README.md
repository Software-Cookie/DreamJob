# DreamJob on Vercel (proxy)

DreamJob runs as a long-lived server (background crawler, in-memory job index, disk snapshot), which Vercel's
serverless functions cannot host. The app runs on Hugging Face Spaces; this folder is a tiny Vercel project that
forwards every request to it, so visitors use your Vercel address (and any custom domain you add there).

1. Replace `YOUR-HF-USERNAME` in `vercel.json` with your Hugging Face username.
2. From this folder: `vercel login`, then `vercel --prod`.
3. On the Space, set the variable `TRUSTED_PROXY_HOPS=2` (Vercel plus Hugging Face's own proxy), so rate limits and
   partner APIs see each visitor's real IP address.
