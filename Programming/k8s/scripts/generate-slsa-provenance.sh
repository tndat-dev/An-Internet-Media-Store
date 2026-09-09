#!/usr/bin/env sh
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: $0 COMPONENT IMAGE@SHA256 SBOM_FILE OUTPUT_FILE" >&2
  exit 2
fi

component=$1
image=$2
sbom_file=$3
output=$4

test -f "$sbom_file"
case "$image" in
  *@sha256:*) ;;
  *) echo "image must be immutable (repository@sha256:digest)" >&2; exit 2 ;;
esac

sbom_sha256="$(sha256sum "$sbom_file" | awk '{print $1}')"

if [ -n "${GITHUB_ACTIONS:-}" ]; then
  source_url="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}"
  commit_sha="${GITHUB_SHA}"
  pipeline_url="${source_url}/actions/runs/${GITHUB_RUN_ID}"
  job_url="${pipeline_url}/attempts/${GITHUB_RUN_ATTEMPT}"
  invocation="${GITHUB_RUN_ID}/${GITHUB_RUN_ATTEMPT}/${component}"
  build_type="https://github.com/aims/buildtypes/container/v1"
  builder_id="https://github.com/${GITHUB_REPOSITORY}/.github/workflows/aims-supply-chain.yml@${GITHUB_REF}"
  started_on="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
else
  source_url="${CI_PROJECT_URL}"
  commit_sha="${CI_COMMIT_SHA}"
  pipeline_url="${CI_PIPELINE_URL}"
  job_url="${CI_JOB_URL}"
  invocation="${CI_PIPELINE_ID}/${CI_JOB_ID}/${component}"
  build_type="https://gitlab.com/aims/buildtypes/container/v1"
  builder_id="https://gitlab.com/aims/gitlab-runner/container-build@v1"
  started_on="${CI_JOB_STARTED_AT:-${CI_PIPELINE_CREATED_AT}}"
fi

source_uri="git+${source_url}.git"
source_ref="git+${source_url}.git@${commit_sha}"
finished_on="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Cosign wraps this predicate in an in-toto Statement and binds its subject to
# the immutable OCI digest. The schema is SLSA build provenance v1.
jq -n \
  --arg buildType "$build_type" \
  --arg component "$component" \
  --arg sourceUri "$source_uri" \
  --arg sourceRef "$source_ref" \
  --arg commit "$commit_sha" \
  --arg pipeline "$pipeline_url" \
  --arg job "$job_url" \
  --arg invocation "$invocation" \
  --arg started "$started_on" \
  --arg finished "$finished_on" \
  --arg sbom "$sbom_file" \
  --arg sbomSha "$sbom_sha256" \
  --arg image "$image" \
  --arg builderId "$builder_id" \
  '{
    buildDefinition: {
      buildType: $buildType,
      externalParameters: {
        source: {uri: $sourceUri, ref: $commit},
        component: $component,
        image: $image
      },
      internalParameters: {
        pipeline: $pipeline,
        job: $job
      },
      resolvedDependencies: [
        {uri: $sourceRef, digest: {gitCommit: $commit}},
        {uri: ("file:" + $sbom), digest: {sha256: $sbomSha}}
      ]
    },
    runDetails: {
      builder: {id: $builderId},
      metadata: {
        invocationId: $invocation,
        startedOn: $started,
        finishedOn: $finished
      },
      byproducts: [
        {name: $sbom, digest: {sha256: $sbomSha}}
      ]
    }
  }' > "$output"

jq -e '.buildDefinition.buildType and .buildDefinition.externalParameters and .runDetails.builder.id' "$output" >/dev/null
