# Infrastructure

Bicep for the LibraryIQ dev environment. One resource group, Entra-only auth (no keys).

## What it creates

| Resource | Purpose |
|---|---|
| Foundry account + project | Hosts the agent; `local auth` disabled |
| Model deployment (`gpt-5.4-mini`, GlobalStandard) | The chat model |
| Container Registry (Basic) | Agent container image |
| Log Analytics + Application Insights | Traces and logs |
| Azure SQL server + serverless database | Requests, decisions and audit; Entra-only auth |
| Project connections | Registry and Application Insights, used by hosted agents |
| Role assignments | Project identity: Foundry User on the account, registry pull, log read. Deployer: Foundry Project Manager, registry push, SQL Entra admin |

Not included yet: AI Search, API Management, private networking, Key Vault. They are added when needed.

## Deploy

Prerequisites: Azure CLI with Bicep, and `Owner` (or Contributor + User Access Administrator) on the target subscription.

```bash
az login
az account set --subscription <subscription-id>

export AZURE_PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
export AZURE_PRINCIPAL_NAME=$(az ad signed-in-user show --query userPrincipalName -o tsv)
RG=rg-libraryiq-dev

az group create -n $RG -l swedencentral

# Preview, then deploy
az deployment group what-if -g $RG -f infra/main.bicep -p infra/main.bicepparam
az deployment group create  -g $RG -f infra/main.bicep -p infra/main.bicepparam
```

The region is the resource group's region. Check that the model and hosted agents are available there before choosing another one.

## Parameters

| Parameter | Default | Notes |
|---|---|---|
| `principalId` | env `AZURE_PRINCIPAL_ID` | Object ID of the deployer |
| `principalName` | env `AZURE_PRINCIPAL_NAME` | Sign-in name; becomes the SQL Entra admin |
| `namePrefix` | `libiq` | Up to 6 characters |
| `modelName` / `modelVersion` | `gpt-5.4-mini` / `2026-03-17` | Must exist in the region |
| `modelCapacity` | `50` | Thousands of tokens per minute; counts against quota |

## Outputs

Project endpoint, model deployment name, registry login server, SQL server name and address, and resource names. Show them with:

```bash
az deployment group show -g $RG -n main --query properties.outputs
```

## After the first agent is deployed

The agent gets its own Entra identity only when it is created, so access for it cannot be part of this template. Once the agent exists, create it as a user in the SQL database (`CREATE USER [<agent identity>] FROM EXTERNAL PROVIDER`) and grant it the table permissions it needs.

## Network access

The template requests public network access, but some subscriptions enforce policies that switch it off. On the subscription used for development this happened to Key Vault and to the SQL server: the server is created with public access disabled and cannot be reached from outside a private network. Reaching it from a hosted agent or a workstation needs private endpoints (and, for the agent, VNet-integrated hosting). Plan for private networking before handling real data.

## Remove

```bash
az group delete -n $RG --yes
```
