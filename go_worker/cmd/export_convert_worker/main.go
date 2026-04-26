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
	"sync"

	"github.com/foxglove/mcap/go/mcap"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protodesc"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/descriptorpb"
	"google.golang.org/protobuf/types/dynamicpb"
)

type sample struct {
	Timestamp float64
	Channel   string
	Value     float64
}

type channelSample struct {
	Timestamp float64
	Value     float64
}

type channelData struct {
	Name     string
	Messages []channelSample
}

type dataLog struct {
	Order    []string
	Channels map[string]*channelData
}

func newDataLog() *dataLog {
	return &dataLog{Order: make([]string, 0), Channels: make(map[string]*channelData)}
}

func (d *dataLog) addSample(name string, timestamp float64, value float64) {
	channel := d.Channels[name]
	if channel == nil {
		channel = &channelData{Name: name, Messages: make([]channelSample, 0, 128)}
		d.Channels[name] = channel
		d.Order = append(d.Order, name)
	}
	channel.Messages = append(channel.Messages, channelSample{Timestamp: timestamp, Value: value})
}

func (d *dataLog) start() float64 {
	minStart := math.Inf(1)
	for _, name := range d.Order {
		msgs := d.Channels[name].Messages
		if len(msgs) == 0 {
			continue
		}
		if msgs[0].Timestamp < minStart {
			minStart = msgs[0].Timestamp
		}
	}
	if math.IsInf(minStart, 1) {
		return 0
	}
	return minStart
}

func (d *dataLog) end() float64 {
	maxEnd := 0.0
	for _, name := range d.Order {
		msgs := d.Channels[name].Messages
		if len(msgs) == 0 {
			continue
		}
		last := msgs[len(msgs)-1].Timestamp
		if last > maxEnd {
			maxEnd = last
		}
	}
	return maxEnd
}

func (d *dataLog) resample(freqHz float64) error {
	if freqHz <= 0 {
		return errors.New("resample-hz must be > 0")
	}
	start := d.start()
	end := d.end()
	for _, name := range d.Order {
		channel := d.Channels[name]
		resampled, err := resampleChannel(channel.Messages, start, end, freqHz)
		if err != nil {
			return err
		}
		channel.Messages = resampled
	}
	return nil
}

func resampleChannel(messages []channelSample, start, end, freqHz float64) ([]channelSample, error) {
	if len(messages) == 0 {
		return messages, nil
	}
	if freqHz <= 0 {
		return nil, errors.New("frequency_hz must be > 0")
	}
	dtStep := 1.0 / freqHz
	numMsgs := int(math.Floor(freqHz*(end-start))) + 1
	if numMsgs < 1 {
		numMsgs = 1
	}

	value := 0.0
	idx := 0
	t := start
	out := make([]channelSample, 0, numMsgs+1)
	for i := 0; i < numMsgs; i++ {
		for idx < len(messages) {
			stamp := messages[idx].Timestamp
			if stamp < t+0.5*dtStep {
				value = messages[idx].Value
				idx++
			} else {
				break
			}
		}
		out = append(out, channelSample{Timestamp: t, Value: value})
		t += dtStep
	}
	if out[len(out)-1].Timestamp < end {
		out = append(out, channelSample{Timestamp: end, Value: value})
	}
	return out, nil
}

type publisher struct {
	mu          sync.Mutex
	subscribers []chan sample
}

func newPublisher() *publisher {
	return &publisher{subscribers: make([]chan sample, 0)}
}

func (p *publisher) subscribe(buffer int) <-chan sample {
	ch := make(chan sample, buffer)
	p.mu.Lock()
	p.subscribers = append(p.subscribers, ch)
	p.mu.Unlock()
	return ch
}

func (p *publisher) publish(msg sample) {
	p.mu.Lock()
	subs := append([]chan sample(nil), p.subscribers...)
	p.mu.Unlock()
	for _, ch := range subs {
		ch <- msg
	}
}

func (p *publisher) close() {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, ch := range p.subscribers {
		close(ch)
	}
}

type schemaDecoder struct {
	msgDesc protoreflect.MessageDescriptor
}

type formatArtifact struct {
	Status     string `json:"status"`
	OutputPath string `json:"output_path,omitempty"`
	Error      string `json:"error,omitempty"`
}

