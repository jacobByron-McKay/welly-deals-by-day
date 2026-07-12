// Records an anonymous comment for a venue.
// Browser -> this function -> Supabase (secret key, server-side only).
// Guards: honeypot + length check + basic profanity filter + per-IP burst limit.
// No account, posts instantly. Moderation: set comments.hidden = true in Supabase
// to remove one (public read policy already filters hidden = false).

const SUPABASE_URL = process.env.SUPABASE_URL || 'https://mnzyobedleurvsixnfzr.supabase.co';
const SECRET = process.env.SUPABASE_SECRET_KEY;

// Small, conservative blocklist — masks the worst slurs/obscenities. Deliberately
// short to avoid false positives; real moderation is the hidden flag in Supabase.
const BLOCK = ['fuck','shit','cunt','nigger','faggot','retard','bitch','asshole','dickhead','wanker'];
function clean(text) {
  let out = text;
  for (const w of BLOCK) {
    out = out.replace(new RegExp(w, 'gi'), m => m[0] + '*'.repeat(Math.max(1, m.length - 1)));
  }
  return out;
}

const hits = new Map();
const WINDOW_MS = 60 * 1000;
const MAX_PER_WINDOW = 6; // comments are heavier than ratings — tighter limit
function rateLimited(ip) {
  const now = Date.now();
  const rec = hits.get(ip) || { n: 0, t: now };
  if (now - rec.t > WINDOW_MS) { rec.n = 0; rec.t = now; }
  rec.n++; hits.set(ip, rec);
  return rec.n > MAX_PER_WINDOW;
}

exports.handler = async (event) => {
  const JSON_H = { 'Content-Type': 'application/json' };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers: JSON_H, body: '{"error":"POST only"}' };
  if (!SECRET) return { statusCode: 500, headers: JSON_H, body: '{"error":"server not configured"}' };

  let data;
  try { data = JSON.parse(event.body || '{}'); } catch { return { statusCode: 400, headers: JSON_H, body: '{"error":"bad json"}' }; }

  if (data.hp) return { statusCode: 200, headers: JSON_H, body: '{"ok":true}' };

  const slug = String(data.venue_slug || '').trim().slice(0, 120);
  let body = String(data.body || '').trim().replace(/\s+/g, ' ');
  if (!slug || body.length < 1 || body.length > 1000) {
    return { statusCode: 400, headers: JSON_H, body: '{"error":"comment must be 1-1000 chars"}' };
  }
  body = clean(body);

  const ip = event.headers['x-nf-client-connection-ip'] || (event.headers['x-forwarded-for'] || '').split(',')[0] || 'unknown';
  if (rateLimited(ip)) return { statusCode: 429, headers: JSON_H, body: '{"error":"slow down"}' };

  try {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/comments`, {
      method: 'POST',
      headers: {
        apikey: SECRET,
        Authorization: `Bearer ${SECRET}`,
        'Content-Type': 'application/json',
        Prefer: 'return=representation',
      },
      body: JSON.stringify({ venue_slug: slug, body }),
    });
    const rows = await res.json();
    const saved = Array.isArray(rows) ? rows[0] : rows;
    return { statusCode: 200, headers: JSON_H, body: JSON.stringify({ ok: true, comment: { body: saved.body, created_at: saved.created_at } }) };
  } catch (e) {
    return { statusCode: 502, headers: JSON_H, body: '{"error":"store failed"}' };
  }
};
