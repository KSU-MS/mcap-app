package http

import (
	"fmt"
	"net/http"

	"github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/background"
	appmiddleware "github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/middleware"
	"github.com/go-chi/chi/v5"
)

type mcapHandler struct {
	fileProcessor *background.FileProcessor
}

func NewMcapHandler(
	r chi.Router,
	fileProcessor *background.FileProcessor,
	fileUploadMiddleware *appmiddleware.FileUploadMiddleware,
) {
	handler := &mcapHandler{fileProcessor: fileProcessor}

	r.Route("/mcaps", func(r chi.Router) {
		r.With(fileUploadMiddleware.FileUploadSizeLimitMiddleware).Post("/upload", handler.UploadMcap)
		r.With(fileUploadMiddleware.FileUploadSizeLimitMiddleware).Post("/bulk_upload", handler.BulkUploadMcaps)
		r.Get("/status/{job_id}", HandlerFunc(handler.CheckFileStatus).ServeHTTP)
	})
}

func (h *mcapHandler) UploadMcap(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	defer r.MultipartForm.RemoveAll()

	files := r.MultipartForm.File["file"]
	if len(files) == 0 {
		http.Error(w, "file field is required", http.StatusBadRequest)
		return
	}

	recoverJob, err := background.NewRecoverMCAPJob()
	if err != nil {
		http.Error(w, fmt.Sprintf("failed to create recover job: %v", err), http.StatusInternalServerError)
		return
	}

	job, err := h.fileProcessor.EnqueueFileUpload(files[0], recoverJob)
	if err != nil {
		http.Error(w, fmt.Sprintf("failed to queue file: %v", err), http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"message": "created file processing job",
		"data":    []string{job.ID},
	})
}

func (h *mcapHandler) BulkUploadMcaps(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	defer r.MultipartForm.RemoveAll()

	files := r.MultipartForm.File["files"]
	if len(files) == 0 {
		http.Error(w, "files field is required", http.StatusBadRequest)
		return
	}

	recoverJob, err := background.NewRecoverMCAPJob()
	if err != nil {
		http.Error(w, fmt.Sprintf("failed to create recover job: %v", err), http.StatusInternalServerError)
		return
	}

	jobIDs := make([]string, 0, len(files))
	for _, fileHeader := range files {
		job, enqueueErr := h.fileProcessor.EnqueueFileUpload(fileHeader, recoverJob)
		if enqueueErr != nil {
			continue
		}
		jobIDs = append(jobIDs, job.ID)
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"message": "created file processing jobs",
		"data":    jobIDs,
	})
}

func (h *mcapHandler) CheckFileStatus(w http.ResponseWriter, r *http.Request) *HandlerError {
	jobID := chi.URLParam(r, "job_id")
	if jobID == "" {
		return NewHandlerError("job_id is required", http.StatusBadRequest)
	}

	job, ok := h.fileProcessor.GetJob(jobID)
	if !ok {
		return NewHandlerError("job not found", http.StatusNotFound)
	}

	errorMessage := ""
	if job.Err != nil {
		errorMessage = job.Err.Error()
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"message": nil,
		"data": map[string]any{
			"job_id":     job.ID,
			"status":     job.Status,
			"file_name":  job.Filename,
			"file_path":  job.FilePath,
			"updated_at": job.UpdatedAt,
			"error":      errorMessage,
			"created_at": job.CreatedAt,
		},
	})

	return nil
}
