#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""This module contains the utility functions used by the KServe deployer step."""
import json
import os
import tempfile
from typing import Any, List, Optional

from ml_metadata.proto.metadata_store_pb2 import Artifact
from model_archiver.model_packaging import package_model
from model_archiver.model_packaging_utils import ModelExportUtils
from pydantic import BaseModel

from zenml.exceptions import DoesNotExistException
from zenml.integrations.kserve.services.kserve_deployment import (
    KServeDeploymentConfig,
)
from zenml.integrations.kserve.steps.kserve_deployer import (
    KServeDeployerStepConfig,
)
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.steps.step_context import StepContext
from zenml.utils import io_utils, source_utils

logger = get_logger(__name__)


ARTIFACT_FILE = "artifact.json"


def prepare_service_config(
    model_uri: str, output_artifact_uri: str, config: KServeDeployerStepConfig
) -> KServeDeploymentConfig:
    """Prepare the model files for model serving.

    This function ensures that the model files are in the correct format
    and file structure required by the KServe server implementation
    used for model serving.

    Args:
        model_uri: the URI of the model artifact being served
        output_artifact_uri: the URI of the output artifact
        config: the KServe deployer step config

    Returns:
        The URL to the model is ready for serving.

    Raises:
        RuntimeError: if the model files cannot be prepared.
    """
    served_model_uri = os.path.join(output_artifact_uri, "kserve")
    fileio.makedirs(served_model_uri)

    # TODO [ENG-773]: determine how to formalize how models are organized into
    #   folders and sub-folders depending on the model type/format and the
    #   KServe protocol used to serve the model.

    # TODO [ENG-791]: an auto-detect built-in KServe server implementation
    #   from the model artifact type

    # TODO [ENG-792]: validate the model artifact type against the
    #   supported built-in KServe server implementations
    if config.service_config.predictor == "tensorflow":
        # the TensorFlow server expects model artifacts to be
        # stored in numbered subdirectories, each representing a model
        # version
        io_utils.copy_dir(model_uri, os.path.join(served_model_uri, "1"))
    elif config.service_config.predictor == "sklearn":
        # the sklearn server expects model artifacts to be
        # stored in a file called model.joblib
        model_uri = os.path.join(model_uri, "model")
        if not fileio.exists(model_uri):
            raise RuntimeError(
                f"Expected sklearn model artifact was not found at "
                f"{model_uri}"
            )
        fileio.copy(model_uri, os.path.join(served_model_uri, "model.joblib"))
    else:
        # default treatment for all other server implementations is to
        # simply reuse the model from the artifact store path where it
        # is originally stored
        served_model_uri = model_uri

    service_config = config.service_config.copy()
    service_config.model_uri = served_model_uri
    return service_config


def prepare_torch_service_config(
    model_uri: str, output_artifact_uri: str, config: KServeDeployerStepConfig
) -> KServeDeploymentConfig:
    """Prepare the PyTorch model files for model serving.

    This function ensures that the model files are in the correct format
    and file structure required by the KServe server implementation
    used for model serving.

    Args:
        model_uri: the URI of the model artifact being served
        output_artifact_uri: the URI of the output artifact
        config: the KServe deployer step config

    Returns:
        The URL to the model is ready for serving.

    Raises:
        RuntimeError: if the model files cannot be prepared.
    """
    deployment_folder_uri = os.path.join(output_artifact_uri, "kserve")
    served_model_uri = os.path.join(deployment_folder_uri, "model-store")
    config_propreties_uri = os.path.join(deployment_folder_uri, "config")
    fileio.makedirs(served_model_uri)
    fileio.makedirs(config_propreties_uri)

    if config.torch_serve_paramters is None:
        raise RuntimeError("No torch serve parameters provided")
    else:
        # Create a temporary folder
        temp_dir = tempfile.mkdtemp(prefix="zenml-pytorch-temp-")
        tmp_model_uri = os.path.join(str(temp_dir), "mnist.pt")

        # Copy from artifact store to temporary file
        fileio.copy(f"{model_uri}/checkpoint.pt", tmp_model_uri)

        torch_archiver_args = TorchModelArchiver(
            model_name=config.service_config.model_name,
            serialized_file=tmp_model_uri,
            model_file=config.torch_serve_paramters.model_class,
            handler=config.torch_serve_paramters.handler,
            export_path=temp_dir,
            version=config.torch_serve_paramters.model_version,
        )

        manifest = ModelExportUtils.generate_manifest_json(torch_archiver_args)
        package_model(torch_archiver_args, manifest=manifest)

        # Copy from temporary file to artifact store
        archived_model_uri = os.path.join(
            temp_dir, f"{config.service_config.model_name}.mar"
        )
        if not fileio.exists(archived_model_uri):
            raise RuntimeError(
                f"Expected torch archived model artifact was not found at "
                f"{archived_model_uri}"
            )

        # Copy the torch model archive artifact to the model store
        fileio.copy(
            archived_model_uri,
            os.path.join(
                served_model_uri, f"{config.service_config.model_name}.mar"
            ),
        )

        # Get or Generate the config file
        if config.torch_serve_paramters.torch_config:
            # Copy the torch model config to the model store
            fileio.copy(
                config.torch_serve_paramters.torch_config,
                os.path.join(config_propreties_uri, "config.properties"),
            )
        else:
            # Generate the config file
            config_file_uri = generate_model_deployer_config(
                model_name=config.service_config.model_name,
                directory=temp_dir,
            )
            # Copy the torch model config to the model store
            fileio.copy(
                config_file_uri,
                os.path.join(config_propreties_uri, "config.properties"),
            )

    service_config = config.service_config.copy()
    service_config.model_uri = deployment_folder_uri
    return service_config


