# Building the image
# docker build --tag project-name:image-version .
# exemple: docker build --tag eze:1.0 .
# or simplye run docker build -t <project_trigramme>/odoo .
# Dome files or directories can be ignored with the .dockerignore file

# Use the official Odoo image as a parent image.
FROM odoo:13.0

# launch command as root
USER root

# Create new directory for enterprise addons
# Todo this can be in a parent image
RUN mkdir -p /mnt/enterprise-addons \
    && chown -R odoo /mnt/enterprise-addons

# copy enterprise addons on /mnt/enterprise-addons
COPY ./docker/enterprise  /mnt/enterprise-addons


# Create new directory for EPL addons
# RUN mkdir -p /mnt/epl-addons \
#     && chown -R odoo /mnt/epl-addons

# copy custom addons and epl addons
COPY ./addons /mnt/extra-addons/
# COPY ./eezee_platinum /mnt/epl-addons/

# copy odoo configuration
COPY ./requirements.txt /etc/odoo/
COPY ./docker/conf/odoo.conf /etc/odoo/

# Install requirements.txt
RUN python3 -m pip install -r /etc/odoo/requirements.txt

VOLUME ["/mnt/enterprise-addons"]

# Set default user when running the container
USER odoo
