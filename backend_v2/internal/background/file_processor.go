package background

import (
	"context"
	"fmt"
	"mime/multipart"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"
)

const (
	StatusPending    = "pending"
	StatusProcessing = "processing"
	StatusCompleted  = "completed"
	StatusFailed     = "failed"
)

type FileJobProcessor interface {
	ProcessFileJob(ctx context.Context, fp *FileProcessor, job *FileJob) error
}

type FileJob struct {
	ID        string
	Filename  string
	FilePath  string
	FileDir   string
	Size      int64
	Status    string
	CreatedAt time.Time
	UpdatedAt time.Time
	Processor FileJobProcessor
	Err       error
}

type FileProcessor struct {
	directory string
	queue     chan *FileJob
	stop      chan struct{}
	workers   int

	MiddlewareEstimatedSize atomic.Int64
	TotalSize               atomic.Int64
	maxTotalSize            int64

	mu   sync.RWMutex
	wg   sync.WaitGroup
	jobs map[string]*FileJob
}

func NewFileProcessor(uploadDir string, queueSize int) (*FileProcessor, error) {
	return NewFileProcessorWithWorkersAndMaxSize(uploadDir, queueSize, 1, 0)
}

func NewFileProcessorWithWorkers(uploadDir string, queueSize int, workers int) (*FileProcessor, error) {
	return NewFileProcessorWithWorkersAndMaxSize(uploadDir, queueSize, workers, 0)
}

func NewFileProcessorWithWorkersAndMaxSize(uploadDir string, queueSize int, workers int, maxTotalSize int64) (*FileProcessor, error) {
	if queueSize <= 0 {
		queueSize = 100
	}
	if workers <= 0 {
		workers = 1
	}
	if err := os.MkdirAll(uploadDir, 0o755); err != nil {
		return nil, fmt.Errorf("create upload directory: %w", err)
	}

	return &FileProcessor{
		directory:    uploadDir,
		queue:        make(chan *FileJob, queueSize),
		stop:         make(chan struct{}),
		workers:      workers,
		maxTotalSize: maxTotalSize,
		jobs:         make(map[string]*FileJob),
	}, nil
}

func (fp *FileProcessor) Start(ctx context.Context) {
	fp.wg.Add(fp.workers)
	for i := 0; i < fp.workers; i++ {
		go fp.listen(ctx)
	}
}

func (fp *FileProcessor) Stop() {
	close(fp.stop)
	fp.wg.Wait()
}

func (fp *FileProcessor) EnqueuePath(filePath string, processor FileJobProcessor) (*FileJob, error) {
	if processor == nil {
		return nil, fmt.Errorf("processor is required")
	}

	info, err := os.Stat(filePath)
	if err != nil {
		return nil, fmt.Errorf("stat file: %w", err)
	}
	if info.IsDir() {
		return nil, fmt.Errorf("path is a directory: %s", filePath)
	}

	job := &FileJob{
		ID:        fmt.Sprintf("job_%d", time.Now().UnixNano()),
		Filename:  filepath.Base(filePath),
		FilePath:  filePath,
		FileDir:   filepath.Dir(filePath),
		Size:      info.Size(),
		Status:    StatusPending,
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
		Processor: processor,
	}

	fp.queue <- job
	fp.TotalSize.Add(job.Size)
	fp.registerJob(job)
	return job, nil
}

func (fp *FileProcessor) EnqueueFileUpload(fileHeader *multipart.FileHeader, processor FileJobProcessor) (*FileJob, error) {
	if fileHeader == nil {
		return nil, fmt.Errorf("file header is required")
	}
	if processor == nil {
		return nil, fmt.Errorf("processor is required")
	}

	src, err := fileHeader.Open()
	if err != nil {
		return nil, fmt.Errorf("open upload: %w", err)
	}
	defer src.Close()

	jobID := fmt.Sprintf("job_%d", time.Now().UnixNano())
	fullPath := filepath.Join(fp.directory, fmt.Sprintf("%s_%s", jobID, fileHeader.Filename))

	dst, err := os.Create(fullPath)
	if err != nil {
		return nil, fmt.Errorf("create queued file: %w", err)
	}
	defer dst.Close()

	if _, err := dst.ReadFrom(src); err != nil {
		_ = os.Remove(fullPath)
		return nil, fmt.Errorf("copy queued file: %w", err)
	}

	job := &FileJob{
		ID:        jobID,
		Filename:  fileHeader.Filename,
		FilePath:  fullPath,
		FileDir:   fp.directory,
		Size:      fileHeader.Size,
		Status:    StatusPending,
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
		Processor: processor,
	}

	fp.queue <- job
	fp.TotalSize.Add(job.Size)
	fp.registerJob(job)
	return job, nil
}

func (fp *FileProcessor) listen(ctx context.Context) {
	defer fp.wg.Done()
	for {
		select {
		case <-ctx.Done():
			return
		case <-fp.stop:
			return
		case job := <-fp.queue:
			fp.processOne(ctx, job)
		}
	}
}

func (fp *FileProcessor) processOne(ctx context.Context, job *FileJob) {
	fp.updateJobStatus(job, StatusProcessing, nil)
	err := job.Processor.ProcessFileJob(ctx, fp, job)
	if err != nil {
		fp.updateJobStatus(job, StatusFailed, err)
		fp.MiddlewareEstimatedSize.Add(-job.Size)
		fp.TotalSize.Add(-job.Size)
		return
	}
	fp.updateJobStatus(job, StatusCompleted, nil)
	fp.MiddlewareEstimatedSize.Add(-job.Size)
	fp.TotalSize.Add(-job.Size)
}

func (fp *FileProcessor) updateJobStatus(job *FileJob, status string, err error) {
	fp.mu.Lock()
	defer fp.mu.Unlock()
	job.Status = status
	job.Err = err
	job.UpdatedAt = time.Now()
}

func (fp *FileProcessor) MaxTotalSize() int64 {
	return fp.maxTotalSize
}

func (fp *FileProcessor) registerJob(job *FileJob) {
	fp.mu.Lock()
	defer fp.mu.Unlock()
	fp.jobs[job.ID] = job
}

func (fp *FileProcessor) GetJob(jobID string) (*FileJob, bool) {
	fp.mu.RLock()
	defer fp.mu.RUnlock()
	job, ok := fp.jobs[jobID]
	if !ok {
		return nil, false
	}
	clone := *job
	return &clone, true
}
