import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { ApiError } from './api/client'
import type { ResumeUploadProps } from './features/resume/ResumeUpload'
import { AppProviders } from './app/AppProviders'
import { matchResponseFixture, resumeSnapshotFixture } from './test/fixtures'

type CreateResume = typeof import('./api/client').createResume
type CreateMatch = typeof import('./api/client').createMatch

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason: unknown) => void
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const apiMocks = vi.hoisted(() => ({
  createResume: vi.fn<CreateResume>(),
  createMatch: vi.fn<CreateMatch>(),
}))

vi.mock('./api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/client')>()
  return { ...actual, ...apiMocks }
})

vi.mock('./features/resume/ResumeUpload', () => ({
  ResumeUpload: ({
    file,
    parsing,
    disabled,
    onFileChange,
    onParse,
  }: ResumeUploadProps) => (
    <section aria-label="测试上传边界">
      <button
        type="button"
        onClick={() =>
          onFileChange(
            new File(['%PDF-1.7'], 'candidate.pdf', { type: 'application/pdf' }),
          )
        }
        disabled={disabled || parsing}
      >
        选择测试 PDF
      </button>
      <button type="button" onClick={onParse} disabled={!file || disabled || parsing}>
        {parsing ? '正在解析' : '解析简历'}
      </button>
    </section>
  ),
}))

function renderApp(): void {
  render(
    <AppProviders>
      <App />
    </AppProviders>,
  )
}

beforeEach(() => {
  apiMocks.createResume.mockReset()
  apiMocks.createMatch.mockReset()
})

