from __future__ import annotations

from collections.abc import Mapping


class DomainError(Exception):
    """Expected business failure that can be safely mapped at the API boundary."""

    code = "DOMAIN_ERROR"
    message = "请求无法处理。"
    status_code = 400

    def __init__(
        self,
        *,
        code: str | None = None,
        message: str | None = None,
        status_code: int | None = None,
        details: Mapping[str, int] | None = None,
    ) -> None:
        self.code = code or type(self).code
        self.message = message or type(self).message
        self.status_code = status_code or type(self).status_code
        self.details = dict(details or {})
        super().__init__(self.message)


class PdfProcessingError(DomainError):
    """Base class for deterministic PDF validation and parsing failures."""


class PdfTooLargeError(PdfProcessingError):
    code = "PDF_TOO_LARGE"
    message = "PDF 文件大小超过限制。"
    status_code = 413


class UnsupportedMediaTypeError(PdfProcessingError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    message = "仅支持有效的 PDF 文件。"
    status_code = 415


class PdfPageLimitExceededError(PdfProcessingError):
    code = "PDF_PAGE_LIMIT_EXCEEDED"
    message = "PDF 页数超过限制。"
    status_code = 422


class PdfEncryptedError(PdfProcessingError):
    code = "PDF_ENCRYPTED"
    message = "PDF 已加密，无法解析。"
    status_code = 422


class PdfCorruptedError(PdfProcessingError):
    code = "PDF_CORRUPTED"
    message = "PDF 文件已损坏或结构无效。"
    status_code = 422


class PdfNoExtractableTextError(PdfProcessingError):
    code = "PDF_NO_EXTRACTABLE_TEXT"
    message = "PDF 中未检测到可解析文本，请上传文本型 PDF。"
    status_code = 422


class PdfTextTooLongError(PdfProcessingError):
    code = "PDF_TEXT_TOO_LONG"
    message = "PDF 可解析文本超过长度限制。"
    status_code = 422
