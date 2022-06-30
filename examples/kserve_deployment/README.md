# 🚀 KServe Deployment Example - Sickit-Learn and Pytorch Examples 🚀

[KServe](https://kserve.github.io/website) is a Kubernetes-based model inference platform
built for highly scalable deployment use cases. It provides a standardized inference protocol 
across ML frameworks while supporting a serverless architecture with autoscaling including Scale to Zero on GPUs.
KServe uses a simple and pluggable production serving architecture for production ML serving that includes 
prediction, pre-/post-processing, monitoring and explainability.

Following the model deployment story within ZenML, and to make it easier to deploy models with other serving tools, 
we have created an Integration for KServe. But how does KServe differ from the already integrated [Seldon Core](../seldon_deployment/)?
* __**Supported frameworks**__: Standards ML frameworks like TensorFlow, PyTorch, Scikit-learn, XGBoost, Keras, MXNet, etc... Are First-class citizens in KServe and can be fairly easily used
while Seldon Core has support for the majority of these ML frameworks, it lacks support for: Pytorch even tho it could be still used using the custom deployment, but that's some extra work to handle.
* __**Custom Deployment**__: Both Seldon Core and KServe have support for custom deployment.
However Seldon Core offers an extra inference graph that includes custom TRANSFORMER and ROUTER which can be used to build more powerful inference graphs.
* __**Autoscaling**__: KServe has more advanced autoscaling features than Seldon Core.
With the Knative autoscaling, it is possible to scale up and down the number of replicas of the model deployment based on the number of requests received.
* __**Predictions interfaces**__: Seldon Core and KServe have built-in support for HTTP-based protocols, However only Seldon Core has support for GRPC-based protocols. While it still can be configured for KServe it requires using manual, custom deployment.

Now that we have a clear understanding of the different features of KServe compared to Seldon Core, we will go through the deployment process of the model with KServe and focus more on how to deploy the PyTorch model.
## 🗺 Overview

The example uses the [digits dataset](https://keras.io/api/datasets/mnist/) 
to train a classifier using both [TensorFlow](https://www.tensorflow.org/)
and [PyTorch](https://pytorch.org/).
Different hyperparameter values (e.g. the number of epochs and learning rate) 
can be supplied as command-line arguments to the `run.py` Python script. 

The example contains three pipelines:
* `pytorch_training_deployment_pipeline`: trains a classifier using TensorFlow and deploys it to KServe with the TFServing Runtime Server.
* `tensorflow_training_deployment_pipeline`: trains a classifier using PyTorch and deploys it to KServe with TorchServe Runtime Server.
* `inference_pipeline`: runs predictions on the served models.

Running the pipelines to train the classifiers and then deploying them to 
KServe requires preparing them into an exact format that is expected 
by the runtime server, storing them into remote storage or a persistent volume 
in the cluster and giving the path to KServe as the model uri with the right permissions. 
By default, ZenML's KServe integration will try to handle that for you 
by automatically loading, preparing and then saving files to the Artifact Store 
active in the ZenML stack. However, for some frameworks (e.g. PyTorch) you will still need 
to provide some additional files that Runtime Server needs to be able to run the model. 

The KServe deployment server is provisioned remotely as a Kubernetes
resource that continues to run after the deployment pipeline run is complete.
Subsequent runs of the deployment pipeline will reuse the existing deployment
server and merely update it to serve the more recent model version.

The deployment pipeline has caching enabled to avoid re-training and
re-deploying the model if the training data and hyperparameter values don't
change. When a new model is trained that passes the accuracy threshold
validation, the pipeline automatically updates the currently running KServe
deployment server so that the new model is being served instead of the old one.

The inference pipeline loads the image from the local filesystem and performs 
online predictions on the running KServe inference service.


# 🖥 Local Stack

### 📄 Prerequisites 

For the ZenML KServe deployer to work, these things are required:
1. Access to a running [Kubernetes cluster](https://kubernetes.io/docs/tutorials/cluster-administration/). The example accepts a `--kubernetes-context` command-line argument. This Kubernetes context needs to point to the Kubernetes cluster where KServe model servers will be deployed. If the context is not explicitly supplied to the example, it defaults to using the locally active context.

2. KServe must be installed and running on the Kubernetes cluster (More information about how to install KServe can be found below or on the [KServe documentation](https://kserve.github.io/website/)).

3. KServe must be able to access whatever storage is used by ZenML to save the artifact. Since  KServe is installed in the Kubernetes cluster, local filesystem storage can't be used. We recommend using a persistent volume or a remote storage service. (e.g. AWS S3, GCS, Azure Blob Storage, etc.).

To run this example, you need to install and initialize ZenML:

```shell
# install CLI
pip install zenml

# install ZenML integrations
zenml integration install pytorch tensorflow kserve

# pull example
zenml example pull kserve_deployment
cd zenml_examples/kserve_deployment

# initialize a local ZenML Repository
zenml init
```

### Installing KServe (e.g. in an GKE cluster)

This section is a trimmed-up version of the serverless installation guide for KServe,
[official KServe installation instructions](https://kserve.github.io/website/0.8/admin/serverless/#recommended-version-matrix), applied to a particular type of Kubernetes cluster, GKE in this case. It assumes that a GKE cluster is already set up and accessible.

To configure GKE cluster access locally, e.g:

```bash
gcloud container clusters get-credentials KUBERNETES_CLUSTER_NAME --zone ZONE --project PROJECT_ID
```

1. Install Istio:

We need to download [istioctl](https://istio.io/latest/docs/setup/getting-started/#download) 
Install Istio v1.12.1 (required for the latest KServe version):

```bash
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.12.1  sh -
cd istio-1.12.1
export PATH=$PWD/bin:$PATH
# Installing Istio without sidecar injection
istioctl install -y
```

2. Installing the Knative Serving component:

```bash
# Install the required custom resources
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.5.0/serving-crds.yaml
# Install the core components of Knative Serving
kubectl apply -f https://github.com/knative/serving/releases/download/knative-v1.5.0/serving-core.yaml
```

Install an Istio networking layer:

```bash
# Install a properly configured Istio
kubectl apply -l knative.dev/crd-install=true -f https://github.com/knative/net-istio/releases/download/knative-v1.5.0/istio.yaml
kubectl apply -f https://github.com/knative/net-istio/releases/download/knative-v1.5.0/istio.yaml
# Install the Knative Istio controller
kubectl apply -f https://github.com/knative/net-istio/releases/download/knative-v1.5.0/net-istio.yaml
# Fetch the External IP address or CNAME
kubectl --namespace istio-system get service istio-ingressgateway
```

Verify the installation:

```bash
kubectl get pods -n knative-serving

"""
activator-59bff9d7c8-2mgdv               1/1     Running     0          11h
autoscaler-c574c9455-x7rfn               1/1     Running     0          3d
controller-59f84c584-mm4pp               1/1     Running     0          3d
domain-mapping-75c659dbc7-hbgnl          1/1     Running     0          3d
domainmapping-webhook-6d9f5996f9-hcvcb   1/1     Running     0          3d
net-istio-controller-76bf75d78f-652fm    1/1     Running     0          11h
net-istio-webhook-9bdb8c6b9-nzf86        1/1     Running     0          11h
webhook-756688c869-79pqh                 1/1     Running     0          2d22h
"""
```
3. Install Cert Manager:

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.8.0/cert-manager.yaml
```

4. Finally, install KServe:

```bash
# Install KServe
kubectl apply -f https://github.com/kserve/kserve/releases/download/v0.8.0/kserve.yaml
# Install KServe Built-in ClusterServingRuntimes
kubectl apply -f https://github.com/kserve/kserve/releases/download/v0.8.0/kserve-runtimes.yaml
```

### Testing the KServe deployment

To test that the installation is functional, you can use this sample KServe
deployment:

1. Create a namespace:

```bash
kubectl create namespace kserve-test
```

2. Create an InferenceService:

```bash
kubectl apply -n kserve-test -f - <<EOF
apiVersion: "serving.kserve.io/v1beta1"
kind: "InferenceService"
metadata:
  name: "sklearn-iris"
spec:
  predictor:
    model:
      modelFormat:
        name: sklearn
      storageUri: "gs://kfserving-examples/models/sklearn/1.0/model"
EOF
```

3. Check InferenceService status:

```bash
kubectl get inferenceservices sklearn-iris -n kserve-test

"""
NAME           URL                                                 READY   PREV   LATEST   PREVROLLEDOUTREVISION   LATESTREADYREVISION                    AGE
sklearn-iris   http://sklearn-iris.kserve-test.example.com         True           100                              sklearn-iris-predictor-default-47q2g   7d23h
"""
```

4. Determine the ingress IP and ports:

```bash
$ kubectl get svc istio-ingressgateway -n istio-system
NAME                   TYPE           CLUSTER-IP       EXTERNAL-IP      PORT(S)   AGE
istio-ingressgateway   LoadBalancer   172.21.109.129   130.211.10.121   ...       17h
```

Extract the HOST and PORT where the model server exposes its prediction API:

```bash
# For GKE clusters, the host is the GKE cluster IP address.
export INGRESS_HOST=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
# For EKS clusters, the host is the EKS cluster IP hostname.
export INGRESS_HOST=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

export INGRESS_PORT=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.spec.ports[?(@.name=="http2")].port}')

```

5. Perform inference

Prepare your inference input request inside a file:

```bash
cat <<EOF > "./iris-input.json"
{
  "instances": [
    [6.8,  2.8,  4.8,  1.4],
    [6.0,  3.4,  4.5,  1.6]
  ]
}
EOF
```

Use `curl` to send a test prediction API request to the server:
 a test prediction API request to the server:

```bash
SERVICE_HOSTNAME=$(kubectl get inferenceservice sklearn-iris -n kserve-test -o jsonpath='{.status.url}' | cut -d "/" -f 3)
curl -v -H "Host: ${SERVICE_HOSTNAME}" http://${INGRESS_HOST}:${INGRESS_PORT}/v1/models/sklearn-iris:predict -d @./iris-input.json
```
echo 
You should see something like this as the prediction response:

```json
{"predictions": [1, 1]}
```

### 🥞 Setting up the ZenML Stack

Before you run the example, a ZenML Stack needs to be set up with all the proper
components. Two different examples of stacks featuring GCP infrastructure
components are described in this document, but similar stacks may be set up
using different backends and used to run the example as long as the basic Stack
prerequisites are met.

#### Local orchestrator with GCS artifact store and GKE KServe installation

This stack consists of the following components:

* a GCP artifact store
* the local orchestrator
* the local metadata store
* a KServe model deployer
* a local secret manager used to store the credentials needed by KServe to
access the GCP artifact store

To have access to the GCP artifact store from your local workstation, the
gcloud client needs to be properly set up locally.

In addition to the stack components, KServe must be installed in a
Kubernetes cluster that is locally accessible through a Kubernetes configuration
context. The reference used in this example is a KServe installation
running in a GKE cluster, but any other type of Kubernetes cluster can be used,
managed or otherwise.

To configure GKE cluster access locally, e.g:

```bash
gcloud container clusters get-credentials zenml-test-cluster --zone us-east1-b --project zenml-core
```

Set up a namespace for ZenML KServe workloads:

```bash
kubectl create ns zenml-workloads
```

Extract the URL where the KServe model server exposes its prediction API, e.g.:

```bash
# If you are running in GKE or AKS clusters, the host is the GKE cluster IP address.
export INGRESS_HOST=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
# If you are running in EKS clusters, the host is the EKS cluster IP hostname.
export INGRESS_HOST=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

export INGRESS_PORT=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.spec.ports[?(@.name=="http2")].port}')
export INGRESS_URL="http://${INGRESS_HOST}:${INGRESS_PORT}"
```

Configuring the stack can be done like this:

```shell
zenml integration install tensorflow pytorch gcp kserve
zenml model-deployer register kserve_gke --flavor=kserve \
  --kubernetes_context=gke_zenml-core_us-east1-b_zenml-test-cluster \ 
  --kubernetes_namespace=zenml-workloads \
  --base_url=$INGRESS_URL \
  --secret=kserve_secret
zenml artifact-store register gcp --flavor=fcp --path gs://my-bucket
zenml secrets-manager register local --flavor=local
zenml stack register local_gcp_kserve_stack -m default -a gcp -o default -d kserve_gke -x local --set
```

ZenML will manage the KServe deployments inside the same `kubeflow`
namespace where the Kubeflow pipelines are running. You also have to update the set of
permissions granted by Kubeflow to the Kubernetes service account in the context
of which Kubeflow pipelines are running to allow the ZenML workloads to create,
update and delete KServe InferenceServices, Secrets and ServiceAccounts. 
You can do so with the below command.

```shell
kubectl apply -n kserve-test -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: kubeflow-kserve-permession
  namespace: kubeflow
  labels:
    app: zenml
rules:
- apiGroups: ["serving.kserve.io",""] # "" indicates the core API group
  resources: ["inferenceservices","secrets","serviceaccounts"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: role-binding
  namespace: kubeflow
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: kubeflow-kserve-permession
subjects:
- kind: ServiceAccount
  name: pipeline-runner
  namespace: kubeflow
EOF
```

As the last step in setting up the stack, we need to configure a ZenML secret
with the credentials needed by KServe to access the Artifact Store. This is
covered in the [Managing KServe Credentials section](#managing-kserve-credentials).

The next sections cover how to set GCP Artifact Store credentials for the KServe model deployer,   
Please look up the variables relevant to your use case in the
[official KServe Storage Credentials](https://kserve.github.io/website/0.8/sdk_docs/docs/KServeClient/#parameters)
and set them accordingly for your ZenML secret.

##### GCP Authentication with kserve_gs secret schema

Before setting ZenML secrets, we need to create a service account key. 
This service account will be used to access the GCP Artifact
Store. for more information, see the [Create and manage service account keys](https://cloud.google.com/iam/docs/creating-managing-service-account-keys#iam-service-account-keys-create-gcloud).
Once we have the service account key, we can create a ZenML secret with the following command:

```bash
$ zenml secret register -s kserve_gs kserve_secret \
    --namespace="zenml-workloads" \
    --credentials="@~/sa-deployment-temp.json" \
```

The following secret will be registered.
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━┓
┃             SECRET_KEY             │ SECRET_VALUE ┃
┠────────────────────────────────────┼──────────────┨
┃            storage_type            │ ***          ┃
┃              namespace             │ ***          ┃
┃             credentials            │ ***          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━┛

```bash
$ zenml secret get kserve_secret
┏━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃    SECRET_KEY    │ SECRET_VALUE              ┃
┠──────────────────┼───────────────────────────┨
┃   storage_type   │ GCS                       ┃
┠──────────────────┼───────────────────────────┨
┃    namespace     │ kserve-test               ┃
┠──────────────────┼───────────────────────────┨
┃   credentials    │ ~/sa-deployment-temp.json ┃
┗━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

## 🔦 Run TensorFlow Pipeline

[MLServer](https://github.com/SeldonIO/MLServer) is a Python library that aims to provide an easy way to start 
serving your machine learning models through a REST and gRPC interface. Out of the box, MLServer comes with 
a set of pre-packaged runtimes which let you interact with a subset of common frameworks.
(e.g. Scikit-Learn, XGBoost, LightGBM, MLflow etc.)

The TensorFlow pipeline consists of the following steps:
* importer - Load the MNIST handwritten digits dataset from the TensorFlow library
* train - Train a Support Vector Classifier model using the training dataset.
* evaluate - Evaluate the model using the test dataset.
* deployment_trigger - Verify if the newly trained model exceeds the threshold and if so, deploy the model.
* model_deployer - Deploy the TensorFlow model to the KServe model server using the SKLearn MLServer runtime. the model_deployer is a ZenML built-in step that takes care of the preparing of the model to the right format for the runtime servers. In this case, the ZenML will be saving a file with name `model.joblib` in the artifact store which is the format that the runtime servers expect.

### 🏃️ Run the code
To run the training/deployment TensorFlow pipeline:

```shell
python run.py
```

Example output when run with the local orchestrator stack:

```shell
Creating run for pipeline: kserve_sklearn_pipeline
Cache enabled for pipeline kserve_sklearn_pipeline
Using stack gcp_stack_kserve to run pipeline kserve_sklearn_pipeline...
Step importer has started.
Using cached version of importer [importer].
Step `importer` has finished in 0.051s.
Step `trainer` has started.
Step `trainer` has finished in 11.972s.
Step `evaluator` has started.
Test `accuracy`: 0.9688542825361512
Step `evaluator` has finished in 4.440s.
Step `deployment_trigger` has started.
Step `deployment_trigger` has finished in 3.847s.
Step `kserve_model_deployer_step` has started.
INFO:kserve.api.creds_utils:Created Secret: `kserve-secret-d5zwr` in namespace kserve-test
INFO:kserve.api.creds_utils:Patched Service account: kserve-service-credentials in namespace kserve-test
Creating a new KServe deployment service: `KServeDeploymentService[7a1d22c1-3892-4cfc-83dc-b89e22cbc743]` (type: model-serving, flavor: kserve)
KServe deployment service started and reachable at:
    `http://35.196.207.240:80/v1/models/zenml-7a1d22c1:predict`
    With the hostname: `http://zenml-7a1d22c1.zenml-workloads.example.com:predict.``
Step `kserve_model_deployer_step` has finished in 23.944s.
Pipeline run kserve_sklearn_pipeline-20_Jun_22-00_03_43_072385 has finished in 45.404s.
``` 
To stop the service, re-run the same command and supply the `--stop-service` argument.

## 🖥 Run PyTorch Pipeline

As PyTorch becomes more of a standard framework for writing Computer Vision
and Natural Language Processing models, especially in the research domain,
it is becoming more and more important to have a robust and easy to not only 
[build ML pipelines with Pytorch](../pytorch/) but also to deploy the models built with it.

[TorchServe](https://torchserve.github.io/website) is an open-source model serving 
framework for PyTorch that makes it easy to deploy Pytorch models at a production 
scale with low latency and high throughput, it provides default handlers for the most 
common applications such as object detection and text classification, so you can write
as little code as possible to deploy your custom models.

The PyTorch Training/Deployment pipeline consists of the following steps:
* importer - Load the MNIST handwritten digits dataset from the TorchVision library
* train - Train a neural network using the training set. The network is defined in the `mnist.py` file in the PyTorch folder.
* evaluate - Evaluate the model using the test set.
* deployment_trigger - Verify if the newly trained model exceeds the threshold and if so, deploy the model.
* model_deployer - Deploy the trained model to the KServe model server using the TorchServe runtime.
Just like the SKLearn MLServer runtime, the `model_deployer` is a ZenML built-in step that takes care of the preparing of the model to the right format for the runtime servers. But in this case, the user must provide some extra files to the config parameters of the `model_deployer` step.
Some of the parameters that TorchServe expects are:
    - `model_class_file`:   Python script containing model architecture class.
    - `handler`:            TorchServe's handler file to handle custom TorchServe inference logic.
    - `torch_config`:       TorchServe configuration file. By default, ZenML generates a config file for you. You can also provide your config file.

For more information about the TorchServe runtime, please refer to the [TorchServe InferenceService](https://kserve.github.io/website/0.8/modelserving/v1beta1/torchserve/#create-the-torchserve-inferenceservice). Or the [TorchServe Github Repository](https://github.com/pytorch/serve).

The PyTorch Inference pipeline consists of the following steps:
* pytorch_inference_processor - Load a digits image from URL (must be 28x28) and convert it to a byte array.
* prediction_service_loader - Load the prediction service into KServeDeploymentService to perform the inference.
* predictor - Perform the inference on the image using the built-in predict function of the prediction service.

### 🏃️ Run the code
To run the PyTorch training/deployment pipeline:

```shell
python run_pytorch.py --config="deploy"
```

Example output when running the pipeline with the local orchestrator stack:

```shell
Creating run for pipeline: pytorch_training_deployment_pipeline
Cache enabled for pipeline pytorch_training_deployment_pipeline
Using stack gcp_stack_kserve to run pipeline pytorch_training_deployment_pipeline...
Step pytorch_data_loader has started.
Using cached version of pytorch_data_loader.
Step pytorch_data_loader has finished in 0.060s.
Step pytorch_trainer has started.
Using cached version of pytorch_trainer.
Step pytorch_trainer has finished in 0.024s.
Step pytorch_evaluator has started.
Using cached version of pytorch_evaluator.
Step pytorch_evaluator has finished in 0.027s.
Step deployment_trigger has started.
Using cached version of deployment_trigger.
Step deployment_trigger has finished in 0.023s.
Step kserve_model_deployer_step has started.
INFO:root:Successfully exported model mnist to file `/var/folders/lt/r3j8hp4s00dfgtf662d1prw80000gn/T/zenml-pytorch-temp-rb85yzvx`
INFO:kserve.api.creds_utils:Created Secret: `kserve-secret-jnxxj` in namespace kserve-test
INFO:kserve.api.creds_utils:Patched Service account: kserve-service-credentials in namespace kserve-test
Creating a new KServe deployment service: `KServeDeploymentService[4b9414f8-b6e6-45c1-b092-5d53c02b0e26]` (type: model-serving, flavor: kserve)
KServe deployment service started and reachable at:
    `http://35.196.207.240:80/v1/models/mnist:predict`
    With the hostname: `zenml-4b9414f8.zenml-workloads.example.com`
Step kserve_model_deployer_step has finished in 2m6s.
Pipeline run pytorch_training_deployment_pipeline-26_Jun_22-23_24_48_544764 has finished in 2m8s.
The KServe prediction server is running remotely as a Kubernetes service and accepts inference requests at:
    `http://35.196.207.240:80/v1/models/mnist:predict`
    With the hostname: `zenml-4b9414f8.zenml-workloads.example.com`
To stop the service, run `zenml served-models delete 4b9414f8-b6e6-45c1-b092-5d53c02b0e26`.
```

To run the PyTorch inference pipeline:

```shell
python run_pytorch.py --config="deploy"
```

Example output when running the pipeline with the local orchestrator stack:

```shell
Creating run for pipeline: pytorch_inference_pipeline
Cache enabled for pipeline pytorch_inference_pipeline
Using stack gcp_stack_kserve to run pipeline pytorch_inference_pipeline...
Step prediction_service_loader has started.
Step prediction_service_loader has finished in 8.063s.
Step pytorch_inference_processor has started.
Step pytorch_inference_processor has finished in 3.430s.
Step predictor has started.
Prediction: 
[1]
Step predictor has finished in 9.228s.
Pipeline run `pytorch_inference_pipeline-26_Jun_22-23_28_57_252054` has finished in 23.051s.
The KServe prediction server is running remotely as a Kubernetes service and accepts inference requests at:
    `http://35.196.207.240:80/v1/models/mnist:predict`
    With the hostname: `zenml-4b9414f8.zenml-workloads.example.com`.
To stop the service, run `zenml served-models delete 4b9414f8-b6e6-45c1-b092-5d53c02b0e26`.
```