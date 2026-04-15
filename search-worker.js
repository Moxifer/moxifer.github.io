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

function prepareDocuments(sourceDocuments) {
  documents = sourceDocuments.map((document) => {
    const speakers = Array.isArray(document.speakers) ? document.speakers : [];
    const nodes = Array.isArray(document.nodes)
      ? document.nodes.map((node) => {
          const nodeSpeakers = Array.isArray(node.speakers) ? node.speakers : [];
          const nodeText = node.text || "";
          return {
            id: node.id || "",
            speakers: nodeSpeakers,
            text: nodeText,
            haystack: normalize(nodeText),
            phraseHaystack: normalizePhrase(nodeText),
          };
        })
      : [];
    return {
      path: document.path,
      title: document.title,
      speakers,
      excerpt: document.excerpt || "",
      sizeBytes: Number(document.size_bytes) || 0,
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

function searchDocuments(query, speaker, speakerMode, queryMode) {
  const normalizedQuery = normalize(query);
  const normalizedPhraseQuery = normalizePhrase(query);
  const queryTerms = normalizedQuery ? normalizedQuery.split(" ") : [];
  const matchMode =
    queryMode === "phrase" || queryMode === "exact" ? "phrase" : "contains";

  const results = [];
  let totalCount = 0;
  for (const document of documents) {
    if (!matchesSpeakerFilter(document, speaker, speakerMode)) {
      continue;
    }

    for (const node of document.nodes) {
      if (!node.haystack) {
        continue;
      }

      if (matchMode === "phrase") {
        if (!normalizedPhraseQuery || !node.phraseHaystack.includes(normalizedPhraseQuery)) {
          continue;
        }
      } else if (!node.haystack.includes(normalizedQuery)) {
        let allTermsPresent = true;
        for (const term of queryTerms) {
          if (!node.haystack.includes(term)) {
            allTermsPresent = false;
            break;
          }
        }
        if (!allTermsPresent) {
          continue;
        }
      }

      totalCount += 1;
      if (results.length < MAX_RESULTS) {
        results.push({
          path: document.path + "#" + node.id,
          documentPath: document.path,
          title: document.title,
          speakers: node.speakers,
          excerpt: node.text,
          sizeBytes: document.sizeBytes,
        });
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
    self.postMessage({
      type: "results",
      payload: response,
    });
  }
};