type allFormatsResponse struct {
	Formats map[string]formatArtifact `json:"formats"`
}

func main() {
	source := flag.String("source", "", "source MCAP file path")
	output := flag.String("output", "", "output file path")
	outputDir := flag.String("output-dir", "", "output directory for format=all")
	baseName := flag.String("base-name", "", "base filename for format=all")
	format := flag.String("format", "h5", "format: h5|all")
	resampleHz := flag.Float64("resample-hz", 20.0, "resample frequency")
	flag.Parse()

	if strings.TrimSpace(*source) == "" {
		fail(errors.New("--source is required"))
	}
	mode := strings.ToLower(strings.TrimSpace(*format))
	if mode != "h5" && mode != "all" {
		fail(fmt.Errorf("unsupported --format: %s", mode))
	}

	if mode == "all" {
		if strings.TrimSpace(*outputDir) == "" || strings.TrimSpace(*baseName) == "" {
			fail(errors.New("--output-dir and --base-name are required for --format all"))
		}
		response, err := convertAllFormats(*source, *outputDir, *baseName, *resampleHz)
		if err != nil {
			fail(err)
		}
		encoded, err := json.Marshal(response)
		if err != nil {
			fail(err)
		}
		fmt.Println(string(encoded))
		return
	}

	if strings.TrimSpace(*output) == "" {
		fail(errors.New("--output is required for single-format conversion"))
	}

	datalog, err := decodeWithPubSub(*source)
	if err != nil {
		fail(err)
	}
	if len(datalog.Order) == 0 {
		fail(errors.New("no numeric scalar protobuf fields found in MCAP"))
	}
	if err := datalog.resample(*resampleHz); err != nil {
		fail(err)
	}

	if err := os.MkdirAll(filepath.Dir(*output), 0o755); err != nil {
		fail(err)
	}

	var writeErr error
	switch mode {
	case "h5":
		writeErr = writeH5(*output, datalog)
	}
	if writeErr != nil {
		fail(writeErr)
	}
}

func convertAllFormats(sourcePath, outputDir, baseName string, resampleHz float64) (*allFormatsResponse, error) {
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return nil, err
	}

	formats := []string{"h5"}
	pub := newPublisher()
	results := make(chan struct {
		format string
		result formatArtifact
	}, len(formats))

	var wg sync.WaitGroup
	for _, formatName := range formats {
		formatName := formatName
		sub := pub.subscribe(4096)
		wg.Add(1)
		go func() {
			defer wg.Done()
			d := newDataLog()
			for msg := range sub {
				d.addSample(msg.Channel, msg.Timestamp, msg.Value)
			}

			artifact := formatArtifact{}
			outputPath := outputPathForFormat(outputDir, baseName, formatName)
			if len(d.Order) == 0 {
				artifact.Status = "failed"
				artifact.Error = "no numeric scalar protobuf fields found in MCAP"
				results <- struct {
					format string
					result formatArtifact
				}{format: formatName, result: artifact}
				return
			}

			if err := d.resample(resampleHz); err != nil {
				artifact.Status = "failed"
				artifact.Error = err.Error()
				results <- struct {
					format string
					result formatArtifact
				}{format: formatName, result: artifact}
				return
			}

			var writeErr error
			switch formatName {
			case "h5":
				writeErr = writeH5(outputPath, d)
			}

			if writeErr != nil {
				artifact.Status = "failed"
				artifact.Error = writeErr.Error()
			} else {
				artifact.Status = "completed"
				artifact.OutputPath = outputPath
			}

			results <- struct {
				format string
				result formatArtifact
			}{format: formatName, result: artifact}
		}()
	}

	streamErr := streamSamples(sourcePath, pub)
	pub.close()
	wg.Wait()
	close(results)

	out := &allFormatsResponse{Formats: map[string]formatArtifact{}}
	for item := range results {
		out.Formats[item.format] = item.result
	}
	if streamErr != nil {
		return out, streamErr
	}
	return out, nil
}

func outputPathForFormat(outputDir, baseName, formatName string) string {
	ext := "h5"
	filename := fmt.Sprintf("%s_%s.%s", baseName, formatName, ext)
	return filepath.Join(outputDir, filename)
}

