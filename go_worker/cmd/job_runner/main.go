package main

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type config struct {
	DatabaseURL      string
	MediaRoot        string
	MediaURL         string
	McapLogsDir      string
	McapRecoverCmd   string
	FanoutCommand    string
	ExportCommand    string
	ExportWorkers    int
	PrecomputeIngest bool
	PollInterval     time.Duration
	JobTypes         []string
	ShutdownTimeout  time.Duration
	RecoverTimeout   time.Duration
	FanoutTimeout    time.Duration
}

type backgroundJob struct {
	ID          string
	JobType     string
	Payload     map[string]any
	Attempts    int
	MaxAttempts int
}

func main() {
	cfg, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}

	ctx := context.Background()
	db, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("failed to connect to postgres: %v", err)
	}
	defer db.Close()

	log.Printf("job runner started (types=%v, poll=%s)", cfg.JobTypes, cfg.PollInterval)

	for {
		job, claimErr := claimNextJob(ctx, db, cfg.JobTypes)
		if claimErr != nil {
			log.Printf("claim error: %v", claimErr)
			time.Sleep(cfg.PollInterval)
			continue
		}
		if job == nil {
			time.Sleep(cfg.PollInterval)
			continue
		}

		log.Printf("processing job id=%s type=%s attempt=%d/%d", job.ID, job.JobType, job.Attempts, job.MaxAttempts)
		result, processErr := processJob(ctx, db, cfg, *job)
		if processErr != nil {
			log.Printf("job failed id=%s: %v", job.ID, processErr)
			if markErr := markJobFailed(ctx, db, *job, processErr); markErr != nil {
				log.Printf("failed to mark job failure id=%s: %v", job.ID, markErr)
			}
			continue
		}

		if markErr := markJobCompleted(ctx, db, job.ID, result); markErr != nil {
			log.Printf("failed to mark job completed id=%s: %v", job.ID, markErr)
			continue
		}
		log.Printf("completed job id=%s", job.ID)
	}
}

func loadConfig() (config, error) {
	cfg := config{
		DatabaseURL:      strings.TrimSpace(os.Getenv("DATABASE_URL")),
		MediaRoot:        envOrDefault("MEDIA_ROOT", "/Users/pettruskonnoth/Documents"),
		MediaURL:         envOrDefault("MEDIA_URL", "/media/"),
		McapLogsDir:      strings.TrimSpace(os.Getenv("MCAP_LOGS_DIR")),
		McapRecoverCmd:   envOrDefault("MCAP_RECOVER_CMD", "mcap"),
		FanoutCommand:    envOrDefault("MCAP_FANOUT_GO_CMD", "./go_worker/mcap_fanout_worker"),
		ExportCommand:    envOrDefault("MCAP_EXPORT_CMD", "./export_convert_worker"),
		ExportWorkers:    parseIntOrDefault("JOB_RUNNER_EXPORT_WORKERS", 4),
		PrecomputeIngest: parseBoolOrDefault("INGEST_PRECOMPUTE_EXPORTS", true),
		PollInterval:     parseDurationOrDefault("JOB_RUNNER_POLL_INTERVAL", time.Second),
		ShutdownTimeout:  parseDurationOrDefault("JOB_RUNNER_SHUTDOWN_TIMEOUT", 5*time.Second),
		RecoverTimeout:   parseDurationOrDefault("JOB_RUNNER_RECOVER_TIMEOUT", 300*time.Second),
		FanoutTimeout:    parseDurationOrDefault("JOB_RUNNER_FANOUT_TIMEOUT", 600*time.Second),
	}

	jobTypesRaw := strings.TrimSpace(envOrDefault("JOB_RUNNER_TYPES", "ingest_pipeline,export_job,map_preview"))
	cfg.JobTypes = make([]string, 0)
	for _, part := range strings.Split(jobTypesRaw, ",") {
		item := strings.TrimSpace(part)
		if item != "" {
			cfg.JobTypes = append(cfg.JobTypes, item)
		}
	}
	if len(cfg.JobTypes) == 0 {
		cfg.JobTypes = []string{"ingest_pipeline"}
	}

	if cfg.DatabaseURL == "" {
		return cfg, errors.New("DATABASE_URL is required")
	}
	if cfg.McapLogsDir == "" {
		cfg.McapLogsDir = filepath.Join(cfg.MediaRoot, "mcap_logs")
	}
	if cfg.ExportWorkers < 1 {
		cfg.ExportWorkers = 1
	}

	return cfg, nil
}

func envOrDefault(name, fallback string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	return value
}

