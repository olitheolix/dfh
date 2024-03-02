package main

import "workspaceApi/pkg/server"

func main() {
	router := server.SetupRouter()
	router.Run("0.0.0.0:5002")
}
