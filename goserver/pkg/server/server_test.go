package server

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGetHealthz(t *testing.T) {
	// Boiler plate setup.
	router := SetupRouter()
	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/healthz", nil)
	router.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
}

func TestGetRepositories(t *testing.T) {
	// Boiler plate setup.
	router := SetupRouter()
	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/repos", nil)
	router.ServeHTTP(w, req)

	// Request must succeed and have the expected payload type.
	assert.Equal(t, http.StatusOK, w.Code)
	var payload []Repository
	err := json.Unmarshal(w.Body.Bytes(), &payload)
	assert.NoError(t, err)

	// Must have returned a list of repos.
	assert.Equal(t, len(payload), 2)
	assert.Equal(t, payload[0].Name, "Repo 1")
	assert.Equal(t, payload[1].Name, "Repo 2")
}

func TestPostRepository(t *testing.T) {
	tests := []struct {
		name    string
		payload any
		isValid bool
	}{
		{name: "valid POST /repos", payload: Repository{Name: "New Repo"}, isValid: true},
		{name: "invalid POST /repos", payload: "invalid payload", isValid: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var buf bytes.Buffer
			err := json.NewEncoder(&buf).Encode(tt.payload)
			assert.NoError(t, err)

			// Boiler plate setup.
			router := SetupRouter()
			w := httptest.NewRecorder()
			req, _ := http.NewRequest(http.MethodPost, "/repos", &buf)
			router.ServeHTTP(w, req)

			// Request must succeed.
			if tt.isValid {
				assert.Equal(t, http.StatusOK, w.Code)
			} else {
				assert.Equal(t, http.StatusBadRequest, w.Code)
			}
		})
	}
}
