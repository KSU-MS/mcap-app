package http

import (
	"net/http"

	"github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/background"
	"github.com/go-chi/chi/v5"
)

type uploadHandler struct {
	fileProcessor *background.FileProcessor
}

func NewUploadHandler(r chi.Router, fileProcessor *background.FileProcessor) {
	handler := &uploadHandler{fileProcessor: fileProcessor}
	r.Route("/uploads", func(r chi.Router) {
		r.Get("/limits", handler.GetUploadLimits)
	})
}

func (handler *uploadHandler) GetUploadLimits(w http.ResponseWriter, r *http.Request) {
	currentFileSize := handler.fileProcessor.TotalSize.Load()
	maxFileSize := handler.fileProcessor.MaxTotalSize()

	writeJSON(w, http.StatusOK, map[string]any{
		"message": nil,
		"data": map[string]any{
			"current_file_size":   currentFileSize,
			"max_file_size":       maxFileSize,
			"available_file_size": maxFileSize - currentFileSize,
		},
	})
}