class TorchModelArchiver(BaseModel):
    """Model Archiver for PyTorch models.

    Attributes:
        model_name: Model name.
        model_version: Model version.
        serialized_file: Serialized model file.
        handler: TorchServe's handler file to handle custom TorchServe inference logic.
        extra_files: Comma separated path to extra dependency files.
        requirements_file: Path to requirements file.
        export_path: Path to export model.
        runtime: Runtime of the model.
        force: Force export of the model.
        archive_format: Archive format.
    """

    model_name: str
    serialized_file: str
    model_file: str
    handler: str
    export_path: str
    extra_files: Optional[List[str]] = None
    version: Optional[str] = None
    requirements_file: Optional[str] = None
    runtime: Optional[str] = "python"
    force: Optional[bool] = None
    archive_format: Optional[str] = "default"


def generate_model_deployer_config(
    model_name: str,
    directory: str,
) -> str:
    """Generate a model deployer config.

    Args:
        model_name: the name of the model
        directory: the directory where the model is stored

    Returns:
        None
    """
    config_lines = [
        "inference_address=http://0.0.0.0:8085",
        "management_address=http://0.0.0.0:8085",
        "metrics_address=http://0.0.0.0:8082",
        "grpc_inference_port=7070",
        "grpc_management_port=7071",
        "enable_metrics_api=true",
        "metrics_format=prometheus",
        "number_of_netty_threads=4",
        "job_queue_size=10",
        "enable_envvars_config=true",
        "install_py_dep_per_model=true",
        "model_store=/mnt/models/model-store",
    ]

    with tempfile.NamedTemporaryFile(
        suffix=".properties", mode="w+", dir=directory, delete=False
    ) as f:
        for line in config_lines:
            f.write(line + "\n")
        f.write(
            f'model_snapshot={{"name":"startup.cfg","modelCount":1,"models":{{"{model_name}":{{"1.0":{{"defaultVersion":true,"marName":"{model_name}.mar","minWorkers":1,"maxWorkers":5,"batchSize":1,"maxBatchDelay":10,"responseTimeout":120}}}}}}}}'
        )
    f.close()
    return f.name


def prepare_custom_service_config(
    model_uri: str,
    output_artifact_uri: str,
    config: KServeDeployerStepConfig,
    context: StepContext,
) -> KServeDeploymentConfig:
    """Prepare the model files for model serving.

    This function ensures that the model files are in the correct format
    and file structure required by the KServe server implementation
    used for model serving.

    Args:
        model_uri: the URI of the model artifact being served
        output_artifact_uri: the URI of the output artifact
        config: the KServe deployer step config
        context: the step context

    Returns:
        The URL to the model is ready for serving.

    Raises:
        RuntimeError: if the model files cannot be prepared.
        DoesNotExistException: if the active stack is not available.
    """
    if config.custom_deploy_paramters is None:
        raise RuntimeError("No custom deploy parameters provided")

    served_model_uri = os.path.join(output_artifact_uri, "kserve")
    fileio.makedirs(served_model_uri)
    io_utils.copy_dir(model_uri, served_model_uri)
    # TODO [ENG-773]: determine how to formalize how models are organized into
    #   folders and sub-folders depending on the model type/format and the
    #   KServe protocol used to serve the model.
    if not context.stack:
        raise DoesNotExistException(
            "No active stack is available. "
            "Please make sure that you have registered and set a stack."
        )
    stack = context.stack
    artifact = stack.metadata_store.store.get_artifacts_by_uri(model_uri)
    save_to_json_zenml_artifact(served_model_uri, artifact[0])

    service_config = config.service_config.copy()
    service_config.model_uri = served_model_uri
    return service_config


def save_to_json_zenml_artifact(
    served_model_uri: str, artifact: Artifact
) -> None:
    """Save a zenml artifact to a json file.

    Args:
        served_model_uri: the URI of the model artifact being served
        artifact: the artifact to save
    """
    data = {}
    data["datatype"] = artifact.properties["datatype"].string_value
    data["materializer"] = artifact.properties["materializer"].string_value
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(data, f)
        # Copy it into artifact store
    fileio.copy(f.name, os.path.join(served_model_uri, ARTIFACT_FILE))


def load_from_json_zenml_artifact(model_file_dir: str) -> Any:
    """Load a zenml artifact from a json file.

    Args:
        model_file_dir: the directory where the model files are stored

    Returns:
        The model
    """
    with fileio.open(os.path.join(model_file_dir, ARTIFACT_FILE), "r") as f:
        artifact = json.load(f)
    model_artifact = Artifact()
    model_artifact.uri = model_file_dir
    model_artifact.properties["datatype"].string_value = artifact["datatype"]
    model_artifact.properties["materializer"].string_value = artifact[
        "materializer"
    ]
    materializer_class = source_utils.load_source_path_class(
        model_artifact.properties["materializer"].string_value
    )
    model_class = source_utils.load_source_path_class(
        model_artifact.properties["datatype"].string_value
    )
    materialzer_object = materializer_class(model_artifact)
    model = materialzer_object.handle_input(model_class, mode="inference")
    logger.debug(f"model loaded successfully :\n{model}")
    return model
