targetScope = 'resourceGroup'

param name string

@description('AI Search can sit in a different region from the Foundry account when that region has no capacity. Sweden Central had none for this subscription.')
param location string

param tags object

// Same settings as the official sample's own Search service: private, Entra auth, system identity.
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  sku: { name: 'standard' }
  properties: {
    disableLocalAuth: false
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http401WithBearerChallenge' } }
    encryptionWithCmk: { enforcement: 'Unspecified' }
    hostingMode: 'default'
    partitionCount: 1
    replicaCount: 1
    publicNetworkAccess: 'disabled'
    semanticSearch: 'disabled'
    networkRuleSet: {
      bypass: 'None'
      ipRules: []
    }
  }
}

output id string = search.id
output name string = search.name
