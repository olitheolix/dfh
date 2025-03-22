package server

import (
	"fmt"
	"log"

	"github.com/gofiber/fiber/v2"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/watch"
)

type GVKMeta struct {
	Group     string
	Version   string
	Kind      string
	Name      string
	Namespace string
}

type Config struct {
	Value     int64
	WatchCh   chan watch.Event
	Resources map[GVKMeta]runtime.Object
}

type WorkspaceInfo struct {
	Name  string `json:"name"`
	Owner string `json:"owner"`
	Ok    bool   `json:"ok"`
}

type WorkspaceResource struct {
	Group         string `json:"group"`
	Version       string `json:"version"`
	Kind          string `json:"kind"`
	Name          string `json:"name"`
	Namespace     string `json:"namespace"`
	Status        string `json:"status"`
	LinkGCPObject string `json:"linkGCPObject"`
	LinkGCPLogs   string `json:"linkGCPLogs"`
	LinkJSON      string `json:"linkJSON"`
	Ok            bool   `json:"ok"`
}

/* Setup configures the web server. */
func Setup(config Config) *fiber.App {
	app := fiber.New(fiber.Config{})

	// Install a dummy middleware to inject our shared `config` into every
	// request. This avoids singletons in the code base.
	app.Use(func(c *fiber.Ctx) error {
		c.Locals("config", config)
		return c.Next()
	})

	// Configure routes.
	v1 := app.Group("/demo/api/uam/v1/workspaces")
	v1.Get("/health", getHealth)
	v1.Get("/info", getWorkspaceInfo)
	v1.Get("/resources/:name", getWorkspaceResources)
	return app
}

/* Start the server */
func Run(app *fiber.App) {
	log.Fatal(app.Listen(":5001"))
}

/* getHealthz unconditionally returns a 200 response.*/
func getHealth(c *fiber.Ctx) error {
	value := c.Locals("config").(Config)
	resp := fmt.Sprintf("value is %d", value.Value)
	return c.Status(fiber.StatusOK).JSON(resp)
}

func getWorkspaceInfo(c *fiber.Ctx) error {
	dummy := []WorkspaceInfo{
		{
			Name:  "foo",
			Owner: "foo",
			Ok:    true,
		},
		{
			Name:  "bar",
			Owner: "bar",
			Ok:    false,
		},
	}

	return c.Status(fiber.StatusOK).JSON(dummy)
}

func getWorkspaceResources(c *fiber.Ctx) error {
	name := c.Params("name")
	url_with_params := "not-yet-implemented"
	res := []WorkspaceResource{
		{
			Group:         "apps",
			Version:       "v1",
			Kind:          "Deployment",
			Name:          fmt.Sprintf("res-%s", name),
			Namespace:     "default",
			Ok:            true,
			Status:        "Ready",
			LinkGCPObject: "https://example.com/obj",
			LinkGCPLogs:   "https://example.com/log",
			LinkJSON:      url_with_params,
		},
		{
			Group:         "security.istio.io",
			Version:       "v1beta",
			Kind:          "PriorityClass",
			Name:          fmt.Sprintf("res-%s", name),
			Namespace:     "default",
			Ok:            false,
			Status:        "Reconcile error",
			LinkGCPObject: "https://example.com/obj",
			LinkGCPLogs:   "https://example.com/log",
			LinkJSON:      url_with_params,
		},
	}

	for i := range 20000 {
		pp := WorkspaceResource{
			Group:         "iam.cnrm.cloud.google.com",
			Version:       "v1beta",
			Kind:          "IAMPartialPolicy",
			Name:          fmt.Sprintf("policy-%d", i),
			Namespace:     "default",
			Status:        "Reconcile error",
			LinkGCPObject: "https://example.com/obj",
			LinkGCPLogs:   "https://example.com/log",
			LinkJSON:      url_with_params,
			Ok:            (i > 5),
		}
		res = append(res, pp)
	}

	return c.Status(fiber.StatusOK).JSON(res)
}
