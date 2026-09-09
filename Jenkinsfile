// CI only: Jenkins never applies manifests to production. It updates a GitOps
// branch/PR after image verification; Argo CD is the only CD reconciler.
pipeline {
  agent none
  options { timestamps(); disableConcurrentBuilds() }
  environment {
    IMAGE_REPOSITORY = "${env.IMAGE_REPOSITORY ?: 'registry.example.com/aims'}"
    IMAGE_TAG = "${env.GIT_COMMIT?.take(12) ?: 'dev'}"
  }
  stages {
    stage('Test') {
      agent {
        kubernetes {
          yaml '''
apiVersion: v1
kind: Pod
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile: {type: RuntimeDefault}
  containers:
    - name: python
      image: python:3.12-slim
      command: [cat]
      tty: true
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: {drop: [ALL]}
      volumeMounts: [{name: tmp, mountPath: /tmp}]
  volumes: [{name: tmp, emptyDir: {}}]
'''
        }
      }
      steps {
        container('python') {
          sh 'pip install --no-cache-dir -r Programming/backend/requirements.txt'
          sh 'cd Programming/backend && pytest -q'
        }
      }
    }
    stage('Build, scan and sign') {
      when { expression { return env.PUBLISH_IMAGES == 'true' } }
      steps {
        error('Configure a rootless BuildKit/Kaniko agent and registry/Cosign credentials before enabling PUBLISH_IMAGES=true.')
      }
    }
    stage('Update GitOps') {
      when { expression { return env.PUBLISH_IMAGES == 'true' } }
      steps {
        error('Use a short-lived Git credential to create a GitOps PR containing immutable image digests; do not use kubectl apply.')
      }
    }
  }
}
