# Use Docker

## Invoke task Manager

To install invoke dependencies run the command

```bash
$ pip install -r requirements-dev.txt
```

On the invoke.yml set debug = True to see executed commands.

## Requirements

* Have a docker container name db for postgreSQL

## Init the project

The init command, build a new docker image from the Docker file and install the main project module on db.

This image contains Odoo enterprise and the custom code on the addons folder.

```bash
$ inv init
# Don't create the image on build
$ inv init ignore-image-build
```

## Start and stop container

To start or stop the container simply type

```bash
$ inv start
# to see log
$ docker logs %container-name/ID% --follow
$ inv stop
```

## Update/install Odoo module

To update or install an new module on Odoo.

```bash
$ inv run -u %modules_to_update% -i %modules_to_install%
```

## Cleaning the project

Cleaning the project: 

* remove the container
* remove the image
* remove database

Important : Volumes with data are not removed.

```bash
$ inv clean
# To clean more
$ docker system prune
```

