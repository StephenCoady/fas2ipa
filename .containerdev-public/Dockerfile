FROM registry.fedoraproject.org/fedora:latest
MAINTAINER Rick Elrod <relrod@redhat.com>

RUN dnf -y install \
    vim git python3-pip && \
    pip3 install python-fedora git+https://github.com/opennode/python-freeipa requests progressbar2

VOLUME /project

WORKDIR /project
