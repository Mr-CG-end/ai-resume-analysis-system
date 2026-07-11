export const MAX_PDF_BYTES = 10 * 1024 * 1024

export type UploadValidationCode =
  | 'FILE_REQUIRED'
  | 'MULTIPLE_FILES_NOT_ALLOWED'
  | 'UNSUPPORTED_MEDIA_TYPE'
  | 'PDF_TOO_LARGE'

export interface UploadValidationError {
  code: UploadValidationCode
  message: string
}

export function validateResumeFiles(
  files: readonly File[],
): UploadValidationError | null {
  if (files.length === 0) {
    return { code: 'FILE_REQUIRED', message: '请选择一份 PDF 简历。' }
  }

  if (files.length > 1) {
    return {
      code: 'MULTIPLE_FILES_NOT_ALLOWED',
      message: '每次只能上传一份 PDF 简历。',
    }
  }

  const [file] = files
  if (
    !file.name.trim().toLowerCase().endsWith('.pdf') ||
    file.type !== 'application/pdf'
  ) {
    return {
      code: 'UNSUPPORTED_MEDIA_TYPE',
      message: '文件格式不受支持，请选择 PDF 文件。',
    }
  }

  if (file.size > MAX_PDF_BYTES) {
    return {
      code: 'PDF_TOO_LARGE',
      message: 'PDF 文件不能超过 10 MiB。',
    }
  }

  return null
}
