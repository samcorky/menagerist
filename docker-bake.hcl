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

group "default" {
  targets = ["menagerist"]
}

target "menagerist" {
  context    = "."
  dockerfile = "Dockerfile"
  platforms  = split(",", PLATFORMS)
  tags = [
    "${REGISTRY}/${OWNER}/${IMAGE_NAME}:${IMAGE_TAG}",
    "${REGISTRY}/${OWNER}/${IMAGE_NAME}:latest",
  ]

  args = {
    VERSION                         = "${VERSION}"
    MENAGERIST_BUILD_COMMIT_SHA     = "${COMMIT_SHA}"
    MENAGERIST_BUILD_BRANCH         = "${BRANCH}"
    MENAGERIST_BUILD_REPOSITORY_URL = "${REPOSITORY_URL}"
    MENAGERIST_BUILD_TIMESTAMP      = "${BUILD_TIMESTAMP}"
    MENAGERIST_BUILD_DIRTY          = "${DIRTY}"
  }
}

group "local" {
  targets = ["local"]
}

target "local" {
  inherits  = ["menagerist"]
  platforms = ["linux/amd64"]
  tags      = ["${IMAGE_NAME}:local"]
  output    = ["type=docker"]
}
