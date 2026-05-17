package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

func main() {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	uploadDir := "./uploads"
	if err := os.MkdirAll(uploadDir, 0o755); err != nil {
		log.Fatalf("failed to create upload dir: %v", err)
	}

	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("backend_v2 up"))
	})
	r.Post("/mcaps/upload", uploadMCAP(uploadDir))

	log.Println("listening on :3333")
	log.Fatal(http.ListenAndServe(":3333", r))
}

func uploadMCAP(uploadDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseMultipartForm(32 << 20); err != nil {
			http.Error(w, "invalid multipart form", http.StatusBadRequest)
			return
		}
		defer r.MultipartForm.RemoveAll()

		file, header, err := r.FormFile("file")
		if err != nil {
			http.Error(w, "file field is required", http.StatusBadRequest)
			return
		}
		defer file.Close()

		storedName := fmt.Sprintf("%d_%s", time.Now().UnixNano(), filepath.Base(header.Filename))
		storedPath := filepath.Join(uploadDir, storedName)

		dst, err := os.Create(storedPath)
		if err != nil {
			http.Error(w, "failed to create destination file", http.StatusInternalServerError)
			return
		}
		defer dst.Close()

		written, err := dst.ReadFrom(file)
		if err != nil {
			_ = os.Remove(storedPath)
			http.Error(w, "failed to save uploaded file", http.StatusInternalServerError)
			return
		}

		response := map[string]any{
			"message": "created fake processing job",
			"data": map[string]any{
				"file_name":          header.Filename,
				"stored_path":        storedPath,
				"stored_size_bytes":  written,
				"recover_simulated":  true,
				"parse_simulated":    true,
				"mongodb_write_dummy": "not implemented yet",
			},
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(response)
	}
}
