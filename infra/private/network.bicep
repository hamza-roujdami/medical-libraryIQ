targetScope = 'resourceGroup'

param location string
param namePrefix string
param token string
param tags object

param vnetAddressPrefix string = '10.60.0.0/16'

var natName = 'nat-${namePrefix}-${token}'

resource natIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-nat-${namePrefix}-${token}'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}

// Outbound internet for the agent and jump subnets (public lookup APIs, package installs).
resource nat 'Microsoft.Network/natGateways@2024-05-01' = {
  name: natName
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    idleTimeoutInMinutes: 4
    publicIpAddresses: [{ id: natIp.id }]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${namePrefix}-${token}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressPrefix] }
    subnets: [
      {
        name: 'agent-subnet'
        properties: {
          addressPrefix: '10.60.0.0/24'
          natGateway: { id: nat.id }
          delegations: [
            {
              name: 'Microsoft.App/environments'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'pe-subnet'
        properties: { addressPrefix: '10.60.1.0/24' }
      }
      {
        name: 'app-subnet'
        properties: {
          addressPrefix: '10.60.2.0/26'
          delegations: [
            {
              name: 'Microsoft.Web/serverFarms'
              properties: { serviceName: 'Microsoft.Web/serverFarms' }
            }
          ]
        }
      }
      {
        name: 'AzureBastionSubnet'
        properties: { addressPrefix: '10.60.3.0/26' }
      }
      {
        name: 'vm-subnet'
        properties: {
          addressPrefix: '10.60.4.0/27'
          natGateway: { id: nat.id }
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output peSubnetId string = '${vnet.id}/subnets/pe-subnet'
output appSubnetId string = '${vnet.id}/subnets/app-subnet'
output bastionSubnetId string = '${vnet.id}/subnets/AzureBastionSubnet'
output vmSubnetId string = '${vnet.id}/subnets/vm-subnet'