func parseDurationOrDefault(name string, fallback time.Duration) time.Duration {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	parsed, err := time.ParseDuration(raw)
	if err != nil {
		return fallback
	}
	return parsed
}

func parseIntOrDefault(name string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	v, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return v
}

func parseBoolOrDefault(name string, fallback bool) bool {
	raw := strings.TrimSpace(strings.ToLower(os.Getenv(name)))
	if raw == "" {
		return fallback
	}
	return raw == "1" || raw == "true" || raw == "yes" || raw == "on"
}

func claimNextJob(ctx context.Context, db *pgxpool.Pool, jobTypes []string) (*backgroundJob, error) {
	tx, err := db.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer func() {
		_ = tx.Rollback(ctx)
	}()

	const query = `
WITH next_job AS (
    SELECT id
    FROM api_backgroundjob
    WHERE status = 'pending'
      AND available_at <= NOW()
      AND job_type = ANY($1)
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE api_backgroundjob job
SET status = 'processing',
    attempts = job.attempts + 1,
    locked_at = NOW(),
    started_at = COALESCE(job.started_at, NOW()),
    error_message = '',
    updated_at = NOW()
FROM next_job
WHERE job.id = next_job.id
RETURNING job.id::text, job.job_type, job.payload, job.attempts, job.max_attempts;
`

	var job backgroundJob
	var payloadRaw []byte
	err = tx.QueryRow(ctx, query, jobTypes).Scan(&job.ID, &job.JobType, &payloadRaw, &job.Attempts, &job.MaxAttempts)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			if commitErr := tx.Commit(ctx); commitErr != nil {
				return nil, commitErr
			}
			return nil, nil
		}
		return nil, err
	}

	if err := json.Unmarshal(payloadRaw, &job.Payload); err != nil {
		return nil, fmt.Errorf("invalid job payload JSON: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}

	return &job, nil
}

func processJob(ctx context.Context, db *pgxpool.Pool, cfg config, job backgroundJob) (map[string]any, error) {
	switch job.JobType {
	case "ingest_pipeline":
		return processIngestPipeline(ctx, db, cfg, job)
	case "map_preview":
		return processMapPreviewOnly(ctx, db, cfg, job)
	case "export_job":
		return processExportJob(ctx, db, cfg, job)
	default:
		return nil, fmt.Errorf("unsupported job type: %s", job.JobType)
	}
}

func processIngestPipeline(ctx context.Context, db *pgxpool.Pool, cfg config, job backgroundJob) (map[string]any, error) {
	mcapLogID, err := payloadInt(job.Payload, "mcap_log_id")
	if err != nil {
		return nil, err
	}
	filePath, err := payloadString(job.Payload, "file_path")
	if err != nil {
		return nil, err
	}

	originalPath := resolveTaskPath(cfg.MediaRoot, filePath)
	if _, err := os.Stat(originalPath); err != nil {
		return nil, fmt.Errorf("mcap file not found: %s", originalPath)
	}

	if _, err := db.Exec(ctx, `UPDATE api_mcaplog SET recovery_status='processing' WHERE id=$1`, mcapLogID); err != nil {
		return nil, err
	}

	recoveredPath, recoveredURI, err := runRecover(cfg, originalPath)
	if err != nil {
		return nil, err
	}

	if _, err := db.Exec(ctx, `UPDATE api_mcaplog SET recovered_uri=$1, recovery_status='completed' WHERE id=$2`, recoveredURI, mcapLogID); err != nil {
		return nil, err
	}

	if _, err := db.Exec(ctx, `
UPDATE api_mcaplog
SET parse_status='processing',
    gps_status='processing',
    gps_error=NULL,
    map_preview_status='pending',
    map_preview_error=NULL
WHERE id=$1
`, mcapLogID); err != nil {
		return nil, err
	}

	fanoutResult, err := runFanout(cfg, recoveredPath, mcapLogID)
	if err != nil {
		return nil, err
	}

	parsed := fanoutResult.Summary
	channelsJSON, _ := json.Marshal(parsed.Channels)

	if _, err := db.Exec(ctx, `
UPDATE api_mcaplog
SET channels=$1::jsonb,
    channel_count=$2,
    start_time=$3,
    end_time=$4,
    duration_seconds=$5,
    captured_at=CASE WHEN $3 IS NULL THEN captured_at ELSE to_timestamp($3) END,
    parse_status='completed'
WHERE id=$6
`, string(channelsJSON), parsed.ChannelCount, parsed.StartTime, parsed.EndTime, parsed.Duration, mcapLogID); err != nil {
		return nil, err
	}

	gpsCoords := fanoutResult.GPS.AllCoordinates
	if len(gpsCoords) < 2 {
		if _, err := db.Exec(ctx, `
UPDATE api_mcaplog
SET lap_path=NULL,
    map_preview_uri=NULL,
    gps_status='completed',
    map_preview_status='skipped'
WHERE id=$1
`, mcapLogID); err != nil {
			return nil, err
		}
	} else {
		lineString := buildLineStringWKT(gpsCoords)
		mapStatus := "skipped"
		var mapURI *string
		if fanoutResult.MapPreview != nil {
			mapStatus = fanoutResult.MapPreview.Status
			mapURI = fanoutResult.MapPreview.URI
		}

		if _, err := db.Exec(ctx, `
UPDATE api_mcaplog
SET lap_path=ST_GeogFromText($1),
    gps_status='completed',
    map_preview_status=$2,
    map_preview_uri=$3
WHERE id=$4
`, lineString, mapStatus, mapURI, mcapLogID); err != nil {
			return nil, err
		}
	}

	artifacts := map[string]any{}
	ingestStatus := "completed"
	if cfg.PrecomputeIngest {
		precomputed, preErr := precomputeIngestArtifacts(cfg, recoveredPath, mcapLogID)
		if preErr != nil {
			log.Printf("precompute failed for log=%d: %v", mcapLogID, preErr)
			artifacts["precompute_error"] = preErr.Error()
			ingestStatus = "completed_with_errors"
		}
		for key, value := range precomputed {
			artifacts[key] = value
		}
		if hasFailedArtifacts(precomputed) {
			ingestStatus = "completed_with_errors"
		}
	}

	result := map[string]any{
		"mcap_log_id": mcapLogID,
		"status":      ingestStatus,
		"artifacts":   artifacts,
	}
	return result, nil
}

func precomputeIngestArtifacts(cfg config, sourcePath string, mcapLogID int64) (map[string]any, error) {
	outputs := map[string]any{}
	precomputedDir := filepath.Join(cfg.MediaRoot, "precomputed", strconv.FormatInt(mcapLogID, 10))
	if err := os.MkdirAll(precomputedDir, 0o755); err != nil {
		return outputs, err
	}

	batchResponse, err := runExportBatch(cfg, sourcePath, precomputedDir, strconv.FormatInt(mcapLogID, 10), 20.0)
	if err != nil {
		return outputs, err
	}

	for formatName, artifact := range batchResponse.Formats {
		entry := map[string]any{"status": artifact.Status}
		if artifact.Error != "" {
			entry["error"] = artifact.Error
		}
		if artifact.OutputPath != "" {
			entry["uri"] = mediaURI(cfg, artifact.OutputPath)
		}
		outputs[formatName] = entry
	}

	manifestPath := filepath.Join(cfg.MediaRoot, "precomputed", strconv.FormatInt(mcapLogID, 10), "manifest.json")
	if err := os.MkdirAll(filepath.Dir(manifestPath), 0o755); err == nil {
		if encoded, err := json.MarshalIndent(outputs, "", "  "); err == nil {
			_ = os.WriteFile(manifestPath, encoded, 0o644)
		}
	}

	return outputs, nil
}

func hasFailedArtifacts(outputs map[string]any) bool {
	for _, value := range outputs {
		artifact, ok := value.(map[string]any)
		if !ok {
			continue
		}
		status, ok := artifact["status"].(string)
		if ok && strings.EqualFold(status, "failed") {
			return true
		}
	}
	return false
}

func runRecover(cfg config, originalPath string) (string, string, error) {
	if err := os.MkdirAll(filepath.Join(cfg.McapLogsDir, "recovered"), 0o755); err != nil {
		return "", "", fmt.Errorf("failed to create recovered dir: %w", err)
	}

	ext := filepath.Ext(originalPath)
	stem := strings.TrimSuffix(filepath.Base(originalPath), ext)
	recoveredPath := filepath.Join(cfg.McapLogsDir, "recovered", stem+"-recovered"+ext)

	ctx, cancel := context.WithTimeout(context.Background(), cfg.RecoverTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, cfg.McapRecoverCmd, "recover", originalPath, "-o", recoveredPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return "", "", fmt.Errorf("mcap recover failed: %s", strings.TrimSpace(string(output)))
	}
	if _, err := os.Stat(recoveredPath); err != nil {
		return "", "", fmt.Errorf("recovered file was not created: %s", recoveredPath)
	}

	rel, err := filepath.Rel(cfg.MediaRoot, recoveredPath)
	if err != nil || strings.HasPrefix(rel, "..") {
		rel = filepath.ToSlash(filepath.Join("mcap_logs", "recovered", filepath.Base(recoveredPath)))
	} else {
		rel = filepath.ToSlash(rel)
	}
	mediaPrefix := strings.TrimRight(cfg.MediaURL, "/")
	uri := mediaPrefix + "/" + rel
	return recoveredPath, uri, nil
}

type fanoutResponse struct {
	Summary struct {
		Channels     []string `json:"channels"`
		ChannelCount int      `json:"channel_count"`
		StartTime    *float64 `json:"start_time"`
		EndTime      *float64 `json:"end_time"`
		Duration     float64  `json:"duration"`
	} `json:"summary"`
	GPS struct {
		AllCoordinates [][]float64 `json:"all_coordinates"`
	} `json:"gps"`
	MapPreview *struct {
		Status string  `json:"status"`
		URI    *string `json:"uri"`
	} `json:"map_preview"`
}

func runFanout(cfg config, sourcePath string, mcapLogID int64) (*fanoutResponse, error) {
	parts := strings.Fields(cfg.FanoutCommand)
	if len(parts) == 0 {
		return nil, errors.New("invalid MCAP_FANOUT_GO_CMD")
	}

	args := append(parts[1:],
		"--mode", "fanout",
		"--path", sourcePath,
		"--gps-sample-step", "10",
		"--generate-map-preview",
		"--log-id", strconv.FormatInt(mcapLogID, 10),
		"--media-root", cfg.MediaRoot,
		"--media-url", cfg.MediaURL,
	)

	ctx, cancel := context.WithTimeout(context.Background(), cfg.FanoutTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, parts[0], args...)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		errText := strings.TrimSpace(stderr.String())
		if errText == "" {
			errText = strings.TrimSpace(stdout.String())
		}
		return nil, fmt.Errorf("go fanout worker failed: %s", errText)
	}

	payload := strings.TrimSpace(stdout.String())
	if payload == "" {
		return nil, errors.New("go fanout worker returned empty output")
	}

	response := &fanoutResponse{}
	if err := json.Unmarshal([]byte(payload), response); err != nil {
		return nil, fmt.Errorf("invalid go fanout JSON: %w", err)
	}
	return response, nil
}

