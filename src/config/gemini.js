/**
 * JUSTICE Legal AI Workspace — Backend-Connected AI & Statutory Engine Client
 * All AI operations strictly invoke the FastAPI backend at http://localhost:8000.
 * Zero client-side generative language calls; zero API key exposure in browser bundle.
 * Enforced model: gemini-3.8-flash (orchestrated via backend google-genai SDK).
 */

export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";
export const API_BASE = `${BACKEND_URL}/api/v1`;

export const geminiConfig = {
  model: "openai/gpt-oss-120b",
  backendUrl: BACKEND_URL,
  apiBase: API_BASE
};

/**
 * Returns false for client-side API key exposure; keys are secured server-side.
 */
export function getGeminiApiKey() {
  return null;
}

/**
 * Indicates whether the backend AI service is expected to be configured.
 */
export function isGeminiConfigured() {
  return true;
}

/**
 * Verifies backend health and active Gemini 3.8 Flash integration via GET /health.
 */
export async function verifyGeminiConnection() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) {
      console.warn(`[JUSTICE AI] Backend health check returned status ${res.status}`);
      return { success: false, status: res.status };
    }
    const data = await res.json();
    console.info(`[JUSTICE AI] Backend connected. Enforced model: ${data.enforced_model}. System Mode: ${data.system_mode}`);
    return { success: true, model: data.enforced_model, data };
  } catch (err) {
    console.warn(`[JUSTICE AI] Backend health check unreachable at ${BACKEND_URL}:`, err.message);
    return { success: false, error: err.message };
  }
}

/**
 * Synthesizes legal analysis via FastAPI backend (replaces client-side Gemini call).
 */
export async function callGeminiGenerateContent(prompt) {
  try {
    const res = await fetch(`${API_BASE}/audit/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        clause_text: prompt,
        contract_title: "Statutory Analysis"
      })
    });
    if (!res.ok) {
      console.warn(`[JUSTICE AI] Synthesize endpoint returned status ${res.status}`);
      return null;
    }
    const data = await res.json();
    return data?.synthesis || null;
  } catch (err) {
    console.warn(`[JUSTICE AI] Error contacting backend synthesis endpoint:`, err.message);
    return null;
  }
}

/**
 * MODULE A: Document Analyzer / Clause Auditor
 * POST /api/v1/audit/verify-clause
 */
export async function verifyClauseWithBackend(clauseText, clauseTitle = "Restrictive Covenant") {
  const res = await fetch(`${API_BASE}/audit/verify-clause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      clause_text: clauseText,
      clause_title: clauseTitle
    })
  });
  if (!res.ok) {
    throw new Error(`Clause verification failed (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * MODULE A: Full Contract Document Audit
 * POST /api/v1/audit/contract (accepts FormData or JSON)
 */
export async function auditContractWithBackend(input, title = "Commercial Agreement") {
  if (input instanceof FormData) {
    const res = await fetch(`${API_BASE}/audit/contract`, {
      method: 'POST',
      body: input
    });
    if (!res.ok) {
      throw new Error(`Contract audit failed (HTTP ${res.status})`);
    }
    return await res.json();
  } else {
    const res = await fetch(`${API_BASE}/audit/contract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: input,
        title: title
      })
    });
    if (!res.ok) {
      throw new Error(`Contract audit failed (HTTP ${res.status})`);
    }
    return await res.json();
  }
}

/**
 * Client-side 10-minute LRU Cache (200 items max) for Universal Search & AI answers.
 * Guarantees sub-second (<50ms) response on warm searches.
 */
class ClientLRUCache {
  constructor(capacity = 200, ttlMs = 10 * 60 * 1000) {
    this.capacity = capacity;
    this.ttlMs = ttlMs;
    this.cache = new Map();
  }

