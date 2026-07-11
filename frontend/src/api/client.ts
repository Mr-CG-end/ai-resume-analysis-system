import type {
  CandidateProfile,
  Education,
  ErrorDetail,
  MatchEvidence,
  MatchRequest,
  MatchResponse,
  Project,
  ResumeWarningCode,
  ResumeSnapshot,
  ScoreBreakdown,
} from './types'

const DEFAULT_API_BASE_URL = '/api/v1'

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim()
  return (configured || DEFAULT_API_BASE_URL).replace(/\/$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString)
}

function isEducation(value: unknown): value is Education {
  return (
    isRecord(value) &&
    isNullableString(value.school) &&
    isNullableString(value.degree) &&
    isNullableString(value.major) &&
    isNullableString(value.start_date) &&
    isNullableString(value.end_date)
  )
}

function isProject(value: unknown): value is Project {
  return (
    isRecord(value) &&
    isNullableString(value.name) &&
    isNullableString(value.role) &&
    isNullableString(value.description) &&
    isStringArray(value.technologies)
  )
}

function isCandidateProfile(value: unknown): value is CandidateProfile {
  return (
    isRecord(value) &&
    isNullableString(value.name) &&
    isNullableString(value.phone) &&
    isNullableString(value.email) &&
    isNullableString(value.address) &&
    isNullableString(value.job_intention) &&
    isNullableString(value.expected_salary) &&
    (value.years_of_experience === null ||
      isFiniteNumber(value.years_of_experience)) &&
    Array.isArray(value.education) &&
    value.education.every(isEducation) &&
    Array.isArray(value.projects) &&
    value.projects.every(isProject)
  )
}

const resumeWarningCodes: ReadonlySet<string> = new Set([
  'name_not_found',
  'phone_not_found',
  'email_not_found',
  'address_not_found',
  'job_intention_not_found',
  'expected_salary_not_found',
  'years_of_experience_uncertain',
  'ai_extraction_fallback',
])

function isResumeWarningCode(value: unknown): value is ResumeWarningCode {
  return isString(value) && resumeWarningCodes.has(value)
}

function isResumeSnapshot(value: unknown): value is ResumeSnapshot {
  return (
    isRecord(value) &&
    isString(value.resume_id) &&
    isRecord(value.document) &&
    isString(value.document.filename) &&
    isFiniteNumber(value.document.page_count) &&
    isFiniteNumber(value.document.character_count) &&
    isString(value.cleaned_text) &&
    isCandidateProfile(value.profile) &&
    Array.isArray(value.warnings) &&
    value.warnings.every(isResumeWarningCode) &&
    isBoolean(value.degraded) &&
    isBoolean(value.cached)
  )
}

function isScoreBreakdown(value: unknown): value is ScoreBreakdown {
  return (
    isRecord(value) &&
    isFiniteNumber(value.skill_match) &&
    isFiniteNumber(value.experience_relevance) &&
    isFiniteNumber(value.overall)
  )
}

function isMatchEvidence(value: unknown): value is MatchEvidence {
  return (
    isRecord(value) &&
    value.dimension === 'experience' &&
    isString(value.text)
  )
}

function isMatchResponse(value: unknown): value is MatchResponse {
  return (
    isRecord(value) &&
    isString(value.match_id) &&
    isString(value.resume_id) &&
    isStringArray(value.jd_keywords) &&
    isStringArray(value.matched_keywords) &&
    isStringArray(value.missing_keywords) &&
    isScoreBreakdown(value.scores) &&
    Array.isArray(value.evidence) &&
    value.evidence.every(isMatchEvidence) &&
    isString(value.summary) &&
    (value.method === 'hybrid' || value.method === 'rule_fallback') &&
    Array.isArray(value.warnings) &&
    value.warnings.every((warning) => warning === 'ai_matching_fallback') &&
    isBoolean(value.degraded) &&
    isBoolean(value.cached)
  )
}

function parseErrorDetail(value: unknown): ErrorDetail | null {
  if (!isRecord(value) || !isRecord(value.error)) {
    return null
  }

  const { code, message, request_id: requestId, details } = value.error
  if (
    typeof code !== 'string' ||
    typeof message !== 'string' ||
    typeof requestId !== 'string'
  ) {
    return null
  }

  return {
    code,
    message,
    request_id: requestId,
    details: isRecord(details) ? details : {},
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: Record<string, unknown>

  constructor(options: {
    status: number
    code: string
    message: string
    requestId?: string | null
    details?: Record<string, unknown>
  }) {
    super(options.message)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code
    this.requestId = options.requestId ?? null
    this.details = options.details ?? {}
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

async function request<T>(
  path: string,
  init: RequestInit,
  isValidPayload: (value: unknown) => value is T,
): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${apiBaseUrl()}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: '无法连接到分析服务，请检查网络后重试。',
    })
  }

  const payload = await readJson(response)
  if (!response.ok) {
    const detail = parseErrorDetail(payload)
    throw new ApiError({
      status: response.status,
      code: detail?.code ?? 'UNEXPECTED_RESPONSE',
      message: detail?.message ?? '服务返回了无法识别的错误，请稍后重试。',
      requestId:
        detail?.request_id ?? response.headers.get('X-Request-ID'),
      details: detail?.details,
    })
  }

  if (!isValidPayload(payload)) {
    throw new ApiError({
      status: response.status,
      code: 'INVALID_RESPONSE',
      message: '服务返回了无效数据，请稍后重试。',
      requestId: response.headers.get('X-Request-ID'),
    })
  }

  return payload
}

export function createResume(
  file: File,
  options: { signal?: AbortSignal } = {},
): Promise<ResumeSnapshot> {
  const body = new FormData()
  body.append('file', file)
  return request<ResumeSnapshot>(
    '/resumes',
    {
      method: 'POST',
      body,
      signal: options.signal,
    },
    isResumeSnapshot,
  )
}

export function createMatch(
  payload: MatchRequest,
  options: { signal?: AbortSignal } = {},
): Promise<MatchResponse> {
  return request<MatchResponse>(
    '/matches',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: options.signal,
    },
    isMatchResponse,
  )
}
