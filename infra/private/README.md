# Private environment

Bicep for an end-to-end private LibraryIQ environment: no public access to the model, data stores or registry. It mirrors what a customer landing zone would look like. The simpler public dev setup is in [`../main.bicep`](../main.bicep).

## What it creates

| Group | Resources |
|---|---|
| Network | VNet with an agent subnet (delegated to Foundry agents), a private-endpoint subnet, an app subnet (delegated to App Service), a Bastion subnet and a jump-VM subnet; NAT gateway for outbound calls; private DNS zones |
| Foundry | Account (public access disabled, network-injected) and project, `gpt-5.4-mini` deployment, Cosmos DB and Storage for agent state, Container Registry |
| Search | Azure AI Search (Standard, private endpoint), created in `searchLocation` and passed to Foundry as an existing resource |
| Telemetry | Log Analytics, Application Insights and a private link scope |
| Application data | Azure SQL server (private endpoint, Entra-only auth) and a serverless database |
| Approval page host | App Service plan and a Python web app with a system identity, VNet-integrated for outbound calls; the page itself is not built yet |
| Access | Bastion (Standard, tunneling enabled) and a small Linux jump VM; deployer roles on the project and registry |

Everything except Bastion and the web app's front door has a private endpoint or no public address. The Foundry part is the official sample, vendored in [`foundry-standard/`](foundry-standard/NOTICE.md).

Region notes: the environment is deployed in Sweden Central. AI Search had no capacity there, so `searchLocation` defaults to Germany West Central. Real capacity only shows on create, not in `what-if`.

Not included yet: real email and Teams publishing.

## Deploy

Prerequisites: Azure CLI with Bicep, `Owner` on the subscription, the providers `Microsoft.App`, `Microsoft.ContainerService`, `Microsoft.Network`, `Microsoft.Search`, `Microsoft.DocumentDB` and `Microsoft.Storage` registered, and an SSH key.

```bash
export AZURE_PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
export AZURE_PRINCIPAL_NAME=$(az ad signed-in-user show --query userPrincipalName -o tsv)
export VM_SSH_PUBLIC_KEY="$(cat ~/.ssh/id_ed25519.pub)"
RG=rg-libraryiq

az group create -n $RG -l swedencentral

az deployment group what-if -g $RG -f infra/private/main.bicep -p infra/private/main.bicepparam
az deployment group create  -g $RG -n main -f infra/private/main.bicep -p infra/private/main.bicepparam
```

The Foundry agent hosting setup is slow; the official sample documents that it can take a long time, so don't cancel it.

## Working with it

The account has no public endpoint, so the model, the project and the registry are reachable only from inside the VNet.

1. Open a Bastion tunnel to the jump VM (needs the `bastion` and `ssh` Azure CLI extensions):
   ```bash
   az network bastion tunnel --name <bastion> -g $RG --target-resource-id <vm id> --resource-port 22 --port 2222
   ```
2. Connect with VS Code Remote-SSH to `azureuser@127.0.0.1` port 2222 using your SSH key, sign in with `az login --use-device-code` and develop on the VM (it installs the Azure CLI, `azd`, Docker and git on first boot).
3. After the first agent is deployed, give its identity access to the SQL database (`CREATE USER [<agent identity>] FROM EXTERNAL PROVIDER`).

## Remove

```bash
az group delete -n rg-libraryiq --yes --no-wait
```

The Foundry account is soft-deleted. Purge it before reusing the same subnet, and allow time for the agent hosting to unlink (see the sample's cleanup notes in [`foundry-standard/NOTICE.md`](foundry-standard/NOTICE.md)).
