Element to install an Trove guest agent.

Note: this requires a system base image modified to include Trove source code
repositories

Environment variables:

``DIB_TROVE_DOCKER_IMAGES``
  Optional, space separated list of ``[source=]target`` docker image
  references to embed, fully extracted, into the image's containerd store
  at build time, so instances don't pull images at create time. See the
  "Guest image variables" section of
  ``doc/source/install/install-devstack.rst`` for details.
