package wswatch

import (
	"context"
	"workspaceApi/pkg/server"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/watch"
)

func getGVKMeta(obj runtime.Object) server.GVKMeta {
	// Check if the object is an Unstructured type
	var name, namespace string
	switch T := obj.(type) {
	case *unstructured.Unstructured:
		name, namespace = T.GetName(), T.GetNamespace()
	case metav1.Object:
		name, namespace = T.GetName(), T.GetNamespace()
	default:
		panic("mate, you have a bug")
	}

	gvk := obj.GetObjectKind().GroupVersionKind()
	return server.GVKMeta{
		Group:     gvk.Group,
		Version:   gvk.Version,
		Kind:      gvk.Kind,
		Name:      name,
		Namespace: namespace,
	}
}

func trackWorkspace(ctx context.Context, appCfg server.Config) {
	for {
		select {
		case <-ctx.Done():
			return
		case event, _ := <-appCfg.WatchCh:
			switch event.Type {
			case watch.Added, watch.Modified:
				key := getGVKMeta(event.Object)
				appCfg.Resources[key] = event.Object
			case watch.Deleted:
				key := getGVKMeta(event.Object)
				delete(appCfg.Resources, key)
			}
		}
	}
}