func decodeWithPubSub(path string) (*dataLog, error) {
	pub := newPublisher()
	sampleCh := pub.subscribe(2048)

	var wg sync.WaitGroup
	resultCh := make(chan *dataLog, 1)
	wg.Add(1)
	go func() {
		defer wg.Done()
		d := newDataLog()
		for msg := range sampleCh {
			d.addSample(msg.Channel, msg.Timestamp, msg.Value)
		}
		resultCh <- d
	}()

	streamErr := streamSamples(path, pub)
	pub.close()
	wg.Wait()
	if streamErr != nil {
		return nil, streamErr
	}

	result := <-resultCh
	return result, nil
}

func streamSamples(path string, pub *publisher) error {
	fh, err := os.Open(path)
	if err != nil {
		return err
	}
	defer fh.Close()

	reader, err := mcap.NewReader(fh)
	if err != nil {
		return err
	}
	iter, err := reader.Messages()
	if err != nil {
		return err
	}

	decoders := make(map[uint16]*schemaDecoder)
	for {
		schema, channel, message, nextErr := iter.NextInto(nil)
		if errors.Is(nextErr, io.EOF) {
			break
		}
		if nextErr != nil {
			return nextErr
		}
		if schema == nil || channel == nil || schema.Encoding != "protobuf" {
			continue
		}

		decoder, err := getSchemaDecoder(decoders, schema, channel.SchemaID)
		if err != nil || decoder == nil {
			continue
		}

		dyn := dynamicpb.NewMessage(decoder.msgDesc)
		if err := proto.Unmarshal(message.Data, dyn); err != nil {
			continue
		}

		timestamp := float64(message.LogTime) / 1_000_000_000.0
		topic := strings.TrimSpace(channel.Topic)
		if topic == "" {
			continue
		}

		dyn.ProtoReflect().Range(func(fd protoreflect.FieldDescriptor, val protoreflect.Value) bool {
			if fd.Cardinality() == protoreflect.Repeated || fd.Kind() == protoreflect.MessageKind {
				return true
			}
			floatValue, ok := scalarToFloat(val.Interface())
			if !ok {
				return true
			}
			channelName := topic + "." + string(fd.Name())
			pub.publish(sample{Timestamp: timestamp, Channel: channelName, Value: floatValue})
			return true
		})
	}

	return nil
}

func getSchemaDecoder(cache map[uint16]*schemaDecoder, schema *mcap.Schema, schemaID uint16) (*schemaDecoder, error) {
	if decoder, ok := cache[schemaID]; ok {
		return decoder, nil
	}

	fileSet, err := parseFileDescriptorSet(schema.Data)
	if err != nil {
		cache[schemaID] = nil
		return nil, err
	}
	files, err := protodesc.NewFiles(fileSet)
	if err != nil {
		cache[schemaID] = nil
		return nil, err
	}
	desc, err := files.FindDescriptorByName(protoreflect.FullName(schema.Name))
	if err != nil {
		cache[schemaID] = nil
		return nil, err
	}
	msgDesc, ok := desc.(protoreflect.MessageDescriptor)
	if !ok {
		cache[schemaID] = nil
		return nil, fmt.Errorf("schema %s is not a message", schema.Name)
	}

	decoder := &schemaDecoder{msgDesc: msgDesc}
	cache[schemaID] = decoder
	return decoder, nil
}

func parseFileDescriptorSet(data []byte) (*descriptorpb.FileDescriptorSet, error) {
	set := &descriptorpb.FileDescriptorSet{}
	if err := proto.Unmarshal(data, set); err == nil {
		return set, nil
	}
	file := &descriptorpb.FileDescriptorProto{}
	if err := proto.Unmarshal(data, file); err != nil {
		return nil, err
	}
	return &descriptorpb.FileDescriptorSet{File: []*descriptorpb.FileDescriptorProto{file}}, nil
}

func scalarToFloat(value interface{}) (float64, bool) {
	switch v := value.(type) {
	case bool:
		if v {
			return 1.0, true
		}
		return 0.0, true
	case int32:
		return float64(v), true
	case int64:
		return float64(v), true
	case uint32:
		return float64(v), true
	case uint64:
		return float64(v), true
	case float32:
		if math.IsNaN(float64(v)) || math.IsInf(float64(v), 0) {
			return 0, false
		}
		return float64(v), true
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return 0, false
		}
		return v, true
	default:
		return 0, false
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err.Error())
	os.Exit(1)
}