type mapPreviewOnlyResponse struct {
	MapPreview struct {
		Status string  `json:"status"`
		URI    *string `json:"uri"`
	} `json:"map_preview"`
}

func processMapPreviewOnly(ctx context.Context, db *pgxpool.Pool, cfg config, job backgroundJob) (map[string]any, error) {
	mcapLogID, err := payloadInt(job.Payload, "mcap_log_id")
	if err != nil {
		return nil, err
	}

	var geoJSON *string
	err = db.QueryRow(ctx, `
SELECT CASE WHEN lap_path IS NULL THEN NULL ELSE ST_AsGeoJSON(lap_path::geometry) END
FROM api_mcaplog
WHERE id=$1
`, mcapLogID).Scan(&geoJSON)
	if err != nil {
		return nil, err
	}

	if geoJSON == nil || strings.TrimSpace(*geoJSON) == "" {
		if _, err := db.Exec(ctx, `UPDATE api_mcaplog SET map_preview_status='skipped' WHERE id=$1`, mcapLogID); err != nil {
			return nil, err
		}
		return map[string]any{"mcap_log_id": mcapLogID, "status": "skipped"}, nil
	}

	if _, err := db.Exec(ctx, `UPDATE api_mcaplog SET map_preview_status='processing', map_preview_error=NULL WHERE id=$1`, mcapLogID); err != nil {
		return nil, err
	}

	coords, err := parseCoordsFromGeoJSON(*geoJSON)
	if err != nil {
		return nil, err
	}
	if len(coords) < 2 {
		if _, err := db.Exec(ctx, `UPDATE api_mcaplog SET map_preview_status='skipped' WHERE id=$1`, mcapLogID); err != nil {
			return nil, err
		}
		return map[string]any{"mcap_log_id": mcapLogID, "status": "skipped"}, nil
	}

	preview, err := runMapPreview(cfg, mcapLogID, coords)
	if err != nil {
		return nil, err
	}

	if _, err := db.Exec(ctx, `
UPDATE api_mcaplog
SET map_preview_uri=$1,
    map_preview_status=$2
WHERE id=$3
`, preview.MapPreview.URI, preview.MapPreview.Status, mcapLogID); err != nil {
		return nil, err
	}

	return map[string]any{
		"mcap_log_id":     mcapLogID,
		"status":          preview.MapPreview.Status,
		"map_preview_uri": preview.MapPreview.URI,
	}, nil
}

