package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/background"
	deliveryhttp "github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/delivery/http"
	appmiddleware "github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/middleware"
	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"
	"github.com/joho/godotenv"
)

func main() {
	_ = godotenv.Load(".env")

	uploadDir := getEnv("UPLOAD_DIR", "backend_v2/data/uploads")
	uploadDirAbs, err := filepath.Abs(uploadDir)
	if err != nil {
		log.Fatalf("failed to resolve UPLOAD_DIR: %v", err)
	}
	uploadDir = uploadDirAbs
	_ = os.Setenv("UPLOAD_DIR", uploadDir)
	queueSize := 200
	workerCount := 4
	maxUploadBytes := int64(10 * 1024 * 1024 * 1024)

	if _, err := background.EnsureLocalArtifactDirs(); err != nil {
		log.Fatalf("failed to initialize local artifact dirs: %v", err)
	}

	processor, err := background.NewFileProcessorWithWorkersAndMaxSize(
		uploadDir,
		queueSize,
		workerCount,
		maxUploadBytes,
	)
	if err != nil {
		log.Fatalf("failed to initialize file processor: %v", err)
	}
	processor.Start(context.Background())

	r := chi.NewRouter()
	r.Use(chimiddleware.Logger)

	uploadMiddleware := &appmiddleware.FileUploadMiddleware{FileProcessor: processor}

	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("backend_v2 up"))
	})

	deliveryhttp.NewUploadHandler(r, processor)
	deliveryhttp.NewMcapHandler(r, processor, uploadMiddleware)

	port := getEnv("PORT", "3000")
	log.Printf("backend_v2 listening on :%s", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		log.Fatal(err)
	}
}

func getEnv(key, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}
