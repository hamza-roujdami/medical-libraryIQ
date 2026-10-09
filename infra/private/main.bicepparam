using 'main.bicep'

// Object ID: az ad signed-in-user show --query id -o tsv
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID')

// Sign-in name: az ad signed-in-user show --query userPrincipalName -o tsv
param principalName = readEnvironmentVariable('AZURE_PRINCIPAL_NAME')

// Contents of a public key file, for example ~/.ssh/id_ed25519.pub
param vmSshPublicKey = readEnvironmentVariable('VM_SSH_PUBLIC_KEY')