func runMapPreview(cfg config, mcapLogID int64, coords [][]float64) (*mapPreviewOnlyResponse, error) {
	coordsFile, err := os.CreateTemp("", "coords-*.json")
	if err != nil {
		return nil, err
	}
	defer os.Remove(coordsFile.Name())

	if err := json.NewEncoder(coordsFile).Encode(coords); err != nil {
		_ = coordsFile.Close()
		return nil, err
	}
	if err := coordsFile.Close(); err != nil {
		return nil, err
	}

	parts := strings.Fields(cfg.FanoutCommand)
	if len(parts) == 0 {
		return nil, errors.New("invalid MCAP_FANOUT_GO_CMD")
	}

	args := append(parts[1:],
		"--mode", "map-preview",
		"--log-id", strconv.FormatInt(mcapLogID, 10),
		"--coords-path", coordsFile.Name(),
		"--media-root", cfg.MediaRoot,
		"--media-url", cfg.MediaURL,
	)

	ctx, cancel := context.WithTimeout(context.Background(), cfg.FanoutTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, parts[0], args...)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		errText := strings.TrimSpace(stderr.String())
		if errText == "" {
			errText = strings.TrimSpace(stdout.String())
		}
		return nil, fmt.Errorf("go map preview worker failed: %s", errText)
	}

	payload := strings.TrimSpace(stdout.String())
	if payload == "" {
		return nil, errors.New("go map preview worker returned empty output")
	}

	response := &mapPreviewOnlyResponse{}
	if err := json.Unmarshal([]byte(payload), response); err != nil {
		return nil, fmt.Errorf("invalid map preview JSON: %w", err)
	}
	return response, nil
}

