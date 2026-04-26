package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/foxglove/mcap/go/mcap"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protodesc"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/descriptorpb"
	"google.golang.org/protobuf/types/dynamicpb"
)

const gpsTopic = "evelogger_vectornav_position_data"
const tileSize = 256.0
const previewWidth = 232.0
const previewHeight = 144.0
const previewPadding = 14.0

type summaryPayload struct {
	Channels      []string `json:"channels"`
	ChannelCount  int      `json:"channel_count"`
	StartTime     *float64 `json:"start_time"`
	EndTime       *float64 `json:"end_time"`
	Duration      float64  `json:"duration"`
	FormattedDate *string  `json:"formatted_date"`
	Latitude      *float64 `json:"latitude"`
	Longitude     *float64 `json:"longitude"`
}

type gpsPayload struct {
	Latitude       *float64     `json:"latitude"`
	Longitude      *float64     `json:"longitude"`
	AllCoordinates [][2]float64 `json:"all_coordinates"`
}

type fanoutPayload struct {
	Summary    summaryPayload     `json:"summary"`
	GPS        gpsPayload         `json:"gps"`
	MapPreview *mapPreviewPayload `json:"map_preview,omitempty"`
}

type mapPreviewPayload struct {
	Status string  `json:"status"`
	URI    *string `json:"uri"`
}

type mapPreviewOnlyPayload struct {
	MapPreview mapPreviewPayload `json:"map_preview"`
}

type gpsDecoder struct {
	messageDescriptor protoreflect.MessageDescriptor
	latitudeField     protoreflect.FieldDescriptor
	longitudeField    protoreflect.FieldDescriptor
}

func main() {
	mode := flag.String("mode", "fanout", "fanout or map-preview")
	path := flag.String("path", "", "absolute path to MCAP file")
	gpsSampleStep := flag.Int("gps-sample-step", 10, "sample every N valid GPS points")
	generateMapPreview := flag.Bool("generate-map-preview", false, "generate map preview from GPS points")
	logID := flag.Int("log-id", 0, "mcap log id used for output filename")
	mediaRoot := flag.String("media-root", "", "media root directory for writing map preview")
	mediaURL := flag.String("media-url", "/media/", "media URL prefix")
	coordsPath := flag.String("coords-path", "", "path to coords JSON file for map-preview mode")
	flag.Parse()

	switch *mode {
	case "fanout":
		if *path == "" {
			fail(errors.New("--path is required"))
		}

		result, err := runFanout(*path, *gpsSampleStep)
		if err != nil {
			fail(err)
		}

		if *generateMapPreview {
			if *logID <= 0 {
				fail(errors.New("--log-id is required when --generate-map-preview is set"))
			}
			if strings.TrimSpace(*mediaRoot) == "" {
				fail(errors.New("--media-root is required when --generate-map-preview is set"))
			}
			preview, err := generateMapPreviewSVG(*logID, result.GPS.AllCoordinates, *mediaRoot, *mediaURL)
			if err != nil {
				fail(err)
			}
			result.MapPreview = preview
		}

		emitJSON(result)
	case "map-preview":
		if *logID <= 0 {
			fail(errors.New("--log-id is required in map-preview mode"))
		}
		if strings.TrimSpace(*mediaRoot) == "" {
			fail(errors.New("--media-root is required in map-preview mode"))
		}
		if strings.TrimSpace(*coordsPath) == "" {
			fail(errors.New("--coords-path is required in map-preview mode"))
		}

		coords, err := loadCoords(*coordsPath)
		if err != nil {
			fail(err)
		}
		preview, err := generateMapPreviewSVG(*logID, coords, *mediaRoot, *mediaURL)
		if err != nil {
			fail(err)
		}
		emitJSON(&mapPreviewOnlyPayload{MapPreview: *preview})
	default:
		fail(fmt.Errorf("unsupported --mode value: %s", *mode))
	}
}

