const ONLY_MODE_IGNORED_SPEAKERS = new Set(["player", "narrator", "no speaker"]);
const MAX_RESULTS = 500;
const SEARCH_INDEX_KEY = "search-index.json";

let cachedSearchPayload = null;
let cachedSearchPayloadPromise = null;

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

function normalize(value, lowerCase = true) {
  const normalized = (value || "").replace(/\s+/g, " ").trim();
  return lowerCase ? normalized.toLowerCase() : normalized;
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildPhraseRegex(query, matchCase = false) {
  const terms = normalize(query, !matchCase).split(/[^a-z0-9]+/).filter(Boolean);
  if (!terms.length) {
    return null;
  }
  return new RegExp(terms.map(escapeRegex).join("[^a-z0-9]+"));
}

function getSpeakerKeys(document) {
  if (!Array.isArray(document.__speakerKeys)) {
    const speakers = Array.isArray(document.speakers) ? document.speakers : [];
    document.__speakerKeys = speakers.map((speaker) => normalize(speaker));
  }
  return document.__speakerKeys;
}

function getDocumentSearchChunks(document) {
  if (!Array.isArray(document.__searchChunks)) {
    const chunks = [document.title || "", document.path || ""];
    if (Array.isArray(document.search_chunks)) {
      chunks.push(...document.search_chunks);
    }
    document.__searchChunks = chunks;
  }
  return document.__searchChunks;
}

function getNodeChunks(node) {
  if (!Array.isArray(node.__searchChunks)) {
    if (Array.isArray(node.chunks)) {
      node.__searchChunks = node.chunks;
    } else if (Array.isArray(node.lines)) {
      node.__searchChunks = node.lines;
    } else if (node.text) {
      node.__searchChunks = [node.text];
    } else {
      node.__searchChunks = [];
    }
  }
  return node.__searchChunks;
}

function matchesSpeakerFilter(document, normalizedSpeaker, mode) {
  if (!normalizedSpeaker) {
    return true;
  }

  const speakerKeys = getSpeakerKeys(document);
  if (!speakerKeys.includes(normalizedSpeaker)) {
    return false;
  }

  if (mode !== "only") {
    return true;
  }

  for (const speakerKey of speakerKeys) {
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

function matchesTextValue(
  value,
  normalizedQuery,
  rawTerms,
  phraseRegex,
  matchMode,
  matchCase
) {
  if (typeof value !== "string" || !value.trim()) {
    return false;
  }

  const haystack = normalize(value, !matchCase);

  if (matchMode === "phrase") {
    return Boolean(phraseRegex && phraseRegex.test(haystack));
  }

  if (normalizedQuery && haystack.includes(normalizedQuery)) {
    return true;
  }

  return (
    rawTerms.length > 1 &&
    rawTerms.every((term) => haystack.includes(term))
  );
}

function normalizeDuplicateText(value) {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

function buildDuplicateKey(documentPath, excerpt) {
  return documentPath + "\n" + normalizeDuplicateText(excerpt);
}

function maybePushResult(
  results,
  seenKeys,
  showDuplicates,
  documentPath,
  result,
  state
) {
  if (!showDuplicates) {
    const duplicateKey = buildDuplicateKey(documentPath, result.excerpt);
    if (seenKeys.has(duplicateKey)) {
      return;
    }
    seenKeys.add(duplicateKey);
  }

  state.matchCount += 1;
  if (results.length >= MAX_RESULTS) {
    state.truncated = true;
    return;
  }

  results.push(result);
}

function searchDocuments(
  documents,
  query,
  speaker,
  speakerMode,
  queryMode,
  showDuplicates,
  matchCase
) {
  const normalizedQuery = normalize(query, !matchCase);
  const rawTerms = normalizedQuery ? normalizedQuery.split(" ").filter(Boolean) : [];
  const matchMode =
    queryMode === "phrase" || queryMode === "exact" ? "phrase" : "contains";
  const normalizedSpeaker = normalize(speaker);
  const phraseRegex =
    matchMode === "phrase" ? buildPhraseRegex(query, matchCase) : null;

  const results = [];
  const seenKeys = new Set();
  const state = {
    matchCount: 0,
    truncated: false,
  };

  searchLoop:
  for (const document of documents) {
    if (!matchesSpeakerFilter(document, normalizedSpeaker, speakerMode)) {
      continue;
    }

    for (const chunk of getDocumentSearchChunks(document)) {
      if (
        !matchesTextValue(
          chunk,
          normalizedQuery,
          rawTerms,
          phraseRegex,
          matchMode,
          matchCase
        )
      ) {
        continue;
      }

      maybePushResult(
        results,
        seenKeys,
        showDuplicates,
        document.path,
        {
          path: document.path,
          documentPath: document.path,
          title: document.title,
          speakers: Array.isArray(document.speakers) ? document.speakers : [],
          excerpt: chunk,
          sizeBytes: Number(document.size_bytes) || 0,
        },
        state
      );
      if (state.truncated) {
        break searchLoop;
      }
    }

    for (const node of Array.isArray(document.nodes) ? document.nodes : []) {
      for (const chunk of getNodeChunks(node)) {
        if (
          !matchesTextValue(
            chunk,
            normalizedQuery,
            rawTerms,
            phraseRegex,
            matchMode,
            matchCase
          )
        ) {
          continue;
        }

        maybePushResult(
          results,
          seenKeys,
          showDuplicates,
          document.path,
          {
            path: document.path + "#" + (node.id || ""),
            documentPath: document.path,
            title: document.title,
            speakers: Array.isArray(node.speakers) ? node.speakers : [],
            excerpt: chunk,
            sizeBytes: Number(document.size_bytes) || 0,
          },
          state
        );
        if (state.truncated) {
          break searchLoop;
        }
      }
    }
  }

  return {
    count: state.truncated ? results.length : state.matchCount,
    results,
    truncated: state.truncated,
  };
}

async function loadSearchIndexText(env, requestUrl) {
  if (env.SEARCH_INDEX_BUCKET) {
    const object = await env.SEARCH_INDEX_BUCKET.get(SEARCH_INDEX_KEY);
    if (!object) {
      throw new Error(
        `Missing ${SEARCH_INDEX_KEY} in R2 binding SEARCH_INDEX_BUCKET`
      );
    }
    return object.text();
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
  return response.text();
}

async function loadSearchPayload(env, requestUrl) {
  const text = await loadSearchIndexText(env, requestUrl);
  return JSON.parse(text);
}

async function getSearchPayload(env, requestUrl) {
  if (cachedSearchPayload) {
    return cachedSearchPayload;
  }

  if (!cachedSearchPayloadPromise) {
    cachedSearchPayloadPromise = loadSearchPayload(env, requestUrl)
      .then((payload) => {
        cachedSearchPayload = payload;
        return payload;
      })
      .catch((error) => {
        cachedSearchPayloadPromise = null;
        throw error;
      });
  }

  return cachedSearchPayloadPromise;
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
  const showDuplicates = url.searchParams.get("showDuplicates") === "true";
  const matchCase = url.searchParams.get("matchCase") === "true";
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

      const loadStartedAt = nowMs();
      const text = await loadSearchIndexText(env, request.url);
      timings.push({
        step: "read_text",
        textLength: text.length,
        elapsedMs: nowMs() - loadStartedAt,
      });

      const parseStartedAt = nowMs();
      const payload = JSON.parse(text);
      timings.push({
        step: "json_parse",
        documents: Array.isArray(payload.documents) ? payload.documents.length : 0,
        speakers: Array.isArray(payload.speakers) ? payload.speakers.length : 0,
        elapsedMs: nowMs() - parseStartedAt,
      });

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
    const payload = await getSearchPayload(env, request.url);
    const response = searchDocuments(
      Array.isArray(payload.documents) ? payload.documents : [],
      query,
      speaker,
      speakerMode,
      queryMode,
      showDuplicates,
      matchCase
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
