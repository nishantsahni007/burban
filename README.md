# Burban

Shows which services reach any area in India, updates itself every day, and notifies people when something they're waiting for arrives. No server, no accounts, no monthly bill.

Live at https://nishantsahni007.github.io/burban/ — share any area with a link like `#bengaluru-hsr-layout`.

```
index.html, sw.js, manifest.webmanifest, icons/   the app (installable web app + background alert checker)
data/index.json, data/places.json, data/city/*    what the app shows. Written by the pipeline; never edit by hand
pipeline/config.json                               providers, city name spellings, canaries. The only file you edit
pipeline/collect_areas.py                          every city, town and neighbourhood in India from OpenStreetMap (monthly)
pipeline/collect_news.py                           launch and "coming soon" stories from Google News (daily)
pipeline/collect_sitemaps.py                       city/neighbourhood pages from providers' public sitemaps (daily)
pipeline/collect_places.py                         stores, gyms, pharmacies from OpenStreetMap (weekly)
pipeline/build.py                                  turns evidence into the data files and checks health
.github/workflows/update-data.yml                  runs it all every morning on GitHub, for free
```

## Statuses

The app shows **Live** or **Not available**. Behind the scenes the data keeps four levels:
live (official neighbourhood page or launch news naming the area), likely (store nearby, several stores in the city, or official in the city), soon (reported coming) and no. Live + likely show as **Live**. It's a rough guide, not a guarantee, and every card links to its evidence.

## Alerts

"Notify me" saves the alert on the phone. The app checks when it opens, and on Android, once Burban is installed, a background check runs about once a day and sends a notification. iPhones show the alert next time the app is opened.

## When something breaks

The daily job fails and GitHub emails you ("Run failed: Update availability data"). The app keeps showing the last good data. Open the failed run, copy the "PROBLEM:" lines, and paste them to Claude.

## Test offline

```
python pipeline/test_pipeline.py      # should print 17 PASS lines
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
