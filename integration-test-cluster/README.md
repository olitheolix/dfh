Download Istio as per the [official docs](https://istio.io/latest/docs/setup/getting-started/):

    curl -L https://istio.io/downloadIstio | sh -

Then start the integration test cluster with

    ./start_cluster.sh

This will produce a kubeconfig file `/tmp/kube-kubeconfig.yaml`. Use it to
connect to the cluster as usual, eg

    kubectl --kubeconfig /tmp/kind-kubeconf.yaml
