# AI Foundry Agent — Azure ML Job Submission

A proof-of-concept that lets users submit Azure Machine Learning jobs through natural language. An AI Foundry agent is equipped with an OpenAPI tool that calls an Azure Function to submit AML jobs.

## Architecture

```
┌──────────┐     ┌───────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  User    │────►│  AI Foundry Agent │────►│  Azure Function  │────►│  Azure ML   │
│          │◄────│  (gpt-4.1-mini)   │◄────│  (submit-job)    │◄────│  Workspace  │
└──────────┘     └───────────────────┘     └──────────────────┘     └─────────────┘
                   Agent decides when        OpenAPI tool calls       Submits command
                   to call the tool          the Function App         job, returns URL
```

**Flow:**
1. User sends a message (e.g., "Submit a hello world job")
2. The Foundry agent (gpt-4.1-mini) decides to call the `submit-aml-job` OpenAPI tool
3. The Azure Function receives the POST request, authenticates to AML, and submits a command job
4. The Function returns the job name, status, and Azure ML Studio URL
5. The agent formats the response and returns it to the user

> **Note:** The agent can also be connected to Teams / M365 Copilot — see [Connect to Teams](#6-connect-to-teams--m365-copilot-optional).

## Project Structure

```
.
├── function_app.py                    # Azure Function — submits AML jobs via azure-ai-ml SDK
├── test_bot_registration.py           # Script to create/test the Foundry agent locally
├── openapi-spec.json                  # OpenAPI 3.0 spec for the submit-job endpoint
├── host.json                          # Azure Functions host configuration
├── requirements.txt                   # Python dependencies (Function App)
├── requirements-test.txt              # Additional dependencies for the test script
├── .gitignore                         # Git ignore rules
├── README.md                          # This file
└── aml_job/
    ├── hello_world.py                 # Sample script submitted to AML as a POC
    └── hello_world_component.yaml     # AML component definition (register before first run)
```

## Prerequisites

- Python 3.11+
- Azure CLI (`az`) logged in
- [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-tools?tabs=v4&pivots=programming-language-python) v4
- An Azure subscription with:
  - An **AI Foundry** project with a model deployment (e.g., `gpt-4.1-mini`)
  - An **Azure ML** workspace with a compute cluster
  - An **Azure Function App** (Python, Linux Consumption)

## Azure Resources

| Resource | Purpose |
|---|---|
| AI Foundry project | Hosts the agent and model deployment |
| Azure Function App | HTTP-triggered function that submits AML jobs |
| Azure ML workspace | Runs the job on a compute cluster |
| Key Vault | Stores the service principal client secret (cross-tenant only) |

## Setup

### 1. Deploy the Azure Function

```bash
func azure functionapp publish <YOUR_FUNCTION_APP_NAME> --python
```

### 2. Register the AML Component

The Function App references a pre-registered component in the AML workspace. Register it once before the first run:

```bash
az ml component create --file aml_job/hello_world_component.yaml \
  --workspace-name <WORKSPACE_NAME> --resource-group <RESOURCE_GROUP>
```

### 3. Configure Function App Settings

Set these application settings on the Function App (via Azure Portal or CLI):

| Setting | Description |
|---|---|
| `AML_SUBSCRIPTION_ID` | Azure subscription containing the AML workspace |
| `AML_RESOURCE_GROUP` | Resource group of the AML workspace |
| `AML_WORKSPACE_NAME` | Name of the AML workspace |
| `AML_COMPUTE_NAME` | Name of the compute cluster (e.g., `cpu-cluster`) |

```bash
az functionapp config appsettings set \
  --name <FUNCTION_APP_NAME> \
  --resource-group <RESOURCE_GROUP> \
  --settings \
    AML_SUBSCRIPTION_ID=<SUBSCRIPTION_ID> \
    AML_RESOURCE_GROUP=<RG_NAME> \
    AML_WORKSPACE_NAME=<WORKSPACE_NAME> \
    AML_COMPUTE_NAME=<COMPUTE_NAME>
```

### 4. Update the OpenAPI Spec

Edit `openapi-spec.json` and replace the `servers[0].url` with your Function App URL:

```json
"servers": [
  {
    "url": "https://<YOUR_FUNCTION_APP_NAME>.azurewebsites.net",
    "description": "Azure Function App"
  }
]
```

### 5. Create and Test the Agent

Update the `PROJECT_ENDPOINT` and `MODEL_DEPLOYMENT` in `test_bot_registration.py` to match your Foundry project (or set the `PROJECT_ENDPOINT` environment variable), then run:

```bash
python test_bot_registration.py
```

This creates the agent in AI Foundry and sends a test prompt. If successful, you'll see the agent response with a job name, status, and Studio URL.

### 6. Connect to Teams / M365 Copilot (Optional)

AI Foundry agents can be deployed directly to Teams and M365 Copilot from the Foundry portal — no separate Bot Service required. See [Deploy agents to Microsoft 365 Copilot and Teams](https://learn.microsoft.com/azure/ai-services/agents/how-to/deploy-agent-to-teams).

## Authentication

### Same-tenant (simplest)

If all users and Azure resources are in the **same tenant**, no extra configuration is needed. The Function App's **system-assigned managed identity** authenticates to AML, and users need the **Azure AI User** role on the Foundry project.

Ensure the Function App's managed identity has:
- **Contributor** on the AML workspace (for job submission)

Ensure users have:
- **Azure AI User** on the AI Foundry resource (for agent interaction)

### Cross-tenant

If users are in a **different tenant** from your Azure resources, the Function App cannot use managed identity to authenticate to AML. Instead, create a **service principal** in the Azure resource tenant:

1. **Create a service principal:**
   ```bash
   az ad app create --display-name "foundry-agent-sp"
   az ad sp create --id <APP_ID>
   az ad app credential reset --id <APP_ID> --end-date "YYYY-MM-DD"
   ```

2. **Assign RBAC roles:**
   ```bash
   # AI Foundry access
   az role assignment create --assignee <APP_ID> --role "Azure AI Developer" \
     --scope /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.CognitiveServices/accounts/<FOUNDRY_RESOURCE>

   # AML workspace access
   az role assignment create --assignee <APP_ID> --role "Contributor" \
     --scope /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.MachineLearningServices/workspaces/<WORKSPACE>
   ```

3. **Store the secret in Key Vault:**
   ```bash
   az keyvault secret set --vault-name <KV_NAME> --name "bot-sp-client-secret" --value "<SECRET>"
   ```

4. **Set Function App settings:**

   | Setting | Description |
   |---|---|
   | `AZURE_TENANT_ID` | Tenant ID where Azure resources live |
   | `AZURE_CLIENT_ID` | Service principal app ID |
   | `AZURE_CLIENT_SECRET` | Key Vault reference: `@Microsoft.KeyVault(SecretUri=https://<KV>.vault.azure.net/secrets/bot-sp-client-secret/)` |

   The Function App's managed identity needs **Key Vault Secrets User** on the Key Vault to resolve the reference.

The code automatically detects this configuration — when `AZURE_TENANT_ID` is set, it uses `ClientSecretCredential`; otherwise, it falls back to `DefaultAzureCredential` (managed identity or `az login`).

> **Note:** Cross-tenant Foundry agent access has a known limitation — AI Foundry validates the user's objectId against the resource tenant's directory. If the user's home tenant objectId doesn't resolve in the resource tenant, the agent returns an authorization error.

## Local Development

1. Log in to the Azure tenant that owns the resources:
   ```bash
   az login --tenant <TENANT_ID>
   ```

2. Run the test script:
   ```bash
   python test_bot_registration.py
   ```

   `DefaultAzureCredential` will pick up your `az login` session.

3. To test with the service principal locally:
   ```powershell
   $env:AZURE_TENANT_ID="<TENANT_ID>"
   $env:AZURE_CLIENT_ID="<CLIENT_ID>"
   $env:AZURE_CLIENT_SECRET="<SECRET>"
   python test_bot_registration.py
   ```

## Dependencies

| Package | Purpose |
|---|---|
| `azure-functions` | Azure Functions runtime |
| `azure-identity` | Authentication (DefaultAzureCredential, ClientSecretCredential) |
| `azure-ai-ml` | Azure ML SDK — job submission |
| `azure-ai-projects` | AI Foundry SDK — agent creation (used in test_bot_registration.py) |
| `jsonref` | Resolves `$ref` pointers in the OpenAPI spec (used in test_bot_registration.py) |

## Extending to Full Training Pipelines

This POC submits a single sample component as a command job. To extend it for full training runs:

1. **Register multiple components** in your AML workspace — e.g., data preparation, feature engineering, model training, evaluation.

2. **Build a pipeline** in the Azure Function using the `azure-ai-ml` SDK:
   ```python
   from azure.ai.ml.dsl import pipeline

   # Retrieve registered components
   prep_component = ml_client.components.get("data_prep", version="1")
   train_component = ml_client.components.get("model_training", version="1")
   eval_component = ml_client.components.get("evaluation", version="1")

   @pipeline(description="Full training pipeline")
   def training_pipeline():
       prep_step = prep_component()
       train_step = train_component(input_data=prep_step.outputs.output_data)
       eval_step = eval_component(model=train_step.outputs.model)
       return {"model": train_step.outputs.model}

   pipeline_job = training_pipeline()
   pipeline_job.settings.default_compute = "cpu-cluster"
   returned_job = ml_client.jobs.create_or_update(pipeline_job)
   ```

3. **Expand the OpenAPI spec** to accept pipeline parameters (e.g., dataset name, hyperparameters) so the agent can pass user inputs to the pipeline.

4. **Add more tools to the agent** — for example, a tool to check job status, download outputs, or list previous runs.
