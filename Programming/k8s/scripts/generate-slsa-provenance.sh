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
source_uri="git+${CI_PROJECT_URL}.git"
source_ref="git+${CI_PROJECT_URL}.git@${CI_COMMIT_SHA}"
started_on="${CI_JOB_STARTED_AT:-${CI_PIPELINE_CREATED_AT}}"
finished_on="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Cosign wraps this predicate in an in-toto Statement and binds its subject to
# the immutable OCI digest. The schema is SLSA build provenance v1.
jq -n \
  --arg buildType "https://gitlab.com/aims/buildtypes/container/v1" \
  --arg component "$component" \
  --arg sourceUri "$source_uri" \
  --arg sourceRef "$source_ref" \
  --arg commit "$CI_COMMIT_SHA" \
  --arg pipeline "$CI_PIPELINE_URL" \
  --arg job "$CI_JOB_URL" \
  --arg invocation "$CI_PIPELINE_ID/$CI_JOB_ID/$component" \
  --arg started "$started_on" \
  --arg finished "$finished_on" \
  --arg sbom "$sbom_file" \
  --arg sbomSha "$sbom_sha256" \
  --arg image "$image" \
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
      builder: {id: "https://gitlab.com/aims/gitlab-runner/container-build@v1"},
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
