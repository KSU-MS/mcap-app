package utils

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// RecoverMCAP runs `mcap recover` and writes to a sibling output file.
// Example output for /tmp/run.mcap -> /tmp/run.recovered.mcap
func RecoverMCAP(inputPath string) (string, error) {
	if strings.TrimSpace(inputPath) == "" {
		return "", fmt.Errorf("input path is required")
	}

	if err := validateInputMCAP(inputPath); err != nil {
		return "", err
	}

	outPath := recoveredOutputPath(inputPath)
	if err := RecoverMCAPToFile(inputPath, outPath); err != nil {
		return "", err
	}

	return outPath, nil
}

// RecoverMCAPToFile runs `mcap recover <input> -o <output>`.
func RecoverMCAPToFile(inputPath, outputPath string) error {
	if strings.TrimSpace(outputPath) == "" {
		return fmt.Errorf("output path is required")
	}

	if err := validateInputMCAP(inputPath); err != nil {
		return err
	}

	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return fmt.Errorf("create output directory: %w", err)
	}

	var stderr bytes.Buffer
	cmd := exec.Command("mcap", "recover", inputPath, "-o", outputPath)
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return fmt.Errorf("mcap recover failed: %s", strings.TrimSpace(stderr.String()))
		}
		return fmt.Errorf("mcap recover failed: %w", err)
	}

	return nil
}

func recoveredOutputPath(inputPath string) string {
	ext := filepath.Ext(inputPath)
	base := strings.TrimSuffix(inputPath, ext)
	return base + ".recovered" + ext
}

func validateInputMCAP(inputPath string) error {
	if strings.TrimSpace(inputPath) == "" {
		return fmt.Errorf("input path is required")
	}

	info, err := os.Stat(inputPath)
	if err != nil {
		return fmt.Errorf("read input file: %w", err)
	}
	if info.IsDir() {
		return fmt.Errorf("input path is a directory: %s", inputPath)
	}

	return nil
}
