package http

import (
	"encoding/json"
	"net/http"
)

type HandlerFunc func(w http.ResponseWriter, r *http.Request) *HandlerError

type HandlerError struct {
	Message    string `json:"message"`
	StatusCode int    `json:"-"`
}

func NewHandlerError(message string, code int) *HandlerError {
	return &HandlerError{Message: message, StatusCode: code}
}

func (fn HandlerFunc) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if handlerError := fn(w, r); handlerError != nil {
		handleHTTPError(w, *handlerError)
	}
}

func handleHTTPError(w http.ResponseWriter, err HandlerError) {
	writeJSON(w, err.StatusCode, map[string]any{
		"data":    []any{},
		"message": err.Message,
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
