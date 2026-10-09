targetScope = 'resourceGroup'

param location string
param namePrefix string
param token string
param tags object
param bastionSubnetId string
param vmSubnetId string
param vmSize string

param adminUsername string = 'azureuser'

@description('SSH public key for the admin user.')
param sshPublicKey string

resource bastionIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-bas-${namePrefix}-${token}'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}

// The only way in from outside. Standard SKU with tunneling lets VS Code
// Remote-SSH and `az network bastion ssh` connect from a laptop.
resource bastion 'Microsoft.Network/bastionHosts@2024-05-01' = {
  name: 'bas-${namePrefix}-${token}'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    enableTunneling: true
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          subnet: { id: bastionSubnetId }
          publicIPAddress: { id: bastionIp.id }
        }
      }
    ]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-jump-${namePrefix}-${token}'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          subnet: { id: vmSubnetId }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'vm-jump-${namePrefix}-${token}'
  location: location
  tags: tags
  properties: {
    hardwareProfile: { vmSize: vmSize }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: { storageAccountType: 'Standard_LRS' }
      }
    }
    osProfile: {
      computerName: 'jump'
      adminUsername: adminUsername
      customData: base64(loadTextContent('jump-cloud-init.yaml'))
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [{ id: nic.id }]
    }
  }
}

output vmName string = vm.name
output bastionName string = bastion.name
