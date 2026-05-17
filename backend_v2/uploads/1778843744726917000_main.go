package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/joho/godotenv"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

/*
	- SO this is will be very rough proto of the full workflow
	- [x] Create one simple POST endpoint for upload
	- [x] save file to local dir
	- [x] do a fake process step to simulate recover , and parsing
	- [x] write the data to monogodb
	- [x] return json data from db
*/

type UploadRecord struct {
	ID               primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	FileName         string             `bson:"file_name" json:"file_name"`
	StoredPath       string             `bson:"stored_path" json:"stored_path"`
	StoredSizeBytes  int64              `bson:"stored_size_bytes" json:"stored_size_bytes"`
	RecoverSimulated bool               `bson:"recover_simulated" json:"recover_simulated"`
	ParseSimulated   bool               `bson:"parse_simulated" json:"parse_simulated"`
	Status           string             `bson:"status" json:"status"`
	UploadedAt       time.Time          `bson:"uploaded_at" json:"uploaded_at"`
}

func main() {
	if err := godotenv.Load(".env"); err != nil {
		log.Println("no .env loaded, using system env")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	mongoURI := os.Getenv("MONGODB_URI")
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017"
	}

	mongoClient, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		log.Fatalf("failed to connect mongo: %v", err)
	}

	if err := mongoClient.Ping(ctx, nil); err != nil {
		log.Fatalf("failed to ping mongo: %v", err)
	}

	uploadsCollection := mongoClient.Database("vehicle_data_db").Collection("uploads_proto")

	defer func() {
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = mongoClient.Disconnect(shutdownCtx)
	}()

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
	r.Post("/mcaps/upload", uploadMCAP(uploadDir, uploadsCollection))

	log.Println("listening on :3333")
	log.Fatal(http.ListenAndServe(":3333", r))
}

func uploadMCAP(uploadDir string, collection *mongo.Collection) http.HandlerFunc {
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

		record := UploadRecord{
			FileName:         header.Filename,
			StoredPath:       storedPath,
			StoredSizeBytes:  written,
			RecoverSimulated: true,
			ParseSimulated:   true,
			Status:           "queued",
			UploadedAt:       time.Now().UTC(),
		}

		insertResult, err := collection.InsertOne(r.Context(), record)
		if err != nil {
			log.Printf("mongodb insert failed: %v", err)
			http.Error(w, "failed to write upload metadata to mongodb", http.StatusInternalServerError)
			return
		}

		insertedID, ok := insertResult.InsertedID.(primitive.ObjectID)
		if !ok {
			http.Error(w, "invalid inserted id from mongodb", http.StatusInternalServerError)
			return
		}

		var createdRecord UploadRecord
		err = collection.FindOne(r.Context(), bson.M{"_id": insertedID}).Decode(&createdRecord)
		if err != nil {
			http.Error(w, "failed to fetch created upload metadata", http.StatusInternalServerError)
			return
		}

		response := map[string]any{
			"message": "created upload record",
			"data":    createdRecord,
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(response)
	}
}