func runFanout(path string, gpsSampleStep int) (*fanoutPayload, error) {
	fileHandle, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("failed to open MCAP file: %w", err)
	}
	defer fileHandle.Close()

	reader, err := mcap.NewReader(fileHandle)
	if err != nil {
		return nil, fmt.Errorf("failed to create MCAP reader: %w", err)
	}

	iterator, err := reader.Messages()
	if err != nil {
		return nil, fmt.Errorf("failed to create message iterator: %w", err)
	}

	validStep := gpsSampleStep
	if validStep < 1 {
		validStep = 1
	}

	channels := make([]string, 0)
	seenChannels := make(map[string]struct{})
	var minLogTime *uint64
	var maxLogTime *uint64

	var firstLat *float64
	var firstLon *float64
	allCoordinates := make([][2]float64, 0)
	var lastPoint *[2]float64
	validGPSCount := 0

	gpsDecoders := make(map[uint16]*gpsDecoder)

	for {
		schema, channel, message, nextErr := iterator.NextInto(nil)
		if errors.Is(nextErr, io.EOF) {
			break
		}
		if nextErr != nil {
			return nil, fmt.Errorf("failed while iterating messages: %w", nextErr)
		}

		topic := ""
		if channel != nil {
			topic = channel.Topic
		}

		if topic != "" {
			if _, exists := seenChannels[topic]; !exists {
				seenChannels[topic] = struct{}{}
				channels = append(channels, topic)
			}
		}

		logTime := message.LogTime
		if minLogTime == nil || logTime < *minLogTime {
			value := logTime
			minLogTime = &value
		}
		if maxLogTime == nil || logTime > *maxLogTime {
			value := logTime
			maxLogTime = &value
		}

		if topic != gpsTopic || schema == nil || channel == nil {
			continue
		}

		decoder, decErr := ensureGPSDecoder(gpsDecoders, schema, channel.SchemaID)
		if decErr != nil || decoder == nil {
			continue
		}

		lat, lon, decodeErr := decodeGPS(decoder, message)
		if decodeErr != nil {
			continue
		}

		if lat == 0.0 && lon == 0.0 {
			continue
		}

		if firstLat == nil && firstLon == nil {
			latCopy := lat
			lonCopy := lon
			firstLat = &latCopy
			firstLon = &lonCopy
		}

		point := [2]float64{lon, lat}
		if validGPSCount == 0 || validGPSCount%validStep == 0 {
			allCoordinates = append(allCoordinates, point)
		}
		pointCopy := point
		lastPoint = &pointCopy
		validGPSCount++
	}

	if lastPoint != nil {
		if len(allCoordinates) == 0 || allCoordinates[len(allCoordinates)-1] != *lastPoint {
			allCoordinates = append(allCoordinates, *lastPoint)
		}
	}

	summary := summaryPayload{
		Channels:     channels,
		ChannelCount: len(channels),
		Duration:     0,
		Latitude:     nil,
		Longitude:    nil,
	}

	if minLogTime != nil && maxLogTime != nil {
		start := float64(*minLogTime) / 1_000_000_000.0
		end := float64(*maxLogTime) / 1_000_000_000.0
		duration := end - start
		if duration < 0 {
			duration = 0
		}
		formatted := time.Unix(int64(start), 0).Format("2006-01-02 15:04:05")
		summary.StartTime = &start
		summary.EndTime = &end
		summary.Duration = duration
		summary.FormattedDate = &formatted
	}

	gps := gpsPayload{
		Latitude:       firstLat,
		Longitude:      firstLon,
		AllCoordinates: allCoordinates,
	}

	return &fanoutPayload{
		Summary: summary,
		GPS:     gps,
	}, nil
}

func loadCoords(coordsPath string) ([][2]float64, error) {
	raw, err := os.ReadFile(coordsPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read coords file: %w", err)
	}

	var coords [][2]float64
	if err := json.Unmarshal(raw, &coords); err != nil {
		return nil, fmt.Errorf("failed to decode coords JSON: %w", err)
	}
	return coords, nil
}

