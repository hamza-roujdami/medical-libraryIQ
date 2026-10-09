targetScope = 'resourceGroup'

@description('Short prefix used in resource names.')
@maxLength(6)
param namePrefix string = 'libiq'

param location string = resourceGroup().location

@description('Object ID of the deployer. Gets access to the Foundry project, the registry, and is the SQL Entra admin.')
param principalId string

@description('Sign-in name (UPN) of the deployer; used as the SQL Entra admin login.')
param principalName string

@description('SSH public key for the jump VM admin user.')
param vmSshPublicKey string

param vmSize string = 'Standard_D2s_v5'

@description('Region for AI Search. Sweden Central had no Search capacity for this subscription.')
param searchLocation string = 'germanywestcentral'

@description('App Service plan SKU for the approval page.')
param appServiceSku string = 'B1'

param modelName string = 'gpt-5.4-mini'
param modelVersion string = '2026-03-17'

@description('Model capacity in thousands of tokens per minute.')
param modelCapacity int = 50

param tags object = {
  project: 'libraryiq'
  environment: 'private-dev'
}

var token = uniqueString(subscription().id, resourceGroup().id)

module network 'network.bicep' = {
  name: 'network'
  params: {
    location: location
    namePrefix: namePrefix
    token: token
    tags: tags
  }
}

// Foundry account, project, model, Cosmos DB, AI Search, Storage, registry and
// monitoring, all private. Vendored from the official sample (see its NOTICE.md).
module search 'search.bicep' = {
  name: 'search'
  params: {
    name: 'srch-${namePrefix}-${token}'
    location: searchLocation
    tags: tags
  }
}

module foundry 'foundry-standard/main.bicep' = {
  name: 'foundry'
  params: {
    location: location
    aiServices: '${namePrefix}ai'
    firstProjectName: 'project'
    displayName: 'LibraryIQ private project'
    modelName: modelName
    modelVersion: modelVersion
    modelCapacity: modelCapacity
    existingVnetResourceId: network.outputs.vnetId
    aiSearchResourceId: search.outputs.id
    reuseExistingSubnets: true
    agentSubnetName: 'agent-subnet'
    peSubnetName: 'pe-subnet'
    enableContainerRegistry: true
  }
}

module deployerRoles 'deployer-roles.bicep' = {
  name: 'deployerRoles'
  params: {
    accountName: foundry.outputs.accountName
    projectName: foundry.outputs.projectName
    registryName: foundry.outputs.registryName
    principalId: principalId
  }
}

// Private DNS for SQL (the Foundry template creates the other zones).
module sqlDnsZone 'br/public:avm/res/network/private-dns-zone:0.8.1' = {
  name: 'sqlDnsZone'
  params: {
    name: 'privatelink${environment().suffixes.sqlServerHostname}'
    tags: tags
    virtualNetworkLinks: [
      {
        name: 'link-${namePrefix}'
        virtualNetworkResourceId: network.outputs.vnetId
        registrationEnabled: false
      }
    ]
  }
}

module sql 'br/public:avm/res/sql/server:0.22.1' = {
  name: 'sql'
  params: {
    name: 'sql-${namePrefix}-${token}'
    location: location
    tags: tags
    publicNetworkAccess: 'Disabled'
    administrators: {
      azureADOnlyAuthentication: true
      login: principalName
      sid: principalId
      principalType: 'User'
      tenantId: tenant().tenantId
    }
    databases: [
      {
        name: 'libraryiq'
        availabilityZone: -1
        sku: {
          name: 'GP_S_Gen5_1'
          tier: 'GeneralPurpose'
        }
        autoPauseDelay: 60
        minCapacity: '0.5'
        maxSizeBytes: 2147483648
      }
    ]
    privateEndpoints: [
      {
        subnetResourceId: network.outputs.peSubnetId
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            { privateDnsZoneResourceId: sqlDnsZone.outputs.resourceId }
          ]
        }
      }
    ]
  }
}

// Approval page host. Public front door; reaches SQL through the VNet.
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${namePrefix}-${token}'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: appServiceSku
  }
  properties: { reserved: true }
}

resource approvalApp 'Microsoft.Web/sites@2024-04-01' = {
  name: 'app-${namePrefix}-${token}'
  location: location
  tags: tags
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: network.outputs.appSubnetId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.13'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
    }
  }
}

module jump 'jump.bicep' = {
  name: 'jump'
  params: {
    location: location
    namePrefix: namePrefix
    token: token
    tags: tags
    bastionSubnetId: network.outputs.bastionSubnetId
    vmSubnetId: network.outputs.vmSubnetId
    vmSize: vmSize
    sshPublicKey: vmSshPublicKey
  }
}

output vnetName string = network.outputs.vnetName
output accountName string = foundry.outputs.accountName
output projectName string = foundry.outputs.projectName
output projectPrincipalId string = foundry.outputs.projectPrincipalId
output registryName string = foundry.outputs.registryName
output registryLoginServer string = foundry.outputs.registryLoginServer
output appInsightsName string = foundry.outputs.appInsightsName
output searchName string = foundry.outputs.searchName
output cosmosName string = foundry.outputs.cosmosName
output storageName string = foundry.outputs.storageName
output sqlServerName string = sql.outputs.name
output sqlServerFqdn string = sql.outputs.fullyQualifiedDomainName
output sqlDatabase string = 'libraryiq'
output approvalAppName string = approvalApp.name
output approvalAppPrincipalId string = approvalApp.identity.principalId
output jumpVmName string = jump.outputs.vmName
output bastionName string = jump.outputs.bastionName
