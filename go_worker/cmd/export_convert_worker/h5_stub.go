//go:build !hdf5

package main

import "errors"

func writeH5(output string, d *dataLog) error {
	_ = output
	_ = d
	return errors.New("h5 export not enabled in this build; rebuild with '-tags hdf5' and HDF5 dev libraries installed")
}
