package wswatch

import (
	"context"
	"testing"
	"time"
	"workspaceApi/pkg/server"

	"github.com/stretchr/testify/assert"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/dynamic/fake"
)

func makeAppConfig() server.Config {
	return server.Config{Value: 5, WatchCh: make(chan watch.Event),
		Resources: make(map[server.GVKMeta]runtime.Object)}
}

func TestWatchResource(t *testing.T) {
	appCfg := makeAppConfig()
	client := fake.NewSimpleDynamicClient(runtime.NewScheme())
	fakeWatcher := watch.NewFake()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	gvk := schema.GroupVersionKind{
		Group:   "example.com",
		Version: "v1",
		Kind:    "ResourceA",
	}
	gvr := schema.GroupVersionResource{
		Group:    gvk.Group,
		Version:  gvk.Version,
		Resource: "ResourceA",
	}

	go watchResource(ctx, appCfg, client, gvr, fakeWatcher)

	obj := &unstructured.Unstructured{}
	obj.SetGroupVersionKind(gvk)
	fakeWatcher.Add(obj)

	// WatchCRD must have put our fake event into the channel.
	time.Sleep(50 * time.Millisecond)
	select {
	case got := <-appCfg.WatchCh:
		assert.Equal(t, watch.EventType("ADDED"), got.Type)
		assert.Equal(t, obj, got.Object)
	default:
		assert.FailNow(t, "empty channel")
	}

	// End the watch. This will close the result channel of the watcher.
	fakeWatcher.Stop()
}

func TestCreateResourceWatch(t *testing.T) {
	appCfg := makeAppConfig()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	client := fake.NewSimpleDynamicClient(runtime.NewScheme())

	gvk := schema.GroupVersionKind{
		Group:   "example.com",
		Version: "v1",
		Kind:    "ResourceA",
	}
	gvr := schema.GroupVersionResource{
		Group:    gvk.Group,
		Version:  gvk.Version,
		Resource: "ResourceA",
	}

	watchCRD := func(ctx context.Context, appCfg server.Config, _client dynamic.Interface, _gvr schema.GroupVersionResource, _watcher watch.Interface) {
		assert.Equal(t, gvr, _gvr)
		assert.Equal(t, client, _client)
	}

	createResourceWatch(ctx, appCfg, client, gvr, watchCRD)
}
