targetScope = 'resourceGroup'

@description('Foundry (AI Services) account name; also its custom subdomain.')
param accountName string

@description('API Management instance name.')
param apimName string

param projectName string = 'libiq-project'
param location string = resourceGroup().location

param modelName string = 'gpt-6-sol'
param modelVersion string = '2026-09-22'

@description('Model capacity in thousands of tokens per minute.')
param modelCapacity int = 100

@description('Object ID of the person who deploys and calls the model directly.')
param principalId string

@description('Publisher contact email shown on the API Management instance.')
param publisherEmail string

@description('Create the role assignments. Turn off when they already exist (the first deployment made them by CLI).')
param createRoleAssignments bool = true

param tags object = {
  project: 'libraryiq'
  environment: 'dev'
}

// Built-in role: Azure AI User (call models and use the project with Entra sign-in).
var azureAiUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

// Foundry account, project and model. Public endpoint, Entra-only (key auth off).
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

// API Management as the AI gateway: every model call goes through it.
resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: apimName
  location: location
  tags: tags
  sku: {
    name: 'BasicV2'
    capacity: 1
  }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: publisherEmail
    publisherName: 'LibraryIQ dev'
  }
}

resource foundryBackend 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'foundry'
  properties: {
    url: 'https://${accountName}.cognitiveservices.azure.com/openai/v1'
    protocol: 'http'
    description: 'Foundry ${modelName}'
  }
}

resource foundryApi 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'foundry-openai'
  properties: {
    displayName: 'Foundry models (OpenAI v1)'
    path: 'openai/v1'
    protocols: ['https']
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'api-key'
      query: 'api-key'
    }
    serviceUrl: 'https://placeholder.invalid'
  }
}

resource chatCompletions 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: foundryApi
  name: 'chat-completions'
  properties: {
    displayName: 'Chat completions'
    method: 'POST'
    urlTemplate: '/chat/completions'
  }
}

resource responses 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: foundryApi
  name: 'responses'
  properties: {
    displayName: 'Responses'
    method: 'POST'
    urlTemplate: '/responses'
  }
}

resource foundryApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: foundryApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/foundry-openai.xml')
  }
  dependsOn: [foundryBackend]
}

// The agent's key for the model API.
resource agentSubscription 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = {
  parent: apim
  name: 'libraryiq-agent'
  properties: {
    scope: foundryApi.id
    displayName: 'libraryiq-agent'
    state: 'active'
  }
}

// The gateway identity calls the model; the deployer can also call it directly.
resource gatewayCallsModel 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createRoleAssignments) {
  scope: account
  name: guid(account.id, apim.id, azureAiUser)
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUser)
  }
}

resource deployerCallsModel 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createRoleAssignments) {
  scope: account
  name: guid(account.id, principalId, azureAiUser)
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUser)
  }
}

output foundryProjectEndpoint string = project.properties.endpoints['AI Foundry API']
output modelDeployment string = model.name
output gatewayUrl string = apim.properties.gatewayUrl
output gatewayModelUrl string = '${apim.properties.gatewayUrl}/openai/v1'
