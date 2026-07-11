import { describe, expect, it } from 'vitest'
import { MAX_PDF_BYTES, validateResumeFiles } from './resumeValidation'

function pdf(name = 'resume.pdf', size = 100): File {
  return new File([new Uint8Array(size)], name, { type: 'application/pdf' })
}

describe('validateResumeFiles', () => {
  it('accepts a PDF with an uppercase extension at the size boundary', () => {
    const file = new File([new Uint8Array(MAX_PDF_BYTES)], 'resume.PDF', {
      type: 'application/pdf',
    })
    expect(validateResumeFiles([file])).toBeNull()
  })

  it.each([
    [[], 'FILE_REQUIRED'],
    [[pdf(), pdf('other.pdf')], 'MULTIPLE_FILES_NOT_ALLOWED'],
    [
      [new File(['text'], 'resume.txt', { type: 'application/pdf' })],
      'UNSUPPORTED_MEDIA_TYPE',
    ],
    [[new File(['pdf'], 'resume.pdf', { type: '' })], 'UNSUPPORTED_MEDIA_TYPE'],
    [
      [new File(['pdf'], 'resume.pdf', { type: 'text/plain' })],
      'UNSUPPORTED_MEDIA_TYPE',
    ],
  ] as const)('rejects invalid selection %#', (files, code) => {
    expect(validateResumeFiles(files)?.code).toBe(code)
  })

  it('rejects a PDF over 10 MiB', () => {
    const file = new File([new Uint8Array(MAX_PDF_BYTES + 1)], 'large.pdf', {
      type: 'application/pdf',
    })
    expect(validateResumeFiles([file])?.code).toBe('PDF_TOO_LARGE')
  })
})
