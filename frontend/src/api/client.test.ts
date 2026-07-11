import { afterEach, describe, expect, it, vi } from 'vitest'
import { matchResponseFixture, resumeSnapshotFixture } from '../test/fixtures'
import { ApiError, createMatch, createResume } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API 客户端', () => {
  it('使用 FormData 上传单个文件且不覆盖 Content-Type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(resumeSnapshotFixture), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['%PDF-1.7'], 'resume.pdf', {
      type: 'application/pdf',
    })

    await expect(createResume(file)).resolves.toEqual(resumeSnapshotFixture)

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/resumes')
    expect(init.method).toBe('POST')
    expect(init.headers).toBeUndefined()
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('file')).toBe(file)
  })

  it('发送完整快照和岗位描述', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(matchResponseFixture), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const payload = {
      resume_snapshot: resumeSnapshotFixture,
      job_description: '招聘 Python 后端工程师，需要 Redis 项目经验。',
    }

    await expect(createMatch(payload)).resolves.toEqual(matchResponseFixture)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/matches')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(String(init.body))).toEqual(payload)
  })

  it('将统一错误响应转换为 ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'PDF_NO_EXTRACTABLE_TEXT',
              message: 'PDF 中未检测到可解析文本。',
              request_id: 'req-test',
              details: { page_count: 1 },
            },
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    const promise = createResume(
      new File(['%PDF-1.7'], 'resume.pdf', { type: 'application/pdf' }),
    )
    await expect(promise).rejects.toMatchObject({
      name: 'ApiError',
      status: 422,
      code: 'PDF_NO_EXTRACTABLE_TEXT',
      requestId: 'req-test',
      details: { page_count: 1 },
    })
  })

  it('为网络故障提供稳定错误代码', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    const promise = createMatch({
      resume_snapshot: resumeSnapshotFixture,
      job_description: '招聘 Python 后端工程师，需要 Redis 项目经验。',
    })
    await expect(promise).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        status: 0,
        code: 'NETWORK_ERROR',
        requestId: null,
      }),
    )
  })

  it('拒绝缺少核心嵌套字段的简历成功响应', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ...resumeSnapshotFixture,
            profile: { ...resumeSnapshotFixture.profile, projects: null },
          }),
          {
            status: 201,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-ID': 'req-invalid-resume',
            },
          },
        ),
      ),
    )

    await expect(
      createResume(
        new File(['%PDF-1.7'], 'resume.pdf', { type: 'application/pdf' }),
      ),
    ).rejects.toMatchObject({
      status: 201,
      code: 'INVALID_RESPONSE',
      requestId: 'req-invalid-resume',
    })
  })

  it('拒绝字段类型错误的匹配成功响应', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ...matchResponseFixture,
            scores: { ...matchResponseFixture.scores, overall: '62' },
          }),
          { status: 201, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    await expect(
      createMatch({
        resume_snapshot: resumeSnapshotFixture,
        job_description: '招聘 Python 后端工程师，需要 Redis 项目经验。',
      }),
    ).rejects.toMatchObject({
      status: 201,
      code: 'INVALID_RESPONSE',
    })
  })

  it('保留请求取消异常供页面忽略迟到响应', async () => {
    const abortError = new DOMException('aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))

    await expect(
      createResume(
        new File(['%PDF-1.7'], 'resume.pdf', { type: 'application/pdf' }),
      ),
    ).rejects.toBe(abortError)
  })
})
