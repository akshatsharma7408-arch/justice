/**
 * JUSTICE Legal AI Workspace — Backend-Connected AI & Statutory Engine Client
 * All AI operations strictly invoke the FastAPI backend at http://localhost:8000.
 * Zero client-side generative language calls; zero API key exposure in browser bundle.
 * Enforced model: gemini-3.8-flash (orchestrated via backend google-genai SDK).
 */

export const BACKEND_URL = "http://localhost:8000";
export const API_BASE = `${BACKEND_URL}/api/v1`;

export const geminiConfig = {
  model: "gemini-3.8-flash",
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
 * MODULE B: Universal Search
 * POST /api/v1/search
 */
export async function searchPrecedentsWithBackend(query, court = "ALL", benchType = "ALL", enableHyde = true, limit = 5) {
  const res = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: query,
      court: court,
      bench_type: benchType,
      enable_hyde: enableHyde,
      limit: limit
    })
  });
  if (!res.ok) {
    throw new Error(`Universal search failed (HTTP ${res.status})`);
  }
  return await res.json();
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
