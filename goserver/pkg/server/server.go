package server

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

type Repository struct {
	Name string `json:"name"`
}

/* getHealthz unconditionally returns a 200 response.*/
func getHealthz(c *gin.Context) {
	c.JSON(http.StatusOK, nil)
}

/*
getRepositories returns a list of repositories in JSON format.

The repositories are represented by the Repository struct and returns
something like [{"Name": "Repo 1"}, {"Name": "Repo 2"}].

NOTE: the value are currently hard coded for demonstration purposes.
*/
func getRepositories(c *gin.Context) {
	payload := []Repository{
		{Name: "Repo 1"},
		{Name: "Repo 2"},
	}
	c.JSON(http.StatusOK, payload)
}

/*
postRepository creates a new repository.

Returns 400 (Bad Request) if the payload is invalid.
*/
func postRepository(c *gin.Context) {
	var payload Repository
	if err := c.BindJSON(&payload); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, nil)
}

/*
SetupRouter adds the handlers and returns the configured `gin.Engine` routing object.
*/
func SetupRouter() *gin.Engine {
	router := gin.Default()
	router.GET("/healthz", getHealthz)
	router.GET("/repos", getRepositories)
	router.POST("/repos", postRepository)
	return router
}
