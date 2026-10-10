# Public dev environment

Bicep for the public dev environment: a Foundry resource, a project, a model deployment and an API Management instance acting as the AI gateway. It mirrors resource group `rg-libraryiq-pub` (UAE North).

The agent runs outside Azure for now (or in a hosted agent later) and reaches the model only through the gateway. The library tools run inside the agent process, so there is nothing else to host.

## What it creates

| Resource | Details |
|---|---|
| Foundry account | `AIServices`, public endpoint, Entra-only (key authentication off) |
| Foundry project | `libiq-project` |
| Model deployment | `gpt-6-sol` 2026-09-22, GlobalStandard, 100K tokens per minute |
| API Management | Basic v2 with a system-assigned identity, used as the AI gateway |
| Model API | `openai/v1` with `chat/completions` and `responses`, backed by the Foundry account |
| Gateway subscription | `libraryiq-agent`, one key for the model API, sent in the `api-key` header |
| Role assignments | Azure AI User on the Foundry account for the gateway identity and for the deployer |

## Gateway policy

[`policies/foundry-openai.xml`](policies/foundry-openai.xml), on the model API: routes to the Foundry backend, signs in with the gateway's managed identity (no model keys), and limits each subscription to 60,000 tokens per minute with the remaining budget in the `x-remaining-tokens` header.

## Deploy

```bash
export AZURE_PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
export AZURE_PRINCIPAL_NAME=$(az ad signed-in-user show --query userPrincipalName -o tsv)

az group create -n rg-libraryiq-pub -l uaenorth
az deployment group what-if -g rg-libraryiq-pub -f infra/main.bicep -p infra/main.bicepparam
az deployment group create  -g rg-libraryiq-pub -f infra/main.bicep -p infra/main.bicepparam
```

Set `createRoleAssignments = true` in the parameter file for a fresh resource group. The current environment was first created by CLI, so its role assignments already exist and the flag is off to avoid duplicates.

## Use it

```bash
SUB=$(az account show --query id -o tsv)
KEY=$(az rest --method post --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/rg-libraryiq-pub/providers/Microsoft.ApiManagement/service/<apim>/subscriptions/libraryiq-agent/listSecrets?api-version=2024-05-01" --query primaryKey -o tsv)

curl -s https://<apim>.azure-api.net/openai/v1/responses \
  -H "api-key: $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-6-sol", "input": "ping"}'
```

Set `LIBRARYIQ_GATEWAY_URL`, `LIBRARYIQ_GATEWAY_API_KEY` and `LIBRARYIQ_MODEL` for the agent (see `.env.example`). A new subscription key can take a short while to work.

## Notes

- Basic v2 has no virtual network integration. A private network setup would need Standard v2.
- API Management bills hourly while it exists; delete the resource group when the environment is not needed.
