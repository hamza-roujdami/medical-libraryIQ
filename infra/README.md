# Public dev environment

Bicep for the public dev environment: a Foundry resource, a project, a model deployment, an API Management instance acting as the AI gateway, and the library tools service. It mirrors resource group `rg-libraryiq-pub` (UAE North, with the tools web app in Sweden Central).

The agent reaches the model and the library tools only through the gateway.

## What it creates

| Resource | Details |
|---|---|
| Foundry account | `AIServices`, public endpoint, Entra-only (key authentication off) |
| Foundry project | `libiq-project` |
| Model deployment | `gpt-6-sol` 2026-09-22, GlobalStandard, 100K tokens per minute |
| API Management | Basic v2 with a system-assigned identity, used as the AI gateway |
| Model API | `openai/v1` with `chat/completions` and `responses`, backed by the Foundry account |
| Tools web app | Linux App Service (B1, Python 3.13) running the library tools as a native MCP server |
| MCP server | `library`, a passthrough to the tools web app's `/mcp` endpoint, exposed at `<gateway>/library/mcp` |
| Gateway subscriptions | `demo-requester` and `demo-librarian` (one key each, all APIs, sent in the `api-key` header), plus `libraryiq-agent`, which counts as a requester |
| Role assignments | Azure AI User on the Foundry account for the gateway identity and for the deployer |

## Gateway policies

- [`policies/foundry-openai.xml`](policies/foundry-openai.xml), on the model API: routes to the Foundry backend, signs in with the gateway's managed identity (no model keys), and limits each subscription to 60,000 tokens per minute with the remaining budget in the `x-remaining-tokens` header.
- [`policies/library-tools.xml`](policies/library-tools.xml), on the MCP server: adds the shared `x-backend-key` header that the tools service requires, sets `x-user-id` and `x-user-role` from the caller's subscription (`demo-librarian` is the librarian, every other key is a requester; callers cannot set these headers themselves), and limits each subscription to 60 calls per minute. In production the same headers would come from the signed-in user's token claims. Policies must not read response bodies, which would break MCP streaming.

## Deploy

```bash
export AZURE_PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
export AZURE_PRINCIPAL_NAME=$(az ad signed-in-user show --query userPrincipalName -o tsv)
export LIBRARYIQ_BACKEND_KEY=$(openssl rand -hex 24)   # shared by the gateway and the tools service

az group create -n rg-libraryiq-pub -l uaenorth
az deployment group what-if -g rg-libraryiq-pub -f infra/main.bicep -p infra/main.bicepparam
az deployment group create  -g rg-libraryiq-pub -f infra/main.bicep -p infra/main.bicepparam

# Tools service code (the web app builds its dependencies)
scripts/package_service.sh
az webapp deploy -g rg-libraryiq-pub -n <webAppName> --src-path /tmp/libraryiq-service.zip --type zip
```

Notes:

- Set `createRoleAssignments = true` in the parameter file for a fresh resource group. The current environment was first created by CLI, so its role assignments already exist and the flag is off to avoid duplicates.
- The dev subscription has no App Service quota in UAE North, so `appLocation` places the tools web app in Sweden Central. The tools handle only public bibliographic lookups and synthetic data.
- `enableTestEndpoints = true` exposes state and reset endpoints that the eval runner uses. Keep it off outside dev.
- The backend key is an app setting here. In production, use a Key Vault reference, or replace it with Entra authentication on the web app and a managed identity on the gateway.

## Use it

```bash
SUB=$(az account show --query id -o tsv)
KEY=$(az rest --method post --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/rg-libraryiq-pub/providers/Microsoft.ApiManagement/service/<apim>/subscriptions/demo-requester/listSecrets?api-version=2024-05-01" --query primaryKey -o tsv)

curl -s https://<apim>.azure-api.net/openai/v1/responses \
  -H "api-key: $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-6-sol", "input": "ping"}'
```

Set `LIBRARYIQ_GATEWAY_URL`, `LIBRARYIQ_GATEWAY_API_KEY`, `LIBRARYIQ_MODEL` and `LIBRARYIQ_TOOLS_MCP_URL` for the agent (see `.env.example`). A new subscription key can take a short while to work.

## Gateway behaviour to know

- A REST-backed gateway MCP server was tried first. It sent a single-property request body as a bare value, and turned a nullable field into an object in the tool schema, so the tools are now a native MCP server and the gateway only passes calls through.
- Basic v2 has no virtual network integration. A private network setup would need Standard v2.
- API Management bills hourly while it exists; delete the resource group when the environment is not needed.
