package main

import (
	"workspaceApi/pkg/server"
	"workspaceApi/pkg/wswatch"

	"k8s.io/apimachinery/pkg/watch"
)

func main() {
	config := server.Config{Value: 5, WatchCh: make(chan watch.Event)}
	wswatch.Start(config)
	app := server.Setup(config)
	server.Run(app)
}
