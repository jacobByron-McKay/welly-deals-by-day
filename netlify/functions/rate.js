// Records an anonymous 1-5 star rating for a venue.
// Browser -> this function -> Supabase (with the secret key, server-side only).
// One vote per device (device_id): a repeat vote updates the existing row, so a
// single device can't inflate the count. Guards: honeypot + per-IP burst limit.

const SUPABASE_URL = process.env.SUPABASE_URL || 'https://mnzyobedleurvsixnfzr.supabase.co';
const SECRET = process.env.SUPABASE_SECRET_KEY;

// Per-warm-instance burst limit: max N writes per IP per window.
const hits = new Map();
const WINDOW_MS = 60 * 1000;
const MAX_PER_WINDOW = 20;
function rateLimited(ip) {
  const now = Date.now();
  const rec = hits.get(ip) || { n: 0, t: now };
  if (now - rec.t > WINDOW_MS) { rec.n = 0; rec.t = now; }
  rec.n++; hits.set(ip, rec);
  return rec.n > MAX_PER_WINDOW;
}

function sb(path, opts) {
  return fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...opts,
    headers: {
      apikey: SECRET,
      Authorization: `Bearer ${SECRET}`,
      'Content-Type': 'application/json',
      ...(opts && opts.headers),
    },
  });
}

exports.handler = async (event) => {
  const JSON_H = { 'Content-Type': 'application/json' };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers: JSON_H, body: '{"error":"POST only"}' };
  if (!SECRET) return { statusCode: 500, headers: JSON_H, body: '{"error":"server not configured"}' };

  let data;
  try { data = JSON.parse(event.body || '{}'); } catch { return { statusCode: 400, headers: JSON_H, body: '{"error":"bad json"}' }; }

  // Honeypot: bots fill hidden fields. Pretend success, store nothing.
  if (data.hp) return { statusCode: 200, headers: JSON_H, body: '{"ok":true}' };

  const slug = String(data.venue_slug || '').trim().slice(0, 120);
  const stars = Number(data.stars);
  const device = String(data.device_id || '').trim().slice(0, 64);
  if (!slug || !Number.isInteger(stars) || stars < 1 || stars > 5 || !device) {
    return { statusCode: 400, headers: JSON_H, body: '{"error":"invalid rating"}' };
  }

  const ip = event.headers['x-nf-client-connection-ip'] || (event.headers['x-forwarded-for'] || '').split(',')[0] || 'unknown';
  if (rateLimited(ip)) return { statusCode: 429, headers: JSON_H, body: '{"error":"slow down"}' };

  try {
    // Upsert by (venue_slug, device_id): update if this device already voted, else insert.
    const q = `ratings?venue_slug=eq.${encodeURIComponent(slug)}&device_id=eq.${encodeURIComponent(device)}&select=id`;
    const existing = await sb(q).then(r => r.json());
    if (Array.isArray(existing) && existing.length) {
      await sb(`ratings?id=eq.${existing[0].id}`, { method: 'PATCH', body: JSON.stringify({ stars }) });
    } else {
      await sb('ratings', { method: 'POST', body: JSON.stringify({ venue_slug: slug, stars, device_id: device }) });
    }

    // Return fresh aggregate for this venue.
    const rows = await sb(`ratings?venue_slug=eq.${encodeURIComponent(slug)}&select=stars`).then(r => r.json());
    const count = rows.length;
    const avg = count ? Math.round((rows.reduce((s, r) => s + r.stars, 0) / count) * 10) / 10 : 0;
    return { statusCode: 200, headers: JSON_H, body: JSON.stringify({ ok: true, avg, count }) };
  } catch (e) {
    return { statusCode: 502, headers: JSON_H, body: '{"error":"store failed"}' };
  }
};
