# Burban

Shows which services reach your area, and updates itself every day with no server and no monthly bill.

```
index.html, manifest.webmanifest, sw.js, icons/   the app (installable web app)
data.json                                          what the app shows. Written by the pipeline; never edit by hand
pipeline/config.json                               cities, areas, providers. The only file you edit
pipeline/collect_news.py                           launch and "coming soon" stories from Google News
pipeline/collect_sitemaps.py                       city and neighbourhood pages from providers' public sitemaps
pipeline/collect_places.py                         stores, gyms, pharmacies from OpenStreetMap + distance rule
pipeline/build.py                                  merges everything into data.json, finds changes, checks health
pipeline/notify.py                                 emails you only if something launched or broke
pipeline/run_all.py                                runs all of the above
pipeline/test_pipeline.py                          offline test (no internet needed)
.github/workflows/update-data.yml                  runs the pipeline every morning on GitHub, for free
```

## How each status is decided

| Status | Meaning | Evidence that triggers it |
| --- | --- | --- |
| Live | Confirmed for this area | Provider has an official page for this area, or a launch story names this area |
| Likely | Very probably available | A store/centre within range (3 km for quick commerce and gyms, 2 km for pharmacies), or the provider officially operates in the city |
| Coming soon | Announced | A "set to launch / coming soon" story for this area or city (kept for 8 months) |
| No sign yet | Nothing found | None of the above |

Every card links to its evidence, so users can see why.

## One-time setup (about 30 minutes)

1. **Create a public GitHub repository** and upload this whole folder, including the hidden `.github` and `.well-known` folders. On github.com, use "Add file → Upload files" and drag in the folder contents. Keep it public: scheduled jobs are free and unlimited in public repositories.
2. **Allow the job to save its results:** repository → Settings → Actions → General → Workflow permissions → "Read and write permissions" → Save.
3. **Turn on the website:** Settings → Pages → Deploy from branch `main`, folder `/ (root)`. Your app will be at `https://<username>.github.io/<repo>/`.
4. **Run it once now:** Actions tab → "Update availability data" → "Run workflow". Wait about 5–10 minutes, then open the app: the "First data update pending" banner disappears and real results appear.
5. **Optional: emails to you.** Create a free Resend account, make an API key, then in GitHub go to Settings → Secrets and variables → Actions and add `RESEND_API_KEY` and `OWNER_EMAIL`. Without these, reports appear in the Actions log instead.

From then on it runs every morning at about 7 am IST. Store locations refresh on Mondays.

## What you'll ever need to do

- **Nothing on a normal day.** Quiet days send no email.
- **When you get a "Needs a look" email:** a source has changed shape, such as a provider renaming its sitemap. The app keeps showing the last good data, so nothing breaks for users. Paste the email to Claude, or fix it yourself.
- **To add an area, city or provider:** edit `pipeline/config.json` and the next run picks it up. An area needs a name, pincode, latitude/longitude, and the spellings it appears under (`aliases`). A provider needs the names used in the news (`news`), its website domain if it has neighbourhood pages (`sitemap`), and its store name on maps (`osm`).

## Test it on your own computer (optional)

```
python pipeline/test_pipeline.py      # offline test, should print 14 PASS lines
python pipeline/run_all.py --all      # real run (needs internet), writes data.json
python -m http.server                 # then open http://localhost:8000
```

## Publish to Google Play

1. pwabuilder.com → paste your app URL → Package for stores → Android → download.
2. Put the package ID and SHA-256 fingerprint it gives you into `.well-known/assetlinks.json`. This file must be served from your domain's root, so either name the repository `<username>.github.io` or use Cloudflare Pages.
3. Google Play developer account: US$25 one time. New personal accounts must run a closed test with at least 12 testers for 14 days in a row before going public.

## Honest limits

- "Live" and "Likely" come from public evidence, not the providers' own delivery checks. "Likely" means a store or official presence is nearby, not a guarantee for your exact building.
- OpenStreetMap's coverage of dark stores is patchy, so some areas will show "No sign yet" even where Blinkit or Zepto deliver. More sources can be added later without changing the app.
- News matching uses keywords. A few odd headlines may slip through; each one is linked so users can judge.
- "Notify me" saves alerts on the user's phone for now. Sending real alerts to users is the next step: the pipeline already writes `pipeline/evidence/changes.json` listing every new launch, ready to send from.
