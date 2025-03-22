package wswatch

import (
	"context"
	"io/ioutil"
	"testing"
	"workspaceApi/pkg/server"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/util/yaml"
	"k8s.io/apimachinery/pkg/watch"
)

func makeVirtSvc(t *testing.T) *unstructured.Unstructured {
	// Read the file content
	yamlData, err := ioutil.ReadFile("testData/virtual-service.yaml")
	require.NoError(t, err)

	// Convert the YAML data to an unstructured object
	var obj map[string]interface{}
	err = yaml.Unmarshal(yamlData, &obj)
	require.NoError(t, err)

	// Create an unstructured object from the map
	return &unstructured.Unstructured{Object: obj}
}

func makeNamespace() *corev1.Namespace {
	ns := corev1.Namespace{ObjectMeta: metav1.ObjectMeta{Name: "my-namespace"}}
	ns.SetGroupVersionKind(schema.GroupVersionKind{Group: "", Version: "v1", Kind: "Namespace"})
	return &ns
}

func makeDeployment() *appsv1.Deployment {
	return &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-deployment",
			Namespace: "default",
		},
		Spec: appsv1.DeploymentSpec{
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{"app": "my-app"},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{"app": "my-app"},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:  "my-container",
							Image: "nginx:latest",
						},
					},
				},
			},
		},
	}
}

func Test_getGVKMetadat(t *testing.T) {
	tests := []struct {
		name string
		obj  runtime.Object
		want server.GVKMeta
	}{
		{
			name: "Unstructured Object",
			obj:  makeVirtSvc(t),
			want: server.GVKMeta{
				Group:     "networking.istio.io",
				Version:   "v1",
				Kind:      "VirtualService",
				Name:      "my-virtualservice",
				Namespace: "default",
			},
		},
		{
			name: "Structured Object",
			obj:  makeNamespace(),
			want: server.GVKMeta{
				Group:     "",
				Version:   "v1",
				Kind:      "Namespace",
				Name:      "my-namespace",
				Namespace: "",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := getGVKMeta(tt.obj)
			assert.Equal(t, tt.want, got)
		})
	}
}

func Test_trackWorkspace(t *testing.T) {
	appCfg := makeAppConfig()
	namespace := makeNamespace()
	deployment := makeDeployment()
	virtSvc := makeVirtSvc(t)

	// Start tracker.
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go trackWorkspace(ctx, appCfg)

	// Simulate object creation.
	appCfg.WatchCh <- watch.Event{Type: watch.Added, Object: namespace}
	appCfg.WatchCh <- watch.Event{Type: watch.Added, Object: deployment}
	appCfg.WatchCh <- watch.Event{Type: watch.Added, Object: virtSvc}

	assert.Equal(t, namespace, appCfg.Resources[getGVKMeta(namespace)])
	assert.Equal(t, deployment, appCfg.Resources[getGVKMeta(deployment)])
	assert.Equal(t, virtSvc, appCfg.Resources[getGVKMeta(virtSvc)])

	// Simulate an update to the namespace.
	namespace.ObjectMeta.Labels = map[string]string{"foo": "bar"}
	appCfg.WatchCh <- watch.Event{Type: watch.Modified, Object: namespace}
	assert.Equal(t, namespace, appCfg.Resources[getGVKMeta(namespace)])

	// Simulate the removal of the Deployment (must be idempotent).
	_, exists := appCfg.Resources[getGVKMeta(deployment)]
	assert.True(t, exists)
	for _ = range 2 {
		appCfg.WatchCh <- watch.Event{Type: watch.Deleted, Object: deployment}
		_, exists = appCfg.Resources[getGVKMeta(deployment)]
		assert.False(t, exists)
	}

	// Nothing bad must happen if we remove a non-existing object.
	// appCfg.Resources["gvkplus"] = obj
	// appCfg.Workspace["olix"].Resources["gvkplus"] = true
	// appCfg.Workspace["olix"].Info = WorkspaceInfo{}

	// // How to compile the info returned by `getWorkspaceInfo` endpoint?
	// info := []WorkspaceInfo{}
	// for name, res := range appCfg.Workspace {
	// 	info = append(info, res.Info)
	// }

	// res := []WorkspaceResource{}
	// for extgvk, res := range appCfg.Workspace["olix"] {
	// 	res = append(res, res)
	// }

}
