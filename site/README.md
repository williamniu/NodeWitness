# NodeWitness product site

Static site for https://nodewitness.williamniu.dev, served by Cloudflare Workers static assets (free plan, no Worker script).

```bash
node site/build.mjs                                   # render pages into site/dist and run the checks
npx wrangler dev --config site/wrangler.jsonc --local # preview on http://localhost:8787
npx wrangler deploy --config site/wrangler.jsonc      # publish
```

The public contact email is not stored in the repo. Set it at build time; without it the site links only to GitHub and the portfolio:

```bash
NW_CONTACT_EMAIL='you@example.com' node site/build.mjs && npx wrangler deploy --config site/wrangler.jsonc
```

`build.mjs` reads its inputs from the pinned commit (`git show origin/main:<path>`), so the content and the line-number links always agree: `tests/agent_env/fixtures/**.json`, `docs/hacks/*.json`, `results/passk/*.{json,md}`, and two test files (to find line numbers for links). It renders everything to HTML at build time, so no raw data ships and the pages need no JavaScript. The one script on the live site is Cloudflare Web Analytics (cookie-free), which Cloudflare injects at the edge; `src/_headers` allows exactly that script and its beacon endpoint, and the footer says so.

The build fails if:
- the output has a file type outside the allowlist;
- any page, or the PNG's text, contains a home-directory path (macOS, Linux, Windows, `~/`), `job-search`, an `.env` reference, an email address, or a key-shaped string (`sk-`, GitHub, Hugging Face, Google, Slack, AWS, private keys). The only exemptions are two exact synthetic strings that are the subject of a replay;
- a results table differs from `results/passk/*.md` row by row and cell by cell, or a home-page number differs from the JSON;
- a fixture scores differently from what its page says (hacks 0, real runs 1, git hacks 1 naive / 0 shipped), or a replay page drops a step.

Nothing here runs an agent, calls a model or starts a container.
