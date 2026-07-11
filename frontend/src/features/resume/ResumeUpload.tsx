import { Button, Upload } from 'antd'
import type { UploadFile, UploadProps } from 'antd'
import styles from './ResumeUpload.module.css'
import {
  validateResumeFiles,
  type UploadValidationError,
} from './resumeUpload'

export interface ResumeUploadProps {
  file: File | null
  parsing: boolean
  disabled?: boolean
  onFileChange: (file: File | null) => void
  onParse: () => void
  onValidationError: (error: UploadValidationError | null) => void
}

const Dragger = Upload.Dragger

export function ResumeUpload({
  file,
  parsing,
  disabled = false,
  onFileChange,
  onParse,
  onValidationError,
}: ResumeUploadProps) {
  const unavailable = disabled || parsing
  const fileList: UploadFile[] = file
    ? [
        {
          uid: `${file.name}-${file.size}-${file.lastModified}`,
          name: file.name,
          size: file.size,
          type: file.type,
          status: 'done',
        },
      ]
    : []

  const selectFiles = (files: readonly File[]) => {
    const error = validateResumeFiles(files)
    if (error) {
      onValidationError(error)
      return false
    }

    onValidationError(null)
    onFileChange(files[0])
    return true
  }

  const beforeUpload: UploadProps['beforeUpload'] = (_file, fileBatch) => {
    selectFiles(fileBatch)
    return Upload.LIST_IGNORE
  }

  const handleDrop: UploadProps['onDrop'] = (event) => {
    if (event.dataTransfer.files.length > 1) {
      selectFiles(Array.from(event.dataTransfer.files))
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="resume-upload-title">
      <div className={styles.heading}>
        <div>
          <p className={styles.kicker}>第一步</p>
          <h2 id="resume-upload-title">上传 PDF 简历</h2>
        </div>
        <p className={styles.help}>仅支持单个文本型 PDF，大小不超过 10 MiB</p>
      </div>

      <Dragger
        accept=".pdf,application/pdf"
        beforeUpload={beforeUpload}
        disabled={unavailable}
        fileList={fileList}
        maxCount={1}
        multiple={false}
        onDrop={handleDrop}
        onRemove={() => {
          onValidationError(null)
          onFileChange(null)
          return true
        }}
        openFileDialogOnClick={!unavailable}
      >
        <p className="ant-upload-text">点击或拖放 PDF 到这里</p>
        <p className="ant-upload-hint">文件只用于本次分析，不会作为历史记录保存</p>
      </Dragger>

      <div className={styles.actions}>
        <Button
          type="primary"
          htmlType="button"
          disabled={!file || unavailable}
          loading={parsing}
          onClick={onParse}
        >
          {parsing ? '正在解析' : '解析简历'}
        </Button>
        <span className={styles.status} role="status" aria-live="polite">
          {parsing ? '正在解析简历，请稍候' : ''}
        </span>
      </div>
    </section>
  )
}
