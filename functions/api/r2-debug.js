const SEARCH_INDEX_KEY = "search-index.json";

function jsonResponse(payload, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "no-store");
  return new Response(JSON.stringify(payload), {
    ...init,
    headers,
  });
}

function nowMs() {
  return Date.now();
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const timings = [];
  const startedAt = nowMs();

  try {
    timings.push({
      step: "binding",
      hasSearchIndexBucket: Boolean(env.SEARCH_INDEX_BUCKET),
      hasAssetsBinding: Boolean(env.ASSETS),
      elapsedMs: nowMs() - startedAt,
    });

    if (!env.SEARCH_INDEX_BUCKET) {
      return jsonResponse(
        {
          ok: false,
          error: "Missing SEARCH_INDEX_BUCKET binding",
          timings,
        },
        { status: 500 }
      );
    }

    const getStartedAt = nowMs();
    const object = await env.SEARCH_INDEX_BUCKET.get(SEARCH_INDEX_KEY);
    timings.push({
      step: "r2_get",
      found: Boolean(object),
      size: object ? object.size : null,
      etag: object ? object.httpEtag : null,
      elapsedMs: nowMs() - getStartedAt,
    });

    if (!object) {
      return jsonResponse(
        {
          ok: false,
          error: `Missing ${SEARCH_INDEX_KEY} in R2 bucket`,
          timings,
        },
        { status: 404 }
      );
    }

    const textStartedAt = nowMs();
    const text = await object.text();
    timings.push({
      step: "read_text",
      textLength: text.length,
      elapsedMs: nowMs() - textStartedAt,
    });

    return jsonResponse({
      ok: true,
      url: request.url,
      timings,
    });
  } catch (error) {
    return jsonResponse(
      {
        ok: false,
        error: error.message || "r2-debug failed",
        stack: error.stack || null,
        timings,
      },
      { status: 500 }
    );
  }
}
