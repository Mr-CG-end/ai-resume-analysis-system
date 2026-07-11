import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { JobMatchForm } from './JobMatchForm'

const validDescription = '招聘 Python 后端工程师，需要 Redis 与 API 项目经验。'

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverMock)
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

afterEach(cleanup)

function renderForm(
  overrides: Partial<React.ComponentProps<typeof JobMatchForm>> = {},
) {
  const props: React.ComponentProps<typeof JobMatchForm> = {
    jobDescription: validDescription,
    onJobDescriptionChange: vi.fn(),
    onSubmit: vi.fn(),
    onReset: vi.fn(),
    hasSnapshot: true,
    ...overrides,
  }
  render(<JobMatchForm {...props} />)
  return props
}

describe('JobMatchForm', () => {
  it.each([
    ['', '岗位描述至少需要 20 个字符'],
    ['x'.repeat(19), '岗位描述至少需要 20 个字符'],
    [`  ${'x'.repeat(19)}  `, '岗位描述至少需要 20 个字符'],
    ['x'.repeat(10_001), '岗位描述不能超过 10,000 个字符'],
  ])('拒绝无效 JD 边界', (jobDescription, message) => {
    const props = renderForm({ jobDescription })
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('button', { name: '开始匹配' })).toBeDisabled()
    fireEvent.submit(screen.getByRole('button', { name: '开始匹配' }).closest('form')!)
    expect(props.onSubmit).not.toHaveBeenCalled()
  })

  it.each(['x'.repeat(20), `  ${'x'.repeat(20)}  `, 'x'.repeat(10_000)])(
    '允许有效 JD 边界提交',
    (jobDescription) => {
      const props = renderForm({ jobDescription })
      fireEvent.click(screen.getByRole('button', { name: '开始匹配' }))
      expect(props.onSubmit).toHaveBeenCalledTimes(1)
    },
  )

  it('受控更新岗位描述并关联可见标签', () => {
    const props = renderForm()
    fireEvent.change(screen.getByRole('textbox', { name: '岗位描述' }), {
      target: { value: '新的岗位描述' },
    })
    expect(props.onJobDescriptionChange).toHaveBeenCalledWith('新的岗位描述')
  })

  it('无快照或禁用时不允许提交', () => {
    const { rerender } = render(
      <JobMatchForm
        jobDescription={validDescription}
        onJobDescriptionChange={vi.fn()}
        onSubmit={vi.fn()}
        onReset={vi.fn()}
        hasSnapshot={false}
      />,
    )
    expect(screen.getByRole('button', { name: '开始匹配' })).toBeDisabled()
    expect(screen.getByText('请先解析简历，再进行岗位匹配。')).toBeInTheDocument()

    rerender(
      <JobMatchForm
        jobDescription={validDescription}
        onJobDescriptionChange={vi.fn()}
        onSubmit={vi.fn()}
        onReset={vi.fn()}
        hasSnapshot
        disabled
      />,
    )
    expect(screen.getByRole('button', { name: '开始匹配' })).toBeDisabled()
  })

  it('提交中显示可感知状态并阻止重复操作', () => {
    const props = renderForm({ submitting: true })
    expect(screen.getByRole('button', { name: '正在匹配…' })).toBeDisabled()
    expect(screen.getByText('正在分析岗位与候选人的匹配度。')).toHaveAttribute(
      'aria-live',
      'polite',
    )
    expect(screen.getByRole('button', { name: '重新分析' })).toBeDisabled()
    expect(props.onSubmit).not.toHaveBeenCalled()
  })

  it('触发重新分析', () => {
    const props = renderForm()
    fireEvent.click(screen.getByRole('button', { name: '重新分析' }))
    expect(props.onReset).toHaveBeenCalledTimes(1)
  })
})