type exportJob struct {
	ID         int64
	Format     string
	ResampleHz float64
}

type exportItem struct {
	ID           int64
	McapLogID    int64
	FileName     string
	OriginalURI  string
	RecoveredURI string
}

func processExportJob(ctx context.Context, db *pgxpool.Pool, cfg config, job backgroundJob) (map[string]any, error) {
	exportJobID, err := payloadInt(job.Payload, "export_job_id")
	if err != nil {
		return nil, err
	}

	jobRow := exportJob{}
	err = db.QueryRow(ctx, `SELECT id, format, resample_hz FROM api_exportjob WHERE id=$1`, exportJobID).Scan(&jobRow.ID, &jobRow.Format, &jobRow.ResampleHz)
	if err != nil {
		return nil, err
	}

	if _, err := db.Exec(ctx, `UPDATE api_exportjob SET status='processing', error_message=NULL, updated_at=NOW() WHERE id=$1`, exportJobID); err != nil {
		return nil, err
	}

	items, err := fetchExportItems(ctx, db, exportJobID)
	if err != nil {
		return nil, err
	}
	if len(items) == 0 {
		if _, err := db.Exec(ctx, `UPDATE api_exportjob SET status='failed', error_message='No items found for export job', completed_at=NOW(), updated_at=NOW() WHERE id=$1`, exportJobID); err != nil {
			return nil, err
		}
		return map[string]any{"export_job_id": exportJobID, "status": "failed"}, nil
	}

	completed := make([]exportItem, 0, len(items))
	failedCount := 0
	workers := cfg.ExportWorkers
	if workers > len(items) {
		workers = len(items)
	}
	type exportResult struct {
		item exportItem
		err  error
	}

	jobsCh := make(chan exportItem)
	resultsCh := make(chan exportResult, len(items))
	var wg sync.WaitGroup

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range jobsCh {
				err := convertExportItem(ctx, db, cfg, jobRow, item)
				resultsCh <- exportResult{item: item, err: err}
			}
		}()
	}

	go func() {
		for _, item := range items {
			jobsCh <- item
		}
		close(jobsCh)
		wg.Wait()
		close(resultsCh)
	}()

	for result := range resultsCh {
		if result.err != nil {
			failedCount++
			if _, markErr := db.Exec(ctx, `UPDATE api_exportitem SET status='failed', error_message=$1, updated_at=NOW() WHERE id=$2`, result.err.Error(), result.item.ID); markErr != nil {
				log.Printf("failed to update export item id=%d failure: %v", result.item.ID, markErr)
			}
			continue
		}
		completed = append(completed, result.item)
	}

	if len(completed) == 0 {
		if _, err := db.Exec(ctx, `UPDATE api_exportjob SET status='failed', error_message='No files were converted successfully', completed_at=NOW(), updated_at=NOW() WHERE id=$1`, exportJobID); err != nil {
			return nil, err
		}
		return map[string]any{"export_job_id": exportJobID, "status": "failed"}, nil
	}

	zipPath, zipURI, err := createExportBundle(cfg, jobRow, completed)
	if err != nil {
		return nil, err
	}
	_ = zipPath

	status := "completed"
	var errorMessage any = nil
	if failedCount > 0 {
		status = "completed_with_errors"
		errorMessage = fmt.Sprintf("%d item(s) failed", failedCount)
	}

	if _, err := db.Exec(ctx, `
UPDATE api_exportjob
SET zip_uri=$1,
    status=$2,
    error_message=$3,
    completed_at=NOW(),
    updated_at=NOW()
WHERE id=$4
`, zipURI, status, errorMessage, exportJobID); err != nil {
		return nil, err
	}

	return map[string]any{
		"export_job_id":   exportJobID,
		"status":          status,
		"completed_items": len(completed),
		"failed_items":    failedCount,
	}, nil
}

