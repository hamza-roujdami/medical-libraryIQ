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

@description('Web app that hosts the library tools service.')
param webAppName string

@description('Region for the web app plan, if the main region has no capacity.')
param appLocation string = resourceGroup().location

@description('App Service plan size.')
param appPlanSku string = 'B1'

@description('Contact address the tools service sends to Crossref, PubMed and Unpaywall.')
param contactEmail string

@secure()
@description('Shared key the gateway sends to the tools service. The service rejects calls without it.')
param backendKey string

@description('Turn on the eval state and reset endpoints of the tools service. Dev only.')
param enableTestEndpoints bool = false

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

// API Management as the AI gateway: model traffic, and later the MCP servers.
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

resource devSubscription 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = {
  parent: apim
  name: 'libraryiq-dev'
  properties: {
    scope: foundryApi.id
    displayName: 'libraryiq-dev'
    state: 'active'
  }
}

// The tools service: the library tools as a native MCP server, hosted on a small Linux web app.
// Code is deployed separately (see README).
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${webAppName}'
  location: appLocation
  tags: tags
  kind: 'linux'
  sku: { name: appPlanSku }
  properties: { reserved: true }
}

resource site 'Microsoft.Web/sites@2024-04-01' = {
  name: webAppName
  location: appLocation
  tags: tags
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.13'
      appCommandLine: 'python -m uvicorn libraryiq.server:create_app --factory --host 0.0.0.0 --port 8000'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'LIBRARYIQ_CONTACT_EMAIL', value: contactEmail }
        { name: 'LIBRARYIQ_DATABASE_PATH', value: '/home/libraryiq.db' }
        { name: 'LIBRARYIQ_BACKEND_KEY', value: backendKey }
        { name: 'LIBRARYIQ_ENABLE_TEST_ENDPOINTS', value: string(enableTestEndpoints) }
      ]
    }
  }
}

resource backendKeyValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'libraryiq-backend-key'
  properties: {
    displayName: 'libraryiq-backend-key'
    value: backendKey
    secret: true
  }
}

// The tools service is a native MCP server (stateless, JSON responses). The gateway fronts it as a
// plain API at <gateway>/library/mcp, so the subscription key, rate limit and backend key apply.
resource libraryApi 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'library'
  properties: {
    displayName: 'LibraryIQ library tools (MCP)'
    path: 'library'
    protocols: ['https']
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'api-key'
      query: 'api-key'
    }
    serviceUrl: 'https://${site.properties.defaultHostName}'
  }
}

resource mcpPost 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: libraryApi
  name: 'mcp-post'
  properties: {
    displayName: 'MCP request'
    method: 'POST'
    urlTemplate: '/mcp'
  }
}

resource mcpGet 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: libraryApi
  name: 'mcp-get'
  properties: {
    displayName: 'MCP stream (not offered by the server)'
    method: 'GET'
    urlTemplate: '/mcp'
  }
}

resource libraryApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: libraryApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/library-tools.xml')
  }
  dependsOn: [backendKeyValue]
}

// One key for the agent: model API and library tools.
resource agentSubscription 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = {
  parent: apim
  name: 'libraryiq-agent'
  properties: {
    scope: '${apim.id}/apis'
    displayName: 'libraryiq-agent'
    state: 'active'
  }
}

// Demo identities: the gateway tells the tools who is calling from the subscription name.
resource requesterSubscription 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = {
  parent: apim
  name: 'demo-requester'
  properties: {
    scope: '${apim.id}/apis'
    displayName: 'demo-requester'
    state: 'active'
  }
}

resource librarianSubscription 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = {
  parent: apim
  name: 'demo-librarian'
  properties: {
    scope: '${apim.id}/apis'
    displayName: 'demo-librarian'
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
output toolsMcpUrl string = '${apim.properties.gatewayUrl}/library/mcp'
output toolsWebApp string = site.properties.defaultHostName
