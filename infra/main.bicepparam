using 'main.bicep'

// Object ID of the deployer: az ad signed-in-user show --query id -o tsv
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID')

// Sign-in name: az ad signed-in-user show --query userPrincipalName -o tsv
param principalName = readEnvironmentVariable('AZURE_PRINCIPAL_NAME')
