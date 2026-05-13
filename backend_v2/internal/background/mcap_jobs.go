package background

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/KSU-MS/mcap-app/blob/main/backend_v2/internal/utils"
)

const (
	localStorageRootEnv = "LOCAL_STORAGE_ROOT"
	defaultStorageRoot  = "backend_v2/data"
)

type RecoverMCAPJob struct {
	OutputDir    string
	DeleteSource bool
}

type LocalArtifactDirs struct {
	Root      string
	Recovered string
	H5        string
}

func NewRecoverMCAPJob() (*RecoverMCAPJob, error) {
	dirs, err := EnsureLocalArtifactDirs()
	if err != nil {
		return nil, err
	}
	return &RecoverMCAPJob{OutputDir: dirs.Recovered}, nil
}

func EnsureLocalArtifactDirs() (*LocalArtifactDirs, error) {
	root := os.Getenv(localStorageRootEnv)
	if root == "" {
		uploadDir := os.Getenv("UPLOAD_DIR")
		if uploadDir != "" {
			root = uploadDir
		} else {
			root = defaultStorageRoot
		}
	}

	rootAbs, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("resolve local storage root: %w", err)
	}

	recoveredDir := filepath.Join(rootAbs, "recovered")
	h5Dir := filepath.Join(rootAbs, "h5")

	if err := os.MkdirAll(recoveredDir, 0o755); err != nil {
		return nil, fmt.Errorf("create recovered directory: %w", err)
	}
	if err := os.MkdirAll(h5Dir, 0o755); err != nil {
		return nil, fmt.Errorf("create h5 directory: %w", err)
	}

	return &LocalArtifactDirs{
		Root:      rootAbs,
		Recovered: recoveredDir,
		H5:        h5Dir,
	}, nil
}

func (r *RecoverMCAPJob) ProcessFileJob(ctx context.Context, fp *FileProcessor, job *FileJob) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	if job == nil {
		return fmt.Errorf("job is required")
	}

	outPath := ""
	if r != nil && r.OutputDir != "" {
		if err := os.MkdirAll(r.OutputDir, 0o755); err != nil {
			return fmt.Errorf("create output directory: %w", err)
		}
		outPath = filepath.Join(r.OutputDir, recoveredFilename(job.ID, job.Filename))
	}

	if outPath == "" {
		recoveredPath, err := utils.RecoverMCAP(job.FilePath)
		if err != nil {
			return err
		}
		outPath = recoveredPath
	} else {
		if err := utils.RecoverMCAPToFile(job.FilePath, outPath); err != nil {
			return err
		}
	}

	if r != nil && r.DeleteSource {
		if err := os.Remove(job.FilePath); err != nil {
			return fmt.Errorf("remove source mcap: %w", err)
		}
	}

	job.FilePath = outPath
	job.FileDir = filepath.Dir(outPath)
	job.Filename = filepath.Base(outPath)

	return nil
}

func recoveredFilename(jobID, name string) string {
	ext := filepath.Ext(name)
	base := name[:len(name)-len(ext)]
	if jobID != "" {
		return fmt.Sprintf("%s_%s.recovered%s", jobID, base, ext)
	}
	return base + ".recovered" + ext
}
