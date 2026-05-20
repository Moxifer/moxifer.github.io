let documents = [];
const ONLY_MODE_IGNORED_SPEAKERS = new Set(["player", "narrator", "no speaker"]);
const MAX_RESULTS = 500;

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
  documents = sourceDocuments.map((document) => {
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
      excerpt: document.excerpt || "",
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

function matchesTextEntry(entry, normalizedQuery, normalizedPhraseQuery, rawTerms, phraseTerms, matchMode) {
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

function searchDocuments(query, speaker, speakerMode, queryMode) {
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

self.onmessage = (event) => {
  const { type, payload } = event.data || {};

  if (type === "init") {
    prepareDocuments(payload.documents || []);
    self.postMessage({
      type: "ready",
      payload: {
        count: documents.length,
        speakers: payload.speakers || [],
      },
    });
    return;
  }

  if (type === "search") {
    const response = searchDocuments(
      payload.query || "",
      payload.speaker || "",
      payload.speakerMode || "includes",
      payload.queryMode || "contains"
    );
    response.requestId = payload.requestId || 0;
    self.postMessage({
      type: "results",
      payload: response,
    });
  }
};
