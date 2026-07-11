import type {
  ErrorDetail,
  MatchRequest,
  MatchResponse,
  ResumeSnapshot,
} from './types'

const DEFAULT_API_BASE_URL = '/api/v1'

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim()
  return (configured || DEFAULT_API_BASE_URL).replace(/\/$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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

async function request<T>(path: string, init: RequestInit): Promise<T> {
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

  if (payload === null) {
    throw new ApiError({
      status: response.status,
      code: 'INVALID_RESPONSE',
      message: '服务返回了无效数据，请稍后重试。',
      requestId: response.headers.get('X-Request-ID'),
    })
  }

  return payload as T
}

export function createResume(
  file: File,
  options: { signal?: AbortSignal } = {},
): Promise<ResumeSnapshot> {
  const body = new FormData()
  body.append('file', file)
  return request<ResumeSnapshot>('/resumes', {
    method: 'POST',
    body,
    signal: options.signal,
  })
}

export function createMatch(
  payload: MatchRequest,
  options: { signal?: AbortSignal } = {},
): Promise<MatchResponse> {
  return request<MatchResponse>('/matches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: options.signal,
  })
}