func generateMapPreviewSVG(logID int, coords [][2]float64, mediaRoot, mediaURL string) (*mapPreviewPayload, error) {
	if len(coords) < 2 {
		return &mapPreviewPayload{Status: "skipped", URI: nil}, nil
	}

	zoom := pickZoom(coords, previewWidth, previewHeight, previewPadding)
	world := make([][2]float64, 0, len(coords))
	for _, point := range coords {
		x, y := lonLatToWorldPixels(point[0], point[1], zoom)
		world = append(world, [2]float64{x, y})
	}

	minX := world[0][0]
	maxX := world[0][0]
	minY := world[0][1]
	maxY := world[0][1]
	for _, p := range world[1:] {
		if p[0] < minX {
			minX = p[0]
		}
		if p[0] > maxX {
			maxX = p[0]
		}
		if p[1] < minY {
			minY = p[1]
		}
		if p[1] > maxY {
			maxY = p[1]
		}
	}

	pathWidth := math.Max(maxX-minX, 1.0)
	pathHeight := math.Max(maxY-minY, 1.0)
	offsetX := (previewWidth-pathWidth)/2.0 - minX
	offsetY := (previewHeight-pathHeight)/2.0 - minY

	screen := make([][2]float64, 0, len(world))
	for _, p := range world {
		screen = append(screen, [2]float64{p[0] + offsetX, p[1] + offsetY})
	}

	pathD := toSVGPath(screen)
	start := screen[0]
	end := screen[len(screen)-1]

	svg := fmt.Sprintf(
		"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"%.0f\" height=\"%.0f\" viewBox=\"0 0 %.0f %.0f\">"+
			"<rect x=\"0\" y=\"0\" width=\"%.0f\" height=\"%.0f\" fill=\"#f5f2ea\" rx=\"8\" ry=\"8\" />"+
			"<path d=\"%s\" fill=\"none\" stroke=\"#C38822\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\" />"+
			"<circle cx=\"%.2f\" cy=\"%.2f\" r=\"4\" fill=\"#1e7b34\" stroke=\"#ffffff\" stroke-width=\"1.2\" />"+
			"<circle cx=\"%.2f\" cy=\"%.2f\" r=\"4\" fill=\"#a7261c\" stroke=\"#ffffff\" stroke-width=\"1.2\" />"+
			"</svg>",
		previewWidth, previewHeight, previewWidth, previewHeight,
		previewWidth, previewHeight,
		pathD,
		start[0], start[1],
		end[0], end[1],
	)

	dir := filepath.Join(mediaRoot, "map_previews")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("failed to create map preview directory: %w", err)
	}

	filename := fmt.Sprintf("%d.svg", logID)
	filePath := filepath.Join(dir, filename)
	if err := os.WriteFile(filePath, []byte(svg), 0o644); err != nil {
		return nil, fmt.Errorf("failed to write map preview: %w", err)
	}

	mediaPrefix := strings.TrimRight(mediaURL, "/")
	uri := fmt.Sprintf("%s/map_previews/%s", mediaPrefix, filename)
	return &mapPreviewPayload{Status: "completed", URI: &uri}, nil
}

func clampLat(lat float64) float64 {
	return math.Max(math.Min(lat, 85.05112878), -85.05112878)
}

func lonLatToWorldPixels(lon, lat float64, zoom int) (float64, float64) {
	lat = clampLat(lat)
	scale := tileSize * math.Pow(2, float64(zoom))
	x := (lon + 180.0) / 360.0 * scale
	sinLat := math.Sin(lat * math.Pi / 180.0)
	y := (0.5 - math.Log((1+sinLat)/(1-sinLat))/(4*math.Pi)) * scale
	return x, y
}

func pickZoom(coords [][2]float64, width, height, padding float64) int {
	if len(coords) < 2 {
		return 12
	}

	minLon := coords[0][0]
	maxLon := coords[0][0]
	minLat := coords[0][1]
	maxLat := coords[0][1]
	for _, c := range coords[1:] {
		if c[0] < minLon {
			minLon = c[0]
		}
		if c[0] > maxLon {
			maxLon = c[0]
		}
		if c[1] < minLat {
			minLat = c[1]
		}
		if c[1] > maxLat {
			maxLat = c[1]
		}
	}

	usableWidth := math.Max(width-2*padding, 10)
	usableHeight := math.Max(height-2*padding, 10)

	for zoom := 18; zoom > 1; zoom-- {
		minX, minY := lonLatToWorldPixels(minLon, maxLat, zoom)
		maxX, maxY := lonLatToWorldPixels(maxLon, minLat, zoom)
		if (maxX-minX) <= usableWidth && (maxY-minY) <= usableHeight {
			return zoom
		}
	}
	return 2
}

func toSVGPath(points [][2]float64) string {
	if len(points) == 0 {
		return ""
	}
	parts := make([]string, 0, len(points))
	parts = append(parts, fmt.Sprintf("M %.2f %.2f", points[0][0], points[0][1]))
	for _, p := range points[1:] {
		parts = append(parts, fmt.Sprintf("L %.2f %.2f", p[0], p[1]))
	}
	return strings.Join(parts, " ")
}

