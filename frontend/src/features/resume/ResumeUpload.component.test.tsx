import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ResumeUpload } from './ResumeUpload'

interface DraggerBoundaryProps {
  beforeUpload?: (file: File, batch: File[]) => unknown
  onDrop?: (event: { dataTransfer: { files: File[] } }) => void
  onRemove?: () => unknown
  disabled?: boolean
  fileList?: Array<{ name: string }>
  children?: ReactNode
}

interface ButtonBoundaryProps {
  children?: ReactNode
  disabled?: boolean
  onClick?: () => void
}

vi.mock('antd', () => {
  const valid = new File(['%PDF-1.7'], 'candidate.pdf', {
    type: 'application/pdf',
  })
  const other = new File(['%PDF-1.7'], 'other.pdf', {
    type: 'application/pdf',
  })
  const Dragger = ({
    beforeUpload,
    onDrop,
    onRemove,
    disabled,
    fileList,
    children,
  }: DraggerBoundaryProps) => (
    <div aria-label="上传边界替身">
      {children}
      {fileList?.map((file) => <span key={file.name}>{file.name}</span>)}
      <button
        type="button"
        disabled={disabled}
        onClick={() => beforeUpload?.(valid, [valid])}
      >
        模拟选择 PDF
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onDrop?.({ dataTransfer: { files: [valid, other] } })}
      >
        模拟拖入多文件
      </button>
      <button type="button" disabled={disabled} onClick={() => onRemove?.()}>
        模拟删除
      </button>
    </div>
  )
  const Upload = Object.assign(() => null, {
    Dragger,
    LIST_IGNORE: 'LIST_IGNORE',
  })
  const Button = ({ children, disabled, onClick }: ButtonBoundaryProps) => (
    <button type="button" disabled={disabled} onClick={onClick}>
      {children}
    </button>
  )
  return { Button, Upload }
})

function pdf(): File {
  return new File(['%PDF-1.7'], 'selected.pdf', {
    type: 'application/pdf',
  })
}

describe('ResumeUpload 受控交互', () => {
  it('选择合法 PDF 后清除错误并上报文件', () => {
    const onFileChange = vi.fn()
    const onValidationError = vi.fn()
    render(
      <ResumeUpload
        file={null}
        parsing={false}
        onFileChange={onFileChange}
        onParse={vi.fn()}
        onValidationError={onValidationError}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '模拟选择 PDF' }))
    expect(onValidationError).toHaveBeenCalledWith(null)
    expect(onFileChange).toHaveBeenCalledWith(expect.objectContaining({ name: 'candidate.pdf' }))
  })

  it('多文件拖放只上报错误且不替换已有文件', () => {
    const onFileChange = vi.fn()
    const onValidationError = vi.fn()
    render(
      <ResumeUpload
        file={pdf()}
        parsing={false}
        onFileChange={onFileChange}
        onParse={vi.fn()}
        onValidationError={onValidationError}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '模拟拖入多文件' }))
    expect(onValidationError).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'MULTIPLE_FILES_NOT_ALLOWED' }),
    )
    expect(onFileChange).not.toHaveBeenCalled()
  })

  it('删除文件会清除错误和受控文件', () => {
    const onFileChange = vi.fn()
    const onValidationError = vi.fn()
    render(
      <ResumeUpload
        file={pdf()}
        parsing={false}
        onFileChange={onFileChange}
        onParse={vi.fn()}
        onValidationError={onValidationError}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '模拟删除' }))
    expect(onValidationError).toHaveBeenCalledWith(null)
    expect(onFileChange).toHaveBeenCalledWith(null)
  })

  it('解析期间禁用冲突操作并通过 aria-live 报告状态', () => {
    render(
      <ResumeUpload
        file={pdf()}
        parsing
        onFileChange={vi.fn()}
        onParse={vi.fn()}
        onValidationError={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: '正在解析' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '模拟选择 PDF' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('正在解析简历，请稍候')
  })

  it('合法文件只触发一次解析操作', () => {
    const onParse = vi.fn()
    render(
      <ResumeUpload
        file={pdf()}
        parsing={false}
        onFileChange={vi.fn()}
        onParse={onParse}
        onValidationError={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '解析简历' }))
    expect(onParse).toHaveBeenCalledOnce()
  })
})
