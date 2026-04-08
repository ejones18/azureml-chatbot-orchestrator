"""Azure Function that submits jobs to Azure Machine Learning.

This function is called by an AI Foundry agent via an OpenAPI tool definition.
The agent sends a POST request to /api/submit-job, and this function:
  1. Authenticates to Azure ML (managed identity or service principal)
  2. Retrieves a registered AML component
  3. Submits it as a command job on the configured compute cluster
  4. Returns the job name, status, and Azure ML Studio URL
"""

import json
import os
import logging

import azure.functions as func
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.ai.ml import MLClient

# NOTE: Auth is set to ANONYMOUS because the Foundry agent's OpenAPI tool
# does not forward user tokens. For production, consider adding an API key,
# function-level auth, or network restrictions (VNET/private endpoint).
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ---------------------------------------------------------------------------
# Configuration — all values are read from Function App Application Settings.
# See README.md "Configure Function App Settings" for details.
# ---------------------------------------------------------------------------
AML_SUBSCRIPTION_ID = os.environ.get("AML_SUBSCRIPTION_ID", "")
AML_RESOURCE_GROUP = os.environ.get("AML_RESOURCE_GROUP", "")
AML_WORKSPACE_NAME = os.environ.get("AML_WORKSPACE_NAME", "")
AML_COMPUTE_NAME = os.environ.get("AML_COMPUTE_NAME", "")

# The component must be pre-registered in the AML workspace.
# See aml_job/hello_world_component.yaml and README.md for registration steps.
AML_COMPONENT_NAME = "hello_world_job"
AML_COMPONENT_VERSION = "1"


@app.route(route="submit-job", methods=["POST"])
def submit_job(req: func.HttpRequest) -> func.HttpResponse:
    """Submit a job to Azure ML using a pre-registered component.

    Accepts an optional JSON body with a "display_name" field.
    Returns a JSON object with the job name, status, and Studio URL.
    """
    logging.info("submit-job HTTP trigger invoked.")

    # Allow the caller to override the job display name (optional).
    display_name = "hello-world-foundry-agent"
    try:
        body = req.get_json()
        display_name = body.get("display_name", display_name)
    except ValueError:
        pass  # No JSON body — use the default display name.

    try:
        # --- Authenticate to Azure ML ---
        # When AZURE_TENANT_ID is set (cross-tenant / service-principal scenario),
        # use explicit ClientSecretCredential. Otherwise, fall back to
        # DefaultAzureCredential (managed identity in Azure, az login locally).
        if os.environ.get("AZURE_TENANT_ID"):
            credential = ClientSecretCredential(
                tenant_id=os.environ["AZURE_TENANT_ID"],
                client_id=os.environ["AZURE_CLIENT_ID"],
                client_secret=os.environ["AZURE_CLIENT_SECRET"],
            )
        else:
            credential = DefaultAzureCredential()

        ml_client = MLClient(
            credential=credential,
            subscription_id=AML_SUBSCRIPTION_ID,
            resource_group_name=AML_RESOURCE_GROUP,
            workspace_name=AML_WORKSPACE_NAME,
        )

        # --- Build and submit the job ---
        # Retrieve the registered component, instantiate it, configure the
        # compute target and environment, then submit to the AML workspace.
        component = ml_client.components.get(AML_COMPONENT_NAME, version=AML_COMPONENT_VERSION)
        job = component()
        job.compute = AML_COMPUTE_NAME
        job.display_name = display_name
        job.environment = "azureml://registries/azureml/environments/sklearn-1.5/labels/latest"
        job.description = "Hello World POC job submitted from Foundry agent"

        returned_job = ml_client.jobs.create_or_update(job)

        # Return job metadata so the agent can relay it to the user.
        result = {
            "status": "success",
            "job_name": returned_job.name,
            "job_status": str(returned_job.status),
            "studio_url": returned_job.studio_url,
        }
        return func.HttpResponse(
            json.dumps(result), status_code=200, mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Failed to submit AML job: {e}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": str(e)}),
            status_code=500,
            mimetype="application/json",
        )
