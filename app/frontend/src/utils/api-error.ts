/**
 * Utility for handling structured API error responses, particularly the
 * 422 pre-check error returned by `/hedge-fund/run` and `/hedge-fund/backtest`
 * when required API keys are missing.
 */

import { toast } from 'sonner';

// -----------------------------------------------------------------------
// Types matching the backend `ApiKeyPreCheckError` schema
// -----------------------------------------------------------------------

export interface MissingKeyDetail {
  key_name: string;
  provider: string;
  required_by: string[];
  reason: string;
}

export interface ApiKeyPreCheckErrorBody {
  message: string;
  missing_keys: MissingKeyDetail[];
}

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

/**
 * Try to parse a Response body as JSON. Returns `null` on failure.
 *
 * The response body stream can only be read once. Since callers typically
 * throw immediately after calling this helper, consuming the stream here
 * is acceptable.
 */
async function tryParseJson(response: Response): Promise<any | null> {
  try {
    // FastAPI wraps the detail in {"detail": {...}} for HTTPException
    const body = await response.json();
    // If the backend used HTTPException(status_code=422, detail=...),
    // the JSON body will be `{"detail": <our structured dict>}`.
    if (body?.detail) {
      return body.detail;
    }
    return body;
  } catch {
    return null;
  }
}

/**
 * Format a `MissingKeyDetail` into a compact, readable string.
 */
function formatKeyLine(detail: MissingKeyDetail): string {
  const agents = detail.required_by.slice(0, 3).join(', ');
  const more = detail.required_by.length > 3 ? ` +${detail.required_by.length - 3} more` : '';
  return `${detail.key_name} (${detail.provider}) — needed by ${agents}${more}`;
}

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

/**
 * Inspect a failed `fetch` Response and, if it is a 422 pre-check error,
 * show a descriptive Sonner toast listing every missing API key.
 *
 * For non-422 errors, a generic error toast is shown.
 *
 * This function is intended to be called **before** throwing the error so
 * the user gets immediate visual feedback.
 *
 * @returns `true` if the response was recognised as a pre-check error.
 */
export async function handleApiPreCheckError(response: Response): Promise<boolean> {
  if (response.status !== 422) {
    return false;
  }

  const parsed = await tryParseJson(response);
  if (!parsed || !Array.isArray(parsed.missing_keys)) {
    // 422 but not our structured format — show a generic message
    toast.error('Request validation failed. Please check your configuration.', {
      duration: 6000,
    });
    return false;
  }

  const errorBody = parsed as ApiKeyPreCheckErrorBody;

  // Build a multi-line description
  const keyLines = errorBody.missing_keys.map(formatKeyLine);
  const description = keyLines.join('\n');

  toast.error(errorBody.message || 'Missing required API keys', {
    description,
    duration: 10000, // keep visible longer so user can read the details
  });

  return true;
}
