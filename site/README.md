# NodeWitness product site

Static site for https://nodewitness.williamniu.dev, served by Cloudflare Workers static assets (free plan, no Worker script).

```bash
node site/build.mjs                                   # render pages into site/dist and run the checks
npx wrangler dev --config site/wrangler.jsonc --local # preview on http://localhost:8787
npx wrangler deploy --config site/wrangler.jsonc      # publish
```

`build.mjs` reads its inputs from the pinned commit (`git show origin/main:<path>`), so the content and the line-number links always agree: `tests/agent_env/fixtures/**.json`, `docs/hacks/*.json`, `results/passk/*.{json,md}`, and two test files (to find line numbers for links). It renders everything to HTML at build time, so no raw data ships and the pages need no JavaScript. The one script on the live site is Cloudflare Web Analytics (cookie-free), which Cloudflare injects at the edge; `src/_headers` allows exactly that script and its beacon endpoint, and the footer says so.

The build fails if:
- the output has a file type outside the allowlist;
- any page, or the PNG's text, contains a home-directory path (macOS, Linux, Windows, `~/`), `job-search`, an `.env` reference, an email address, or a key-shaped string (`sk-`, GitHub, Hugging Face, Google, Slack, AWS, private keys). The only exemptions are two exact synthetic strings that are the subject of a replay;
- a results table differs from `results/passk/*.md` row by row and cell by cell, or a home-page number differs from the JSON;
- a fixture scores differently from what its page says (hacks 0, real runs 1, git hacks 1 naive / 0 shipped), or a replay page drops a step.

## Demo video (Cloudflare R2)

The home page embeds a demo film made outside this repo (demo-film kit). The MP4 is not in git or in `dist/`: it is served from the R2 bucket `williamniu-media` at `https://media.williamniu.dev/`. `src/demo.json` pins the URL, byte size and SHA-256; `src/demo-transcript.txt` is the film's approved script, rendered under the video; `src/demo-poster.jpg` is a frame from it.

To publish a new version, give it a new file name (never overwrite, so the immutable cache stays correct):

```bash
cp <film>/out/<name>-web.mp4 site/media/demo-v7.mp4          # git-ignored upload copy; the build checks it
npx wrangler r2 object put williamniu-media/nodewitness/demo-v7.mp4 --file site/media/demo-v7.mp4 \
  --content-type video/mp4 --cache-control "public, max-age=31536000, immutable" --remote
# update src/demo.json (url, bytes, sha256, duration_s), then:
node site/build.mjs && node site/check-demo.mjs               # local copy + live copy both match demo.json
```

The build also fails if the video URL is not on `media.williamniu.dev`, if the CSP `media-src` does not allow that origin, or if a transcript paragraph is missing from the page.

Nothing here runs an agent, calls a model or starts a container.