func ensureGPSDecoder(decoderMap map[uint16]*gpsDecoder, schema *mcap.Schema, schemaID uint16) (*gpsDecoder, error) {
	if decoder, exists := decoderMap[schemaID]; exists {
		return decoder, nil
	}

	decoder, err := buildGPSDecoder(schema)
	if err != nil {
		decoderMap[schemaID] = nil
		return nil, err
	}

	decoderMap[schemaID] = decoder
	return decoder, nil
}

func buildGPSDecoder(schema *mcap.Schema) (*gpsDecoder, error) {
	if schema == nil {
		return nil, errors.New("nil schema")
	}
	if schema.Encoding != "protobuf" {
		return nil, fmt.Errorf("unsupported schema encoding: %s", schema.Encoding)
	}

	fileSet, err := parseFileDescriptorSet(schema.Data)
	if err != nil {
		return nil, fmt.Errorf("failed to parse schema descriptors: %w", err)
	}

	files, err := protodesc.NewFiles(fileSet)
	if err != nil {
		return nil, fmt.Errorf("failed to build descriptor files: %w", err)
	}

	messageDescriptor, err := files.FindDescriptorByName(protoreflect.FullName(schema.Name))
	if err != nil {
		return nil, fmt.Errorf("message descriptor not found: %s", schema.Name)
	}

	message, ok := messageDescriptor.(protoreflect.MessageDescriptor)
	if !ok {
		return nil, fmt.Errorf("descriptor is not a message: %s", schema.Name)
	}

	latitudeField := message.Fields().ByName("evelogger_vectornav_latitude")
	longitudeField := message.Fields().ByName("evelogger_vectornav_longitude")
	if latitudeField == nil || longitudeField == nil {
		return nil, errors.New("GPS latitude/longitude fields not found")
	}

	return &gpsDecoder{
		messageDescriptor: message,
		latitudeField:     latitudeField,
		longitudeField:    longitudeField,
	}, nil
}

func parseFileDescriptorSet(data []byte) (*descriptorpb.FileDescriptorSet, error) {
	fileSet := &descriptorpb.FileDescriptorSet{}
	if err := proto.Unmarshal(data, fileSet); err == nil {
		return fileSet, nil
	}

	fileDescriptor := &descriptorpb.FileDescriptorProto{}
	if err := proto.Unmarshal(data, fileDescriptor); err != nil {
		return nil, err
	}

	return &descriptorpb.FileDescriptorSet{File: []*descriptorpb.FileDescriptorProto{fileDescriptor}}, nil
}

func decodeGPS(decoder *gpsDecoder, message *mcap.Message) (float64, float64, error) {
	dynMessage := dynamicpb.NewMessage(decoder.messageDescriptor)
	if err := proto.Unmarshal(message.Data, dynMessage); err != nil {
		return 0, 0, err
	}

	latitude := dynMessage.Get(decoder.latitudeField)
	longitude := dynMessage.Get(decoder.longitudeField)

	latValue, latErr := protoValueToFloat64(latitude.Interface())
	if latErr != nil {
		return 0, 0, latErr
	}
	lonValue, lonErr := protoValueToFloat64(longitude.Interface())
	if lonErr != nil {
		return 0, 0, lonErr
	}

	return latValue, lonValue, nil
}

func protoValueToFloat64(value interface{}) (float64, error) {
	switch typed := value.(type) {
	case float64:
		if math.IsNaN(typed) || math.IsInf(typed, 0) {
			return 0, errors.New("invalid float64 value")
		}
		return typed, nil
	case float32:
		asFloat := float64(typed)
		if math.IsNaN(asFloat) || math.IsInf(asFloat, 0) {
			return 0, errors.New("invalid float32 value")
		}
		return asFloat, nil
	case int64:
		return float64(typed), nil
	case int32:
		return float64(typed), nil
	case uint64:
		return float64(typed), nil
	case uint32:
		return float64(typed), nil
	default:
		return 0, fmt.Errorf("unsupported numeric type: %T", value)
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err.Error())
	os.Exit(1)
}

func emitJSON(value interface{}) {
	encoded, err := json.Marshal(value)
	if err != nil {
		fail(fmt.Errorf("failed to encode result JSON: %w", err))
	}
	fmt.Println(string(encoded))
}
