package subscribers

import (
	"fmt"
	"io"

	"gonum.org/v1/plot"
	"gonum.org/v1/plot/plotter"
	"gonum.org/v1/plot/vg"
)

// GenerateGPSPathImage creates a line image of the GPS path.
func GenerateGPSPathImage(lats, lons []float32) (*io.WriterTo, error) {
	p := plot.New()
	p.Title.Text = "GPS Path"
	p.X.Label.Text = "longitude"
	p.Y.Label.Text = "latitude"
	p.HideAxes()

	if len(lats) != len(lons) {
		return nil, fmt.Errorf("lat/lon length mismatch")
	}
	if len(lats) == 0 {
		writer, err := p.WriterTo(25*vg.Centimeter, 25*vg.Centimeter, "png")
		if err != nil {
			return nil, fmt.Errorf("could not get plot writer: %+v", err)
		}
		return &writer, nil
	}

	pts := make(plotter.XYs, len(lats))

	minX, maxX := float64(lons[0]), float64(lons[0])
	minY, maxY := float64(lats[0]), float64(lats[0])
	for i := range lats {
		xf := float64(lons[i])
		yf := float64(lats[i])
		pts[i].X = xf
		pts[i].Y = yf
		if xf < minX {
			minX = xf
		}
		if xf > maxX {
			maxX = xf
		}
		if yf < minY {
			minY = yf
		}
		if yf > maxY {
			maxY = yf
		}
	}

	p.X.Min = minX
	p.Y.Min = minY
	p.X.Max = maxX
	p.Y.Max = maxY

	line, err := plotter.NewLine(pts)
	if err != nil {
		return nil, fmt.Errorf("could not create line plot: %+v", err)
	}
	p.Add(line)

	writer, err := p.WriterTo(25*vg.Centimeter, 25*vg.Centimeter, "png")
	if err != nil {
		return nil, fmt.Errorf("could not get plot writer: %+v", err)
	}

	return &writer, nil
}
