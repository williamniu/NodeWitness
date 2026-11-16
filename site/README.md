# NodeWitness product site

Static site for https://nodewitness.williamniu.dev, served by Cloudflare Workers static assets (free plan, no Worker script).

```bash
node site/build.mjs                                   # render pages into site/dist and run the checks
npx wrangler dev --config site/wrangler.jsonc --local # preview on http://localhost:8787
npx wrangler deploy --config site/wrangler.jsonc      # publish
```

`build.mjs` reads only these repo files: `tests/agent_env/fixtures/**.json`, `docs/hacks/*.json`, `results/passk/*.{json,md}`, and two test files (to find line numbers for links). It renders everything to HTML at build time, so no raw data and no JavaScript ship. The build fails if the output contains a file type outside the allowlist, a real home-directory path, `job-search`, an env-file reference, an email address, key-shaped strings, or a results cell that differs from `results/passk/*.md`.

Nothing here runs an agent, calls a model or starts a container.
