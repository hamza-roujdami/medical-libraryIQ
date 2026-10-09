targetScope = 'resourceGroup'

@description('Short prefix used in resource names.')
@maxLength(6)
param namePrefix string = 'libiq'

param location string = resourceGroup().location

@description('Object ID of the person or identity that deploys. Gets data-plane access to the Foundry project and the registry, and is the SQL Entra admin.')
param principalId string

@description('Sign-in name (UPN) of the deployer; used as the SQL Entra admin login.')
param principalName string

@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

param modelName string = 'gpt-5.4-mini'
param modelVersion string = '2026-03-17'

@description('Model capacity in thousands of tokens per minute.')
param modelCapacity int = 50

param tags object = {
  project: 'libraryiq'
  environment: 'dev'
}

var token = uniqueString(subscription().id, resourceGroup().id)
var accountName = '${namePrefix}-ai-${token}'
var projectName = '${namePrefix}-project'

// Built-in role definition IDs.
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  acrPush: '8311e382-0749-4cb8-b61a-304f252e45ec'
  foundryProjectManager: 'eadc314b-1a2d-4efa-be10-5d325db5065e'
  foundryUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  logAnalyticsDataReader: '3b03c2da-16b3-4a49-8834-0f8130efdd3b'
}

// Foundry account, project and model. Entra-only: local (key) auth is off.
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      ipRules: []
      virtualNetworkRules: []
    }
    disableLocalAuth: true
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: projectName
    description: 'LibraryIQ dev project'
  }
  dependsOn: [model]
}

// Hosting environment for hosted agents (as in the official azd starter).
resource capabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-10-01-preview' = {
  parent: account
  name: 'agents'
  properties: {
    capabilityHostKind: 'Agents'
    enablePublicHostingEnvironment: true
  }
  dependsOn: [project]
}

// The project identity calls the model through the account.
resource projectFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, project.id, roles.foundryUser)
  properties: {
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser)
  }
}

resource deployerProjectManager 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, principalId, roles.foundryProjectManager)
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryProjectManager)
  }
}

module logs 'br/public:avm/res/operational-insights/workspace:0.16.1' = {
  name: 'logs'
  params: {
    name: 'log-${namePrefix}-${token}'
    location: location
    tags: tags
    dataRetention: 30
    roleAssignments: [
      {
        // Lets the project read traces for evaluations.
        principalId: project.identity.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: roles.logAnalyticsDataReader
      }
    ]
  }
}

module appInsights 'br/public:avm/res/insights/component:0.8.0' = {
  name: 'appInsights'
  params: {
    name: 'appi-${namePrefix}-${token}'
    location: location
    tags: tags
    workspaceResourceId: logs.outputs.resourceId
    kind: 'web'
    applicationType: 'web'
  }
}

module registry 'br/public:avm/res/container-registry/registry:0.13.1' = {
  name: 'registry'
  params: {
    name: 'cr${namePrefix}${token}'
    location: location
    tags: tags
    acrSku: 'Basic'
    publicNetworkAccess: 'Enabled'
    networkRuleSetDefaultAction: 'Allow'
    azureADAuthenticationAsArmPolicyStatus: 'enabled'
    roleAssignments: [
      {
        // The project identity pulls the agent image.
        principalId: project.identity.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: roles.acrPull
      }
      {
        principalId: principalId
        principalType: principalType
        roleDefinitionIdOrName: roles.acrPush
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
    publicNetworkAccess: 'Enabled'
    administrators: {
      azureADOnlyAuthentication: true
      login: principalName
      sid: principalId
      principalType: principalType == 'User' ? 'User' : 'Application'
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
  }
}

// Project connections that hosted agents use for image pull and telemetry.
resource registryConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: 'registry'
  properties: {
    category: 'ContainerRegistry'
    target: registry.outputs.loginServer
    authType: 'ManagedIdentity'
    isSharedToAll: true
    credentials: {
      clientId: project.identity.principalId
      resourceId: registry.outputs.resourceId
    }
    metadata: {
      ResourceId: registry.outputs.resourceId
    }
  }
}

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsights.outputs.resourceId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsights.outputs.connectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.outputs.resourceId
    }
  }
}

output accountName string = account.name
output projectName string = project.name
output projectEndpoint string = project.properties.endpoints['AI Foundry API']
output projectPrincipalId string = project.identity.principalId
output modelDeployment string = model.name
output registryName string = registry.outputs.name
output registryLoginServer string = registry.outputs.loginServer
output sqlServerName string = sql.outputs.name
output sqlServerFqdn string = sql.outputs.fullyQualifiedDomainName
output sqlDatabase string = 'libraryiq'
output appInsightsName string = appInsights.outputs.name
output logAnalyticsName string = logs.outputs.name
