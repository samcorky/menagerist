// docker-bake.hcl

variable "REGISTRY" {
  default = "ghcr.io"
}

variable "OWNER" {
  default = "samcorky"
}

variable "IMAGE_NAME" {
  default = "menagerist"
}

variable "VERSION" {
  default = ""
}

variable "COMMIT_SHA" {
  default = ""
}

variable "BRANCH" {
  default = ""
}

variable "REPOSITORY_URL" {
  default = ""
}

variable "BUILD_TIMESTAMP" {
  default = ""
}

variable "DIRTY" {
  default = ""
}

variable "PLATFORMS" {
  default = "linux/amd64,linux/arm64"
}

variable "IMAGE_TAG" {
  default = "dev"
}

function "tag" {
  params = [component]
  result = [
    "${REGISTRY}/${OWNER}/${IMAGE_NAME}-${component}:${IMAGE_TAG}",
    "${REGISTRY}/${OWNER}/${IMAGE_NAME}-${component}:latest",
  ]
}

group "default" {
  targets = ["backend", "frontend"]
}

target "_common" {
  platforms = split(",", PLATFORMS)
}

target "backend" {
  inherits   = ["_common"]
  context    = "."
  dockerfile = "backend/Dockerfile"
  tags       = tag("backend")

  args = {
    SETUPTOOLS_SCM_PRETEND_VERSION  = "${VERSION}"
    MENAGERIST_BUILD_COMMIT_SHA     = "${COMMIT_SHA}"
    MENAGERIST_BUILD_BRANCH         = "${BRANCH}"
    MENAGERIST_BUILD_REPOSITORY_URL = "${REPOSITORY_URL}"
    MENAGERIST_BUILD_TIMESTAMP      = "${BUILD_TIMESTAMP}"
    MENAGERIST_BUILD_DIRTY          = "${DIRTY}"
  }
}

target "frontend" {
  inherits   = ["_common"]
  context    = "."
  dockerfile = "frontend/Dockerfile"
  tags       = tag("frontend")

  args = {
    VERSION                    = "${VERSION}"
    MENAGERIST_BUILD_COMMIT_SHA = "${COMMIT_SHA}"
    MENAGERIST_BUILD_TIMESTAMP  = "${BUILD_TIMESTAMP}"
  }
}

group "local" {
  targets = ["backend-local", "frontend-local"]
}

target "backend-local" {
  inherits  = ["backend"]
  platforms = ["linux/amd64"]
  tags      = ["${IMAGE_NAME}-backend:local"]
  output    = ["type=docker"]
}

target "frontend-local" {
  inherits  = ["frontend"]
  platforms = ["linux/amd64"]
  tags      = ["${IMAGE_NAME}-frontend:local"]
  output    = ["type=docker"]
}