  get(key) {
    if (!this.cache.has(key)) return null;
    const entry = this.cache.get(key);
    if (Date.now() - entry.timestamp > this.ttlMs) {
      this.cache.delete(key);
      return null;
    }
    // Refresh LRU position
    this.cache.delete(key);
    this.cache.set(key, entry);
    return entry.value;
  }

  set(key, value) {
    if (this.cache.has(key)) {
      this.cache.delete(key);
    }
    this.cache.set(key, { value, timestamp: Date.now() });
    if (this.cache.size > this.capacity) {
      const oldestKey = this.cache.keys().next().value;
      this.cache.delete(oldestKey);
    }
  }

  clear() {
    this.cache.clear();
  }
}

export const clientSearchCache = new ClientLRUCache(200, 10 * 60 * 1000);
export const clientAnswerCache = new ClientLRUCache(200, 10 * 60 * 1000);

/**
 * MODULE B: Universal Search
 * POST /api/v1/search
 */
export async function searchPrecedentsWithBackend(query, court = "ALL", benchType = "ALL", enableHyde = true, limit = 8, bypassCorrection = false) {
  const normalizedQuery = (query || "").trim().toLowerCase();
  const cacheKey = `search:${normalizedQuery}:${court}:${benchType}:${enableHyde}:${limit}:${bypassCorrection}`;
  const cached = clientSearchCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const res = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: query,
      court: court,
      bench_type: benchType,
      enable_hyde: enableHyde,
      limit: limit,
      bypass_correction: bypassCorrection
    })
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Universal search failed (HTTP ${res.status})`);
  }
  const data = await res.json();
  clientSearchCache.set(cacheKey, data);
  return data;
}

/**
 * MODULE B: AI Answer for Universal Search
 * POST /api/v1/search/answer
 */
export async function fetchSearchAnswerWithBackend(query, court = "ALL", benchType = "ALL", results = null, forceFallback = false, bypassCorrection = false) {
  const normalizedQuery = (query || "").trim().toLowerCase();
  // Only cache if results is null (direct query synthesis)
  const cacheKey = results ? null : `answer:${normalizedQuery}:${court}:${benchType}:${forceFallback}:${bypassCorrection}`;
  if (cacheKey) {
    const cached = clientAnswerCache.get(cacheKey);
    if (cached) {
      return cached;
    }
  }

  const res = await fetch(`${API_BASE}/search/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: query,
      court: court,
      bench_type: benchType,
      results: results,
      force_fallback: forceFallback,
      bypass_correction: bypassCorrection
    })
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Search answer failed (HTTP ${res.status})`);
  }
  const data = await res.json();
  if (cacheKey) {
    clientAnswerCache.set(cacheKey, data);
  }
  return data;
}

/**
 * MODULE C: Smart Citator
 * GET /api/v1/citator/{case_id}
 */
export async function getCitatorCaseWithBackend(caseId) {
  const res = await fetch(`${API_BASE}/citator/${caseId}`, {
    method: 'GET',
    headers: { 'Accept': 'application/json' }
  });
  if (!res.ok) {
    throw new Error(`Citator fetch failed for ${caseId} (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * MODULE E: Legal Maxims
 * GET /api/v1/maxims
 */
export async function fetchMaximsWithBackend(q = "", category = "ALL", letter = "", page = 1, limit = 50) {
  const params = new URLSearchParams();
  if (q && q.trim()) params.append('q', q.trim());
  if (category && category !== 'ALL') params.append('category', category);
  if (letter && letter !== 'ALL') params.append('letter', letter);
  params.append('page', page);
  params.append('limit', limit);

  const res = await fetch(`${API_BASE}/maxims?${params.toString()}`, {
    method: 'GET',
    headers: { 'Accept': 'application/json' }
  });
  if (!res.ok) {
    const errorDetail = await res.text().catch(() => '');
    console.error(`[fetchMaximsWithBackend] HTTP ${res.status} error from ${res.url}:`, errorDetail);
    throw new Error(`Maxims query failed (HTTP ${res.status}): ${errorDetail}`);
  }
  return await res.json();
}

/**
 * GET /api/v1/maxims/random (Maxim of the Day)
 */
export async function fetchMaximOfTheDayWithBackend() {
  const res = await fetch(`${API_BASE}/maxims/random`, {
    method: 'GET',
    headers: { 'Accept': 'application/json' }
  });
  if (!res.ok) {
    const errorDetail = await res.text().catch(() => '');
    console.error(`[fetchMaximOfTheDayWithBackend] HTTP ${res.status} error from ${res.url}:`, errorDetail);
    throw new Error(`Maxim of the day fetch failed (HTTP ${res.status}): ${errorDetail}`);
  }
  return await res.json();
}

/**
 * POST /api/v1/maxims/explain
 */
export async function explainMaximWithBackend(maximOrId, factSituation = null, userMessage = null, history = []) {
  const payload = {
    id: maximOrId,
    maxim: maximOrId,
    fact_situation: factSituation,
    message: userMessage,
    history: (history || []).slice(-4)
  };
  const res = await fetch(`${API_BASE}/maxims/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    throw new Error(`Maxim explanation failed (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * MODULE E: Legal Maxim Chat & Situation Application
 * POST /api/v1/maxims/chat
 */
export async function chatMaximWithBackend({
  maximId = null,
  maxim = null,
  message,
  history = [],
  factSituation = null
}) {
  const payload = {
    maxim_id: maximId,
    maxim: maxim,
    message: message,
    history: (history || []).slice(-4),
    fact_situation: factSituation
  };
  const res = await fetch(`${API_BASE}/maxims/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Maxim chat failed (HTTP ${res.status})`);
  }
  return await res.json();
}


/**
 * MODULE F: Document Chat
 * POST /api/v1/doc/upload
 */
export async function uploadDocumentForChatWithBackend(input, title = "Uploaded Agreement") {
  if (input instanceof FormData) {
    const res = await fetch(`${API_BASE}/doc/upload`, {
      method: 'POST',
      body: input
    });
    if (!res.ok) {
      throw new Error(`Document upload for chat failed (HTTP ${res.status})`);
    }
    return await res.json();
  } else {
    const res = await fetch(`${API_BASE}/doc/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: typeof input === 'string' ? input : '',
        title: title
      })
    });
    if (!res.ok) {
      throw new Error(`Document upload for chat failed (HTTP ${res.status})`);
    }
    return await res.json();
  }
}

/**
 * MODULE F: Document Chat
 * POST /api/v1/doc/chat
 */
export async function chatWithDocumentWithBackend(docId, question) {
  const res = await fetch(`${API_BASE}/doc/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      doc_id: docId,
      question: question
    })
  });
  if (!res.ok) {
    throw new Error(`Document chat query failed (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * MODULE G: Case Chat
 * POST /api/v1/case-chat
 */
export async function sendCaseChatMessage({ caseId, question, messages = [] }) {
  const res = await fetch(`${API_BASE}/case-chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      question: question,
      messages: messages.map(m => ({ role: m.role, content: m.content }))
    })
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Case chat failed (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * MODULE G: Explain Selected Text
 * POST /api/v1/explain-selection
 */
export async function explainSelectedText({ selectedText, context = null, caseId = null }) {
  const res = await fetch(`${API_BASE}/explain-selection`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selected_text: selectedText,
      context: context,
      case_id: caseId
    })
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Explain selection failed (HTTP ${res.status})`);
  }
  return await res.json();
}

/**
 * MODULE G: Case Text Paragraphs
 * GET /api/v1/case-text/{case_id}
 */
export async function fetchCaseText(caseId) {
  const res = await fetch(`${API_BASE}/case-text/${encodeURIComponent(caseId)}`);
  if (!res.ok) {
    throw new Error(`Fetch case text failed (HTTP ${res.status})`);
  }
  return await res.json();
}

