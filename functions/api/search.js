const ONLY_MODE_IGNORED_SPEAKERS = new Set(["player", "narrator", "no speaker"]);
const MAX_RESULTS = 500;
const SEARCH_INDEX_KEY = "search-index.json";

let preparedIndexPromise = null;

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

function normalize(value) {
  return (value || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizePhrase(value) {
  return normalize(value)
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function prepareTextEntries(values) {
  const seen = new Set();
  const entries = [];

  for (const value of Array.isArray(values) ? values : []) {
    if (typeof value !== "string" || !value.trim()) {
      continue;
    }

    const key = value.trim();
    if (seen.has(key)) {
      continue;
    }

    seen.add(key);
    entries.push({
      text: value,
      haystack: normalize(value),
      phraseHaystack: normalizePhrase(value),
    });
  }

  return entries;
}

function prepareDocuments(sourceDocuments) {
  return (sourceDocuments || []).map((document) => {
    const speakers = Array.isArray(document.speakers) ? document.speakers : [];
    const documentSearchChunks = prepareTextEntries([
      document.title || "",
      document.path || "",
      ...(Array.isArray(document.search_chunks) ? document.search_chunks : []),
    ]);

    const nodes = Array.isArray(document.nodes)
      ? document.nodes.map((node) => {
          const nodeSpeakers = Array.isArray(node.speakers) ? node.speakers : [];
          const nodeChunks = prepareTextEntries([
            ...(Array.isArray(node.chunks)
              ? node.chunks
              : Array.isArray(node.lines)
                ? node.lines
                : node.text
                  ? [node.text]
                  : []),
          ]);

          return {
            id: node.id || "",
            speakers: nodeSpeakers,
            chunks: nodeChunks,
          };
        })
      : [];

    return {
      path: document.path,
      title: document.title,
      speakers,
      sizeBytes: Number(document.size_bytes) || 0,
      searchChunks: documentSearchChunks,
      nodes,
      speakerKeys: speakers.map((speaker) => normalize(speaker)),
    };
  });
}

function matchesSpeakerFilter(document, speaker, mode) {
  const normalizedSpeaker = normalize(speaker);
  if (!normalizedSpeaker) {
    return true;
  }

  if (!document.speakerKeys.includes(normalizedSpeaker)) {
    return false;
  }

  if (mode !== "only") {
    return true;
  }

  for (const speakerKey of document.speakerKeys) {
    if (speakerKey === normalizedSpeaker) {
      continue;
    }
    if (ONLY_MODE_IGNORED_SPEAKERS.has(speakerKey)) {
      continue;
    }
    return false;
  }

  return true;
}

function matchesTextEntry(
  entry,
  normalizedQuery,
  normalizedPhraseQuery,
  rawTerms,
  phraseTerms,
  matchMode
) {
  if (!entry || !entry.haystack) {
    return false;
  }

  if (matchMode === "phrase") {
    return Boolean(
      normalizedPhraseQuery && entry.phraseHaystack.includes(normalizedPhraseQuery)
    );
  }

  if (normalizedQuery && entry.haystack.includes(normalizedQuery)) {
    return true;
  }

  if (normalizedPhraseQuery && entry.phraseHaystack.includes(normalizedPhraseQuery)) {
    return true;
  }

  const rawTermsMatch =
    rawTerms.length > 0 && rawTerms.every((term) => entry.haystack.includes(term));
  const phraseTermsMatch =
    phraseTerms.length > 0 &&
    phraseTerms.every((term) => entry.phraseHaystack.includes(term));

  return rawTermsMatch || phraseTermsMatch;
}

function searchDocuments(documents, query, speaker, speakerMode, queryMode) {
  const normalizedQuery = normalize(query);
  const normalizedPhraseQuery = normalizePhrase(query);
  const rawTerms = normalizedQuery ? normalizedQuery.split(" ").filter(Boolean) : [];
  const phraseTerms = normalizedPhraseQuery
    ? normalizedPhraseQuery.split(" ").filter(Boolean)
    : [];
  const matchMode =
    queryMode === "phrase" || queryMode === "exact" ? "phrase" : "contains";

  const results = [];
  let totalCount = 0;

  for (const document of documents) {
    if (!matchesSpeakerFilter(document, speaker, speakerMode)) {
      continue;
    }

    for (const chunk of document.searchChunks) {
      if (
        !matchesTextEntry(
          chunk,
          normalizedQuery,
          normalizedPhraseQuery,
          rawTerms,
          phraseTerms,
          matchMode
        )
      ) {
        continue;
      }

      totalCount += 1;
      if (results.length < MAX_RESULTS) {
        results.push({
          path: document.path,
          documentPath: document.path,
          title: document.title,
          speakers: document.speakers,
          excerpt: chunk.text,
          sizeBytes: document.sizeBytes,
        });
      }
    }

    for (const node of document.nodes) {
      for (const chunk of node.chunks) {
        if (
          !matchesTextEntry(
            chunk,
            normalizedQuery,
            normalizedPhraseQuery,
            rawTerms,
            phraseTerms,
            matchMode
          )
        ) {
          continue;
        }

        totalCount += 1;
        if (results.length < MAX_RESULTS) {
          results.push({
            path: document.path + "#" + node.id,
            documentPath: document.path,
            title: document.title,
            speakers: node.speakers,
            excerpt: chunk.text,
            sizeBytes: document.sizeBytes,
          });
        }
      }
    }
  }

  return {
    count: totalCount,
    results,
    truncated: totalCount > results.length,
  };
}

async function loadSearchIndexPayload(env, requestUrl) {
  if (env.SEARCH_INDEX_BUCKET) {
    const object = await env.SEARCH_INDEX_BUCKET.get(SEARCH_INDEX_KEY);
    if (!object) {
      throw new Error(
        `Missing ${SEARCH_INDEX_KEY} in R2 binding SEARCH_INDEX_BUCKET`
      );
    }
    return object.json();
  }

  if (!env.ASSETS) {
    throw new Error(
      "Search index source is not configured. Add an R2 binding named SEARCH_INDEX_BUCKET."
    );
  }

  const assetUrl = new URL("/" + SEARCH_INDEX_KEY, requestUrl);
  const response = await env.ASSETS.fetch(assetUrl);
  if (!response.ok) {
    throw new Error("Failed to load search index asset");
  }
  return response.json();
}

async function loadPreparedIndex(env, requestUrl) {
  const payload = await loadSearchIndexPayload(env, requestUrl);
  return prepareDocuments(payload.documents || []);
}

function getPreparedIndex(env, requestUrl) {
  if (!preparedIndexPromise) {
    preparedIndexPromise = loadPreparedIndex(env, requestUrl).catch((error) => {
      preparedIndexPromise = null;
      throw error;
    });
  }

  return preparedIndexPromise;
}

export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "cache-control": "no-store",
    },
  });
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const query = url.searchParams.get("query") || "";
  const speaker = url.searchParams.get("speaker") || "";
  const speakerMode = url.searchParams.get("speakerMode") || "includes";
  const queryMode = url.searchParams.get("queryMode") || "contains";
  const requestId = Number(url.searchParams.get("requestId") || "0");
  const debug = url.searchParams.get("debug") === "1";

  if (debug) {
    const timings = [];
    const startedAt = nowMs();
    try {
      timings.push({
        step: "binding",
        hasSearchIndexBucket: Boolean(env.SEARCH_INDEX_BUCKET),
        hasAssetsBinding: Boolean(env.ASSETS),
        elapsedMs: nowMs() - startedAt,
      });

      let object = null;
      if (env.SEARCH_INDEX_BUCKET) {
        const getStartedAt = nowMs();
        object = await env.SEARCH_INDEX_BUCKET.get(SEARCH_INDEX_KEY);
        timings.push({
          step: "r2_get",
          found: Boolean(object),
          size: object ? object.size : null,
          etag: object ? object.httpEtag : null,
          elapsedMs: nowMs() - getStartedAt,
        });
      } else if (env.ASSETS) {
        const assetFetchStartedAt = nowMs();
        const assetUrl = new URL("/" + SEARCH_INDEX_KEY, request.url);
        const response = await env.ASSETS.fetch(assetUrl);
        timings.push({
          step: "assets_fetch",
          ok: response.ok,
          status: response.status,
          elapsedMs: nowMs() - assetFetchStartedAt,
        });
      }

      if (object) {
        const parseStartedAt = nowMs();
        const payload = await object.json();
        timings.push({
          step: "json_parse",
          documents: Array.isArray(payload.documents) ? payload.documents.length : 0,
          speakers: Array.isArray(payload.speakers) ? payload.speakers.length : 0,
          elapsedMs: nowMs() - parseStartedAt,
        });

        const prepareStartedAt = nowMs();
        const prepared = prepareDocuments(payload.documents || []);
        timings.push({
          step: "prepare_documents",
          preparedDocuments: prepared.length,
          elapsedMs: nowMs() - prepareStartedAt,
        });
      }

      return jsonResponse({
        ok: true,
        requestId,
        timings,
      });
    } catch (error) {
      return jsonResponse(
        {
          ok: false,
          requestId,
          error: error.message || "Debug failed",
          stack: error.stack || null,
          timings,
        },
        { status: 500 }
      );
    }
  }

  if (!query.trim()) {
    return jsonResponse({
      requestId,
      count: 0,
      results: [],
      truncated: false,
    });
  }

  try {
    const documents = await getPreparedIndex(env, request.url);
    const response = searchDocuments(
      documents,
      query,
      speaker,
      speakerMode,
      queryMode
    );
    response.requestId = requestId;
    return jsonResponse(response);
  } catch (error) {
    return jsonResponse(
      {
        error: error.message || "Search failed",
        requestId,
      },
      { status: 500 }
    );
  }
}
