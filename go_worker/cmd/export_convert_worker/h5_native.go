//go:build hdf5

package main

import (
	"errors"
	"strings"

	"gonum.org/v1/hdf5"
)

func writeH5(output string, d *dataLog) error {
	if len(d.Order) == 0 {
		return errors.New("no channels available for h5")
	}

	file, err := hdf5.CreateFile(output, hdf5.F_ACC_TRUNC)
	if err != nil {
		return err
	}
	defer file.Close()

	group, err := file.CreateGroup("data")
	if err != nil {
		return err
	}
	defer group.Close()

	chunk, err := file.CreateGroup("/data/chunk_0")
	if err != nil {
		return err
	}
	defer chunk.Close()

	for _, channelName := range d.Order {
		samples := d.Channels[channelName].Messages
		series := make([][]float64, len(samples))
		for i, s := range samples {
			series[i] = []float64{s.Timestamp, s.Value}
		}
		safeName := strings.ReplaceAll(channelName, "/", "_")
		safeName = strings.ReplaceAll(safeName, ".", "_")
		if err := writeSeriesDataset(chunk, safeName, series); err != nil {
			return err
		}
	}

	return nil
}

func writeSeriesDataset(group *hdf5.Group, name string, values [][]float64) error {
	if len(values) == 0 {
		return nil
	}
	flattened := flattenSeries(values)
	dims := []uint{uint(len(values)), 2}
	space, err := hdf5.CreateSimpleDataspace(dims, nil)
	if err != nil {
		return err
	}
	defer space.Close()

	dataset, err := group.CreateDataset(name, hdf5.T_NATIVE_DOUBLE, space)
	if err != nil {
		return err
	}
	defer dataset.Close()

	return dataset.Write(&flattened)
}

func flattenSeries(values [][]float64) []float64 {
	flat := make([]float64, 0, len(values)*2)
	for _, pair := range values {
		if len(pair) < 2 {
			continue
		}
		flat = append(flat, pair[0], pair[1])
	}
	return flat
}
