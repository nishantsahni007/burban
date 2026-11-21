/**
 * Burban email alerts — runs free on Google Apps Script with a Google Sheet as the database.
 *
 * What it does
 *   - doPost: the app sends {action, email, area, service}. "subscribe" adds a row and emails a
 *     confirmation link (so nobody can sign someone else up). "unsubscribe" removes it.
 *   - doGet:  handles the Confirm and Unsubscribe links in emails.
 *   - checkLaunches: runs every morning. Reads the app's data.json and emails each confirmed
 *     subscriber once, the first time their service shows as Live in their area.
 *
 * Setup (once): paste this file into a new Apps Script project, set APP_URL below, run setup(),
 * then Deploy > New deployment > Web app (Execute as: Me, Who has access: Anyone).
 */

const APP_URL = 'https://nishantsahni007.github.io/burban/';   // where the app lives
const SHEET_NAME = 'subscribers';
const MAX_ALERTS_PER_EMAIL = 40;
const LIVE = { live: true, likely: true };   // same grouping the app uses

function setup() {
  const ss = getSheet_().getParent();
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('checkLaunches').timeBased().everyDays(1).atHour(9).inTimezone('Asia/Kolkata').create();
  Logger.log('Ready. Sheet: ' + ss.getUrl());
}

function getSheet_() {
  const props = PropertiesService.getScriptProperties();
  let id = props.getProperty('SHEET_ID');
  let ss;
  if (id) { ss = SpreadsheetApp.openById(id); }
  else {
    ss = SpreadsheetApp.create('Burban alert subscribers');
    props.setProperty('SHEET_ID', ss.getId());
  }
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.appendRow(['created', 'email', 'area', 'service', 'token', 'status', 'confirmed_at', 'notified_at']);
    sh.setFrozenRows(1);
    const first = ss.getSheetByName('Sheet1');
    if (first) ss.deleteSheet(first);
  }
  return sh;
}

function rows_(sh) {
  const v = sh.getDataRange().getValues();
  return v.slice(1).map((r, i) => ({ row: i + 2, created: r[0], email: r[1], area: r[2], service: r[3],
    token: r[4], status: r[5], confirmed_at: r[6], notified_at: r[7] }));
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function page_(title, text) {
  return HtmlService.createHtmlOutput(
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<div style="font-family:system-ui,sans-serif;max-width:480px;margin:60px auto;padding:0 20px;color:#1B1A17">' +
    '<h2 style="color:#0F5C4A">' + title + '</h2><p>' + text + '</p>' +
    '<p><a href="' + APP_URL + '" style="color:#0F5C4A">Back to Burban</a></p></div>').setTitle(title);
}

function data_() {
  const res = UrlFetchApp.fetch(APP_URL + 'data.json?t=' + Date.now(), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) throw new Error('data.json returned ' + res.getResponseCode());
  return JSON.parse(res.getContentText());
}

function names_(d, area, service) {
  const a = (d.areas || []).find(x => x.id === area);
  const s = (d.services || []).find(x => x.id === service);
  return { area: a ? a.name : area, service: s ? s.name : service };
}

function validEmail_(e) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e || '') && e.length < 200; }

function doPost(e) {
  let body;
  try { body = JSON.parse(e.postData.contents); } catch (err) { return json_({ ok: false, error: 'bad json' }); }
  const email = String(body.email || '').trim().toLowerCase();
  const area = String(body.area || '').slice(0, 40), service = String(body.service || '').slice(0, 40);
  if (!validEmail_(email) || !/^[a-z0-9_-]+$/.test(area) || !/^[a-z0-9_-]+$/.test(service)) return json_({ ok: false, error: 'invalid' });

  const lock = LockService.getScriptLock(); lock.waitLock(20000);
  try {
    const sh = getSheet_();
    const all = rows_(sh);
    const mine = all.filter(r => r.email === email && r.status !== 'unsubscribed');
    const same = mine.find(r => r.area === area && r.service === service);

    if (body.action === 'unsubscribe') {
      if (same) sh.getRange(same.row, 6).setValue('unsubscribed');
      return json_({ ok: true });
    }
    if (body.action !== 'subscribe') return json_({ ok: false, error: 'unknown action' });
    if (same) return json_({ ok: true, already: true });
    if (mine.length >= MAX_ALERTS_PER_EMAIL) return json_({ ok: false, error: 'too many alerts' });

    const d = data_(); const n = names_(d, area, service);
    const token = Utilities.getUuid();
    const confirmed = mine.some(r => r.status === 'active');   // already verified this address before
    sh.appendRow([new Date(), email, area, service, token, confirmed ? 'active' : 'pending', confirmed ? new Date() : '', '']);
    if (!confirmed) {
      const url = ScriptApp.getService().getUrl();
      MailApp.sendEmail({ to: email, subject: 'Confirm your Burban alert for ' + n.service,
        htmlBody: 'Hi! Someone (hopefully you) asked Burban to email this address when <b>' + n.service +
          '</b> becomes available in <b>' + n.area + '</b>.<br><br>' +
          '<a href="' + url + '?action=confirm&token=' + token + '">Yes, confirm my alert</a><br><br>' +
          '<small>If this wasn\'t you, ignore this email and nothing will be sent.</small>' });
    }
    return json_({ ok: true });
  } finally { lock.releaseLock(); }
}

function doGet(e) {
  const p = e.parameter || {};
  const sh = getSheet_();
  const r = rows_(sh).find(x => x.token === p.token);
  if (!r) return page_('Link not found', 'This link has expired or was already used.');
  if (p.action === 'confirm') {
    rows_(sh).filter(x => x.email === r.email && x.status === 'pending').forEach(x => {
      sh.getRange(x.row, 6).setValue('active'); sh.getRange(x.row, 7).setValue(new Date());
    });
    return page_('Alert confirmed', 'We\'ll email you once, the day it becomes available in your area.');
  }
  if (p.action === 'unsubscribe') {
    sh.getRange(r.row, 6).setValue('unsubscribed');
    return page_('Unsubscribed', 'You won\'t get this alert again.');
  }
  return page_('Burban', 'Nothing to do here.');
}

function checkLaunches() {
  const d = data_();
  const sh = getSheet_();
  const url = ScriptApp.getService().getUrl();
  const due = {};   // email -> list of rows now live
  rows_(sh).forEach(r => {
    if (r.status !== 'active' || r.notified_at) return;
    const st = ((d.status || {})[r.area] || {})[r.service];
    if (st && LIVE[st.s]) (due[r.email] = due[r.email] || []).push(Object.assign({ detail: st.d || '' }, r));
  });
  Object.keys(due).forEach(email => {
    if (MailApp.getRemainingDailyQuota() < 1) return;   // Gmail's free daily limit; the rest go tomorrow
    const list = due[email];
    const lines = list.map(r => {
      const n = names_(d, r.area, r.service);
      return '<li><b>' + n.service + '</b> is now available in <b>' + n.area + '</b>' +
        (r.detail ? ' <span style="color:#6B675E">(' + r.detail + ')</span>' : '') +
        ' · <a href="' + url + '?action=unsubscribe&token=' + r.token + '" style="color:#6B675E">stop this alert</a></li>';
    }).join('');
    const first = names_(d, list[0].area, list[0].service);
    MailApp.sendEmail({ to: email,
      subject: list.length === 1 ? first.service + ' is now available in ' + first.area : list.length + ' services are now available near you',
      htmlBody: 'Good news from Burban:<ul>' + lines + '</ul><a href="' + APP_URL + '">Open Burban</a>' });
    list.forEach(r => sh.getRange(r.row, 8).setValue(new Date()));
  });
}
