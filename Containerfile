FROM registry.access.redhat.com/ubi10/python-312-minimal:latest
# This prevents Python from writing out pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# This keeps Python from buffering stdin/stdout
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Install additional package according to guide here:
# https://catalog.redhat.com/software/containers/rhel10/python-312-minimal/677d3146199814f7fac1401d?container-tabs=overview
USER 0
RUN INSTALL_PKGS="skopeo" && \
    mkdir -p /var/cache/yum/metadata && \
    microdnf -y --setopt=tsflags=nodocs --setopt=install_weak_deps=0 install $INSTALL_PKGS && \
    microdnf -y clean all --enablerepo='*'
USER 1001

COPY requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt

COPY programable-exporter.py /app/programable-exporter.py
COPY programable-exporter.ini /etc/programable-exporter.ini

ENV CONFIG_FILE /etc/programable-exporter.ini

EXPOSE 8000

ENTRYPOINT ["python3", "programable-exporter.py"]