func fetchExportItems(ctx context.Context, db *pgxpool.Pool, exportJobID int64) ([]exportItem, error) {
	rows, err := db.Query(ctx, `
SELECT item.id, item.mcap_log_id, log.file_name, COALESCE(log.original_uri,''), COALESCE(log.recovered_uri,'')
FROM api_exportitem item
JOIN api_mcaplog log ON log.id = item.mcap_log_id
WHERE item.job_id=$1
ORDER BY item.id
`, exportJobID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]exportItem, 0)
	for rows.Next() {
		item := exportItem{}
		if err := rows.Scan(&item.ID, &item.McapLogID, &item.FileName, &item.OriginalURI, &item.RecoveredURI); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func convertExportItem(ctx context.Context, db *pgxpool.Pool, cfg config, job exportJob, item exportItem) error {
	if _, err := db.Exec(ctx, `UPDATE api_exportitem SET status='processing', attempts=attempts+1, error_message=NULL, updated_at=NOW() WHERE id=$1`, item.ID); err != nil {
		return err
	}

	sourcePath := resolveSourcePath(cfg, item.OriginalURI, item.RecoveredURI)
	if sourcePath == "" {
		return errors.New("MCAP source not found")
	}
	if _, err := os.Stat(sourcePath); err != nil {
		return fmt.Errorf("MCAP source not found: %s", sourcePath)
	}

	formatSuffix := strings.TrimPrefix(job.Format, "csv_")
	ext := "csv"
	if formatSuffix == "h5" {
		ext = "h5"
	}

	exportDir := filepath.Join(cfg.MediaRoot, "exports", strconv.FormatInt(job.ID, 10))
	if err := os.MkdirAll(exportDir, 0o755); err != nil {
		return err
	}
	outputFile := filepath.Join(exportDir, fmt.Sprintf("%d_%s.%s", item.McapLogID, formatSuffix, ext))
	precomputed := precomputedArtifactPath(cfg, item.McapLogID, formatSuffix)
	if precomputedExists(precomputed) {
		if err := copyFile(precomputed, outputFile); err != nil {
			return err
		}
	} else {
		if err := runExportConversion(cfg, sourcePath, outputFile, formatSuffix, job.ResampleHz); err != nil {
			return err
		}
	}

	rel, err := filepath.Rel(cfg.MediaRoot, outputFile)
	if err != nil {
		rel = filepath.Join("exports", strconv.FormatInt(job.ID, 10), filepath.Base(outputFile))
	}
	outputURI := strings.TrimRight(cfg.MediaURL, "/") + "/" + filepath.ToSlash(rel)

	_, err = db.Exec(ctx, `
UPDATE api_exportitem
SET output_uri=$1,
    status='completed',
    error_message=NULL,
    updated_at=NOW()
WHERE id=$2
`, outputURI, item.ID)
	return err
}

func runExportConversion(cfg config, sourcePath, outputPath, formatSuffix string, resampleHz float64) error {
	parts := strings.Fields(cfg.ExportCommand)
	if len(parts) == 0 {
		return errors.New("invalid MCAP_EXPORT_CMD")
	}

	args := append(parts[1:],
		"--source", sourcePath,
		"--output", outputPath,
		"--format", formatSuffix,
		"--resample-hz", strconv.FormatFloat(resampleHz, 'f', -1, 64),
	)

	ctx, cancel := context.WithTimeout(context.Background(), cfg.FanoutTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, parts[0], args...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("export conversion failed: %s", strings.TrimSpace(string(output)))
	}
	return nil
}

type exportBatchArtifact struct {
	Status     string `json:"status"`
	OutputPath string `json:"output_path,omitempty"`
	Error      string `json:"error,omitempty"`
}

type exportBatchResponse struct {
	Formats map[string]exportBatchArtifact `json:"formats"`
}

func runExportBatch(
	cfg config,
	sourcePath string,
	outputDir string,
	baseName string,
	resampleHz float64,
) (*exportBatchResponse, error) {
	parts := strings.Fields(cfg.ExportCommand)
	if len(parts) == 0 {
		return nil, errors.New("invalid MCAP_EXPORT_CMD")
	}
	args := append(parts[1:],
		"--source", sourcePath,
		"--format", "all",
		"--output-dir", outputDir,
		"--base-name", baseName,
		"--resample-hz", strconv.FormatFloat(resampleHz, 'f', -1, 64),
	)

	ctx, cancel := context.WithTimeout(context.Background(), cfg.FanoutTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, parts[0], args...)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		details := strings.TrimSpace(stderr.String())
		if details == "" {
			details = strings.TrimSpace(stdout.String())
		}
		return nil, fmt.Errorf("export batch failed: %s", details)
	}

	raw := strings.TrimSpace(stdout.String())
	if raw == "" {
		return nil, errors.New("export batch returned empty output")
	}

	response := &exportBatchResponse{}
	if err := json.Unmarshal([]byte(raw), response); err != nil {
		return nil, fmt.Errorf("invalid export batch JSON: %w", err)
	}
	if response.Formats == nil {
		response.Formats = map[string]exportBatchArtifact{}
	}
	return response, nil
}