describe('完整简历分析流程', () => {
  it('从上传、档案确认进入岗位匹配并展示可解释结果', async () => {
    apiMocks.createResume.mockResolvedValue(resumeSnapshotFixture)
    apiMocks.createMatch.mockResolvedValue(matchResponseFixture)
    renderApp()

    expect(screen.getByRole('heading', { level: 1, name: '智能简历分析系统' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '候选人档案' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '选择测试 PDF' }))
    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))

    expect(await screen.findByRole('heading', { name: '候选人档案' })).toBeVisible()
    expect(screen.getByText('张三')).toBeVisible()
    expect(apiMocks.createResume).toHaveBeenCalledOnce()

    fireEvent.change(screen.getByRole('textbox', { name: '岗位描述' }), {
      target: { value: '  招聘 Python 后端工程师，需要 Redis 和 API 项目经验。\n' },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始匹配' }))

    expect(await screen.findByRole('heading', { name: '候选人与岗位的契合度' })).toBeVisible()
    expect(screen.getByLabelText('综合匹配分数 62 分')).toBeVisible()
    expect(screen.getAllByText('负责简历解析与匹配服务')).toHaveLength(2)
    expect(apiMocks.createMatch).toHaveBeenCalledWith(
      {
        resume_snapshot: resumeSnapshotFixture,
        job_description: '招聘 Python 后端工程师，需要 Redis 和 API 项目经验。',
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('解析期间允许取消，并忽略取消后的迟到失败', async () => {
    const pending = createDeferred<typeof resumeSnapshotFixture>()
    let requestSignal: AbortSignal | undefined
    apiMocks.createResume.mockImplementation((_file, options = {}) => {
      requestSignal = options.signal
      return pending.promise
    })
    renderApp()

    fireEvent.click(screen.getByRole('button', { name: '选择测试 PDF' }))
    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))
    expect(requestSignal?.aborted).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: '取消并重新分析' }))
    expect(requestSignal?.aborted).toBe(true)
    expect(screen.getByRole('button', { name: '解析简历' })).toBeDisabled()

    await act(async () => {
      pending.reject(new Error('迟到的解析失败'))
      await pending.promise.catch(() => undefined)
    })
    expect(screen.queryByText('分析未完成')).not.toBeInTheDocument()
  })

  it('匹配期间允许取消，并清空本次分析状态', async () => {
    const pending = createDeferred<typeof matchResponseFixture>()
    let requestSignal: AbortSignal | undefined
    apiMocks.createResume.mockResolvedValue(resumeSnapshotFixture)
    apiMocks.createMatch.mockImplementation((_payload, options = {}) => {
      requestSignal = options.signal
      return pending.promise
    })
    renderApp()

    fireEvent.click(screen.getByRole('button', { name: '选择测试 PDF' }))
    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))
    await screen.findByRole('heading', { name: '候选人档案' })
    fireEvent.change(screen.getByRole('textbox', { name: '岗位描述' }), {
      target: { value: '招聘 Python 后端工程师，需要 Redis 和 API 项目经验。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始匹配' }))

    fireEvent.click(screen.getByRole('button', { name: '取消并重新分析' }))
    expect(requestSignal?.aborted).toBe(true)
    expect(screen.queryByRole('heading', { name: '候选人档案' })).not.toBeInTheDocument()

    await act(async () => {
      pending.reject(new Error('迟到的匹配失败'))
      await pending.promise.catch(() => undefined)
    })
    expect(screen.queryByText('分析未完成')).not.toBeInTheDocument()
  })

  it('展示可操作的服务错误和请求编号，并允许关闭后重试', async () => {
    apiMocks.createResume
      .mockRejectedValueOnce(
        new ApiError({
          status: 422,
          code: 'PDF_NO_EXTRACTABLE_TEXT',
          message: 'PDF 中未检测到可解析文本。',
          requestId: 'req-ui-test',
        }),
      )
      .mockResolvedValueOnce(resumeSnapshotFixture)
    renderApp()

    fireEvent.click(screen.getByRole('button', { name: '选择测试 PDF' }))
    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))

    expect(await screen.findByText('无法读取这份简历')).toBeVisible()
    expect(screen.getByText('请求编号：req-ui-test')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: /关\s*闭/ }))
    expect(screen.queryByText('无法读取这份简历')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))
    expect(await screen.findByRole('heading', { name: '候选人档案' })).toBeVisible()
    expect(apiMocks.createResume).toHaveBeenCalledTimes(2)
  })

  it('匹配失败后保留档案和岗位描述以便重试', async () => {
    const jobDescription = '招聘 Python 后端工程师，需要 Redis 和 API 项目经验。'
    apiMocks.createResume.mockResolvedValue(resumeSnapshotFixture)
    apiMocks.createMatch
      .mockRejectedValueOnce(
        new ApiError({
          status: 0,
          code: 'NETWORK_ERROR',
          message: '无法连接服务。',
        }),
      )
      .mockResolvedValueOnce(matchResponseFixture)
    renderApp()

    fireEvent.click(screen.getByRole('button', { name: '选择测试 PDF' }))
    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))
    await screen.findByRole('heading', { name: '候选人档案' })
    fireEvent.change(screen.getByRole('textbox', { name: '岗位描述' }), {
      target: { value: jobDescription },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始匹配' }))

    expect(await screen.findByText('无法连接分析服务')).toBeVisible()
    expect(screen.getByRole('textbox', { name: '岗位描述' })).toHaveValue(jobDescription)
    fireEvent.click(screen.getByRole('button', { name: '开始匹配' }))
    expect(await screen.findByRole('heading', { name: '候选人与岗位的契合度' })).toBeVisible()
    expect(apiMocks.createMatch).toHaveBeenCalledTimes(2)
  })

  it('重新分析会清空文件、档案、岗位描述和匹配结果', async () => {
    apiMocks.createResume.mockResolvedValue(resumeSnapshotFixture)
    apiMocks.createMatch.mockResolvedValue(matchResponseFixture)
    renderApp()

    fireEvent.click(screen.getByRole('button', { name: '选择测试 PDF' }))
    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))
    await screen.findByRole('heading', { name: '候选人档案' })
    fireEvent.change(screen.getByRole('textbox', { name: '岗位描述' }), {
      target: { value: '招聘 Python 后端工程师，需要 Redis 和 API 项目经验。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始匹配' }))
    await screen.findByRole('heading', { name: '候选人与岗位的契合度' })

    const resetButtons = screen.getAllByRole('button', { name: '重新分析' })
    fireEvent.click(resetButtons.at(-1)!)

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: '候选人档案' })).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('textbox', { name: '岗位描述' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '解析简历' })).toBeDisabled()
  })
})
