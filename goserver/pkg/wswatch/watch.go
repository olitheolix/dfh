package wswatch

import (
	"context"
	"log"

	"k8s.io/apimachinery/pkg/watch"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"workspaceApi/pkg/server"

	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	ctrl "sigs.k8s.io/controller-runtime"
)

func Start(appCfg server.Config) {
	ctx := context.Background()

	// Create Kubernetes client.
	client, err := dynamic.NewForConfig(ctrl.GetConfigOrDie())
	if err != nil {
		log.Fatalf("Failed to create Kubernetes client: %v", err)
	}

	// Setup the watch for resource.
	gvrs := []schema.GroupVersionResource{
		{Group: "apps", Version: "v1", Resource: "deployments"},
		{Group: "", Version: "v1", Resource: "namespaces"},
		{Group: "networking.istio.io", Version: "v1", Resource: "virtualservices"},
	}

	for _, gvr := range gvrs {
		createResourceWatch(ctx, appCfg, client, gvr, watchResource)
	}
}

type funcWatchResource func(ctx context.Context, appCfg server.Config, client dynamic.Interface, gvr schema.GroupVersionResource, watcher watch.Interface)

func createResourceWatch(ctx context.Context, appCfg server.Config, client dynamic.Interface, gvr schema.GroupVersionResource, watchCRD funcWatchResource) {
	// Construct a K8s resource client for the specified K8s resource we
	// want to watch.
	resource := client.Resource(gvr)
	watcher, err := resource.Watch(ctx, metav1.ListOptions{})
	if err != nil {
		log.Fatalf("Failed to watch ResourceA: %v", err)
	}

	// Start watching
	go watchCRD(ctx, appCfg, client, gvr, watcher)
}

func watchResource(ctx context.Context, appCfg server.Config, client dynamic.Interface, gvr schema.GroupVersionResource, watcher watch.Interface) {
	for {
		select {
		case <-ctx.Done():
			log.Printf("Stopping watch for %s", gvr)
			return
		case event, ok := <-watcher.ResultChan():
			if !ok {
				log.Printf("Watch channel closed for %s", gvr)
				return
			}
			appCfg.WatchCh <- event
		}
	}
}