func precomputedArtifactPath(cfg config, mcapLogID int64, formatSuffix string) string {
	ext := "csv"
	if formatSuffix == "h5" {
		ext = "h5"
	}
	base := filepath.Join(cfg.MediaRoot, "precomputed", strconv.FormatInt(mcapLogID, 10))
	return filepath.Join(base, fmt.Sprintf("%d_%s.%s", mcapLogID, formatSuffix, ext))
}

func mediaURI(cfg config, absPath string) string {
	rel, err := filepath.Rel(cfg.MediaRoot, absPath)
	if err != nil {
		rel = filepath.Base(absPath)
	}
	return strings.TrimRight(cfg.MediaURL, "/") + "/" + filepath.ToSlash(rel)
}

func precomputedExists(path string) bool {
	if path == "" {
		return false
	}
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func copyFile(sourcePath, destinationPath string) error {
	source, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer source.Close()
	if err := os.MkdirAll(filepath.Dir(destinationPath), 0o755); err != nil {
		return err
	}
	dest, err := os.Create(destinationPath)
	if err != nil {
		return err
	}
	defer dest.Close()
	if _, err := io.Copy(dest, source); err != nil {
		return err
	}
	return nil
}

func resolveSourcePath(cfg config, originalURI, recoveredURI string) string {
	if recoveredURI != "" && recoveredURI != "pending" {
		recovered := resolveURIPath(cfg, recoveredURI)
		if recovered != "" {
			if _, err := os.Stat(recovered); err == nil {
				return recovered
			}
		}
	}
	return resolveURIPath(cfg, originalURI)
}

func resolveURIPath(cfg config, uri string) string {
	trimmed := strings.TrimSpace(uri)
	if trimmed == "" {
		return ""
	}
	if strings.HasPrefix(trimmed, strings.TrimRight(cfg.MediaURL, "/")+"/") {
		rel := strings.TrimPrefix(trimmed, strings.TrimRight(cfg.MediaURL, "/")+"/")
		return filepath.Join(cfg.MediaRoot, filepath.FromSlash(rel))
	}
	if filepath.IsAbs(trimmed) {
		return trimmed
	}
	if strings.HasPrefix(trimmed, "/") {
		return trimmed
	}
	return filepath.Join(cfg.MediaRoot, trimmed)
}

func createExportBundle(cfg config, job exportJob, completed []exportItem) (string, string, error) {
	formatSuffix := strings.TrimPrefix(job.Format, "csv_")
	ext := "csv"
	if formatSuffix == "h5" {
		ext = "h5"
	}

	exportDir := filepath.Join(cfg.MediaRoot, "exports", strconv.FormatInt(job.ID, 10))
	if err := os.MkdirAll(exportDir, 0o755); err != nil {
		return "", "", err
	}
	zipPath := filepath.Join(exportDir, "bundle.zip")

	zipFile, err := os.Create(zipPath)
	if err != nil {
		return "", "", err
	}
	defer zipFile.Close()

	zipWriter := zip.NewWriter(zipFile)
	for _, item := range completed {
		source := filepath.Join(exportDir, fmt.Sprintf("%d_%s.%s", item.McapLogID, formatSuffix, ext))
		if _, err := os.Stat(source); err != nil {
			continue
		}
		archiveName := fmt.Sprintf("%s_%s.%s", strings.TrimSuffix(item.FileName, filepath.Ext(item.FileName)), formatSuffix, ext)
		if err := addFileToZip(zipWriter, source, archiveName); err != nil {
			_ = zipWriter.Close()
			return "", "", err
		}
	}
	if err := zipWriter.Close(); err != nil {
		return "", "", err
	}

	rel, err := filepath.Rel(cfg.MediaRoot, zipPath)
	if err != nil {
		rel = filepath.Join("exports", strconv.FormatInt(job.ID, 10), "bundle.zip")
	}
	zipURI := strings.TrimRight(cfg.MediaURL, "/") + "/" + filepath.ToSlash(rel)
	return zipPath, zipURI, nil
}

func addFileToZip(zipWriter *zip.Writer, sourcePath, archiveName string) error {
	file, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer file.Close()

	entry, err := zipWriter.Create(archiveName)
	if err != nil {
		return err
	}
	_, err = io.Copy(entry, file)
	return err
}

func parseCoordsFromGeoJSON(raw string) ([][]float64, error) {
	var geo struct {
		Type        string      `json:"type"`
		Coordinates [][]float64 `json:"coordinates"`
	}
	if err := json.Unmarshal([]byte(raw), &geo); err != nil {
		return nil, err
	}
	if strings.ToLower(geo.Type) != "linestring" {
		return nil, fmt.Errorf("unsupported geometry type: %s", geo.Type)
	}
	return geo.Coordinates, nil
}

func buildLineStringWKT(coords [][]float64) string {
	parts := make([]string, 0, len(coords))
	for _, p := range coords {
		if len(p) < 2 {
			continue
		}
		parts = append(parts, fmt.Sprintf("%f %f", p[0], p[1]))
	}
	return "SRID=4326;LINESTRING(" + strings.Join(parts, ",") + ")"
}

func payloadString(payload map[string]any, key string) (string, error) {
	v, ok := payload[key]
	if !ok {
		return "", fmt.Errorf("payload missing %s", key)
	}
	value, ok := v.(string)
	if !ok || strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("payload %s is not a valid string", key)
	}
	return value, nil
}

