#!/usr/bin/env bash
# Deployment steps used by .github/workflows/deploy.yml and teardown.yml. Inputs come from the environment:
#   DEPLOY_TOOL   terraform | bicep
#   TARGET_ENV    dev | prod
#   LOCATION      Azure region (default eastus2)
#   ARM_* / AZURE_*  set by azure/login (OIDC) and the workflow env
#
#   deploy.sh provision   create/update the stack; write resource group, app, registry, vault to $GITHUB_OUTPUT
#   deploy.sh image       langgraph build, push to the registry (az acr login with the OIDC session), roll the app
#   deploy.sh smoke       GET /ok on the Agent Server and check the LangSmith key exists in Key Vault
#   deploy.sh destroy     tear the environment down (teardown workflow only)
#
# Never run from this repository: DEPLOY_ENABLED is not set.
set -euo pipefail

TOOL="${DEPLOY_TOOL:-terraform}"
ENV_NAME="${TARGET_ENV:?TARGET_ENV is required}"
LOCATION="${LOCATION:-eastus2}"
STACK="infra/terraform"
OUT="${GITHUB_OUTPUT:-/dev/stdout}"
RG_BICEP="rg-lcdesk-${ENV_NAME}-${LOCATION}-001"

log() { echo "::group::$*"; }
end() { echo "::endgroup::"; }

tf_init() {
  : "${TFSTATE_RESOURCE_GROUP:?set repo/environment variable TFSTATE_RESOURCE_GROUP}"
  : "${TFSTATE_STORAGE_ACCOUNT:?set repo/environment variable TFSTATE_STORAGE_ACCOUNT}"
  terraform -chdir="$STACK" init -input=false \
    -backend-config="envs/${ENV_NAME}.backend.hcl" \
    -backend-config="resource_group_name=${TFSTATE_RESOURCE_GROUP}" \
    -backend-config="storage_account_name=${TFSTATE_STORAGE_ACCOUNT}" \
    -backend-config="container_name=${TFSTATE_CONTAINER:-tfstate}"
}

provision() {
  if [[ "$TOOL" == "terraform" ]]; then
    log "terraform apply ($ENV_NAME)"
    tf_init
    terraform -chdir="$STACK" apply -auto-approve -input=false -var-file="envs/${ENV_NAME}.tfvars" -var "location=${LOCATION}"
    {
      echo "resource_group=$(terraform -chdir="$STACK" output -raw AZURE_RESOURCE_GROUP)"
      echo "app=$(terraform -chdir="$STACK" output -raw container_app_name)"
      echo "registry=$(terraform -chdir="$STACK" output -raw registry_login_server)"
      echo "vault=$(terraform -chdir="$STACK" output -raw key_vault_name)"
    } >> "$OUT"
    end
  else
    log "bicep deployment ($ENV_NAME)"
    az group create -n "$RG_BICEP" -l "$LOCATION" --tags workload=lcdesk environment="$ENV_NAME" -o none
    pw="$(openssl rand -hex 24)"
    echo "::add-mask::$pw"
    private=false; [[ "$ENV_NAME" == "prod" ]] && private=true
    res=$(az deployment group create -g "$RG_BICEP" -n "lcdesk-${GITHUB_RUN_ID:-local}" -f infra/bicep/main.bicep \
      -p environment="$ENV_NAME" privateNetworking="$private" postgresAdminPassword="$pw" --query properties.outputs -o json)
    {
      echo "resource_group=$RG_BICEP"
      echo "app=$(jq -r .containerAppName.value <<<"$res")"
      echo "registry=$(az acr list -g "$RG_BICEP" --query '[0].loginServer' -o tsv)"
      echo "vault=$(jq -r .keyVaultName.value <<<"$res")"
    } >> "$OUT"
    end
  fi
}

image() {
  : "${RESOURCE_GROUP:?}" "${APP:?}" "${REGISTRY:?}"
  log "langgraph build and push"
  pip install --quiet -r requirements.lock && pip install --quiet --no-deps -e .
  tag="${REGISTRY}/lcdesk-agent-server:${GITHUB_SHA:-local}"
  langgraph build -t "$tag"
  az acr login --name "${REGISTRY%%.*}"
  docker push "$tag"
  az containerapp update -g "$RESOURCE_GROUP" -n "$APP" --image "$tag" -o none
  end
}

smoke() {
  : "${RESOURCE_GROUP:?}" "${APP:?}" "${VAULT:?}"
  log "smoke checks"
  az keyvault secret show --vault-name "$VAULT" -n langsmith-api-key --query id -o tsv >/dev/null \
    || { echo "::error::write the LangSmith key to Key Vault secret langsmith-api-key first (docs/deployment.md)"; exit 1; }
  fqdn=$(az containerapp show -g "$RESOURCE_GROUP" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)
  if [[ "$ENV_NAME" == "prod" ]]; then
    echo "::notice::prod ingress is internal; run the /ok check from inside the VNet"
  else
    curl -fsS "https://${fqdn}/ok"
  fi
  end
}

destroy() {
  if [[ "$TOOL" == "terraform" ]]; then
    tf_init
    terraform -chdir="$STACK" destroy -auto-approve -input=false -var-file="envs/${ENV_NAME}.tfvars" -var "location=${LOCATION}"
  else
    az group delete -n "$RG_BICEP" --yes
  fi
}

case "${1:-}" in
  provision | image | smoke | destroy) "$1" ;;
  *) echo "usage: deploy.sh provision|image|smoke|destroy" >&2; exit 2 ;;
esac
