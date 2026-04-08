"""Test script to create an AI Foundry agent and submit an Azure ML job.

This script:
  1. Loads the OpenAPI spec for the Azure Function (submit-job endpoint)
  2. Authenticates to the AI Foundry project
  3. Creates (or updates) a Foundry agent with the OpenAPI tool attached
  4. Sends a test prompt so the agent calls the Function App and submits an AML job
  5. Prints the agent's response (job name, status, Studio URL)

Prerequisites:
  - pip install azure-ai-projects azure-identity jsonref
  - az login --tenant <TENANT_ID>  (or set SP env vars — see below)
"""

import os
from typing import Any, cast
import jsonref
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    OpenApiAgentTool,
    OpenApiFunctionDefinition,
    OpenApiAnonymousAuthDetails,
)
from azure.identity import ClientSecretCredential, DefaultAzureCredential

# ---------------------------------------------------------------------------
# Configuration — update these to match your environment.
# ---------------------------------------------------------------------------
# Foundry project endpoint (format: https://<resource>.services.ai.azure.com/api/projects/<project>)
PROJECT_ENDPOINT = os.environ.get(
    "PROJECT_ENDPOINT",
    "https://<RESOURCE_NAME>.services.ai.azure.com/api/projects/<PROJECT_NAME>",
)
# Model deployment name in the Foundry project
MODEL_DEPLOYMENT = "gpt-4.1-mini"

# ---------------------------------------------------------------------------
# Load the OpenAPI spec that describes the Azure Function's submit-job API.
# jsonref resolves any $ref pointers in the spec so the SDK receives a flat dict.
# ---------------------------------------------------------------------------
spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi-spec.json")
with open(spec_path, "r") as f:
    openapi_spec = cast(dict[str, Any], jsonref.loads(f.read()))

# ---------------------------------------------------------------------------
# Authenticate — service principal (if env vars set) or az login / managed identity.
# ---------------------------------------------------------------------------
if os.environ.get("AZURE_TENANT_ID"):
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
else:
    credential = DefaultAzureCredential()

# ---------------------------------------------------------------------------
# Create the AI Foundry project client and an OpenAI-compatible client for
# sending prompts to the agent.
# ---------------------------------------------------------------------------
project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=credential,
)
openai = project.get_openai_client()

# ---------------------------------------------------------------------------
# Define the OpenAPI tool that points at the Azure Function's submit-job
# endpoint. The agent will call this tool when the user asks to submit a job.
# Auth is anonymous because the Function App handles its own auth to AML.
# ---------------------------------------------------------------------------
aml_tool = OpenApiAgentTool(
    openapi=OpenApiFunctionDefinition(
        name="submit-aml-job",
        spec=openapi_spec,
        description="Submit a hello_world.py sample job to Azure Machine Learning and return the job name, status, and Studio URL.",
        auth=OpenApiAnonymousAuthDetails(),
    )
)

# ---------------------------------------------------------------------------
# Create (or update) the agent in AI Foundry with the OpenAPI tool attached.
# ---------------------------------------------------------------------------
agent = project.agents.create_version(
    agent_name="AML-Job-Bot",
    definition=PromptAgentDefinition(
        model=MODEL_DEPLOYMENT,
        instructions=(
            "You are a helpful assistant that submits Azure ML jobs. "
            "When a user asks to submit, run, or execute a job, use the submit-aml-job tool. "
            "After the job is submitted, share the job name, status, and Studio URL with the user."
        ),
        tools=[aml_tool],
    ),
)
print(f"Agent created: {agent.name} (version {agent.version})")

# ---------------------------------------------------------------------------
# Send a test prompt — the agent should invoke the submit-aml-job tool,
# which calls the Azure Function, which submits the AML job.
# ---------------------------------------------------------------------------
response = openai.responses.create(
    input="Submit a hello world job on Azure ML.",
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
)

print(f"Agent response: {response.output_text}")