func payloadInt(payload map[string]any, key string) (int64, error) {
	v, ok := payload[key]
	if !ok {
		return 0, fmt.Errorf("payload missing %s", key)
	}
	switch typed := v.(type) {
	case float64:
		return int64(typed), nil
	case int64:
		return typed, nil
	case int:
		return int64(typed), nil
	default:
		return 0, fmt.Errorf("payload %s is not numeric", key)
	}
}

func resolveTaskPath(mediaRoot, filePath string) string {
	if filepath.IsAbs(filePath) {
		return filePath
	}
	return filepath.Join(mediaRoot, filePath)
}

func markJobCompleted(ctx context.Context, db *pgxpool.Pool, jobID string, result map[string]any) error {
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return err
	}
	_, err = db.Exec(ctx, `
UPDATE api_backgroundjob
SET status='completed',
    result=$1::jsonb,
    error_message='',
    completed_at=NOW(),
    locked_at=NULL,
    updated_at=NOW()
WHERE id=$2::uuid
`, string(resultJSON), jobID)
	return err
}

func markJobFailed(ctx context.Context, db *pgxpool.Pool, job backgroundJob, cause error) error {
	message := cause.Error()
	if job.Attempts < job.MaxAttempts {
		delaySeconds := minInt(300, 15*job.Attempts)
		_, err := db.Exec(ctx, `
UPDATE api_backgroundjob
SET status='pending',
    available_at=NOW() + ($1 * interval '1 second'),
    error_message=$2,
    locked_at=NULL,
    updated_at=NOW()
WHERE id=$3::uuid
`, delaySeconds, message, job.ID)
		return err
	}

	_, err := db.Exec(ctx, `
UPDATE api_backgroundjob
SET status='failed',
    error_message=$1,
    completed_at=NOW(),
    locked_at=NULL,
    updated_at=NOW()
WHERE id=$2::uuid
`, message, job.ID)
	return err
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
