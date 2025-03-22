package server

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"testing"

	"github.com/gofiber/fiber/v2"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func getApp() *fiber.App {
	return Setup(Config{Value: 5})
}

func unpackResponse[T any](t *testing.T, got *http.Response) T {
	defer got.Body.Close()
	body, err := io.ReadAll(got.Body)
	assert.NoError(t, err)

	var gotData T
	err = json.Unmarshal(body, &gotData)
	assert.NoError(t, err)
	return gotData
}

func TestGetHealth(t *testing.T) {
	app := getApp()
	req, _ := http.NewRequest("GET", "/demo/api/uam/v1/workspaces/health", nil)
	got, err := app.Test(req, -1)
	assert.NoError(t, err)
	assert.Equal(t, fiber.StatusOK, got.StatusCode)
}

func TestGetWorkspaces(t *testing.T) {
	app := getApp()
	req, _ := http.NewRequest("GET", "/demo/api/uam/v1/workspaces/info", nil)
	resp, err := app.Test(req, -1)
	assert.NoError(t, err)
	assert.Equal(t, fiber.StatusOK, resp.StatusCode)

	got := unpackResponse[[]WorkspaceInfo](t, resp)
	assert.NoError(t, err)
	assert.Equal(t, 2, len(got))
}

func TestGetResources(t *testing.T) {
	app := getApp()

	for _, name := range []string{"foo", "bar"} {
		url := fmt.Sprintf("/demo/api/uam/v1/workspaces/resources/%s", name)
		req, _ := http.NewRequest("GET", url, nil)
		resp, err := app.Test(req, -1)
		assert.NoError(t, err)
		assert.Equal(t, fiber.StatusOK, resp.StatusCode)

		got := unpackResponse[[]WorkspaceResource](t, resp)
		require.Equal(t, 20002, len(got))
		assert.Equal(t, fmt.Sprintf("res-%s", name), got[0].Name)
	}
}
