function jsonResponse(payload, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "no-store");
  return new Response(JSON.stringify(payload), {
    ...init,
    headers,
  });
}

export async function onRequestGet(context) {
  return jsonResponse({
    ok: true,
    url: context.request.url,
    hasSearchIndexBucket: Boolean(context.env.SEARCH_INDEX_BUCKET),
    hasAssetsBinding: Boolean(context.env.ASSETS),
  });
}
