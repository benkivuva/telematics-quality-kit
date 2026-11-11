# Design notes

## Container base image updates

The Dockerfile uses the unpinned `python:3.12-slim` tag and runs `apt-get upgrade -y`
in the runtime stage. This was chosen to bring Debian packages in the image up to
their available security fixes and clear Trivy findings during image scans.

The trade-off is reduced build reproducibility: the same Dockerfile can produce
different base layers as the tag moves or Debian publishes package updates. A
build also depends on the package repository state at build time. Pinning the
base image by digest and managing explicit base-image refreshes would make builds
more repeatable, but requires regular digest updates to receive security fixes.

Application dependencies remain reproducible through the locked `uv.lock`
exported with hashes during the build.
