#!/bin/bash

set -e

KUBECONFIG=/tmp/kind-kubeconf.yaml

# ------------------------------------------------------------------------------
#                            Bootstrap Kind Cluster
# ------------------------------------------------------------------------------
KINDCONFIG=/tmp/kind-config.yaml

# Create a KinD configuration file.
cat << EOF > $KINDCONFIG
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  image: kindest/node:v1.29.8@sha256:d46b7aa29567e93b27f7531d258c372e829d7224b25e3fc6ffdefed12476d3aa
EOF

# Create cluster, then delete its config file.
kind delete cluster
kind create cluster --config $KINDCONFIG --kubeconfig $KUBECONFIG
rm $KINDCONFIG

# ------------------------------------------------------------------------------
#                          Deploy The Demo Resources
# ------------------------------------------------------------------------------
printf "### Deploy test resources into the cluster:\n"

# Install Istio.
istio-1.23.2/bin/istioctl install --kubeconfig $KUBECONFIG --skip-confirmation --verify

kubectl --kubeconfig $KUBECONFIG label namespace default istio-injection=enabled

# Apply the resource manifests until KinD accepts all of them. This may take a
# few iterations because some resources, in particular CRDs, may require some
# time to boot before they expose their new API endpoints.
while true; do
    # Deploy the manifests.
    kubectl --kubeconfig $KUBECONFIG apply -f ./

    # Keep trying until the command succeeded.
    if [ $? == 0 ]; then break; fi
    printf "\n   # Retry deployment...\n"
    sleep 1
done
set -e
printf "done\n"

printf "\n\n### KIND cluster now fully deployed (KUBECONF=$KUBECONFIG)\n"
