using 'main.bicep'

// The environment in resource group rg-libraryiq-pub (UAE North).
param accountName = 'libiqpubvtyj5'
param apimName = 'apim-libiq-1n9l68'

// Object ID of the deployer: az ad signed-in-user show --query id -o tsv
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID')

// Sign-in name: az ad signed-in-user show --query userPrincipalName -o tsv
param publisherEmail = readEnvironmentVariable('AZURE_PRINCIPAL_NAME')

// The two role assignments in this environment were created by CLI. Use true for a fresh deployment.
param createRoleAssignments = false
