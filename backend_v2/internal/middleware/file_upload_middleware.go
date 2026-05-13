package middleware

import (
	"fmt"
	"net/http"

	"github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/background"
)

type FileUploadMiddleware struct {
	FileProcessor *background.FileProcessor
}

func (fp *FileUploadMiddleware) FileUploadSizeLimitMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		contentLength := r.ContentLength
		if contentLength <= 0 {
			http.Error(w, "Content-Length required", http.StatusBadRequest)
			return
		}

		currentSize := fp.FileProcessor.MiddlewareEstimatedSize.Load()
		maxTotalSize := fp.FileProcessor.MaxTotalSize()
		if currentSize+contentLength > maxTotalSize {
			http.Error(w, fmt.Sprintf(
				"Upload would exceed size limit. Current: %d bytes, Max: %d bytes",
				currentSize,
				maxTotalSize,
			), http.StatusServiceUnavailable)
			return
		}

		fp.FileProcessor.MiddlewareEstimatedSize.Add(contentLength)
		next.ServeHTTP(w, r)
	})
}
