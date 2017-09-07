# Kankube

[![pypi](https://img.shields.io/pypi/v/kankube.svg)](https://pypi.python.org/pypi/kankube)

Basic kubectl wrapper

Provides basic namespace substitutions, programmatic status, and the ability to execute commands
in child pods.

# Installation

## Python

kankube is available from pypi:
```
pip install kankube
```

or, clone the repository and run setup.py install. It has been developed using python 3.5, 

## Docker

A docker image is available at quay.io/kando/kankube

# Usage

## Substitutions

Basic python style [.format](https://docs.python.org/3/library/string.html#formatstrings)
substitutions are available in yaml files. eg:

**my_deployment.yml**
```yaml
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: my_deployment
spec:
  template:
    metadata:
      labels:
        app: my_deployment
    spec:
      containers:
      - name: my_deployment_container
        image: {my-deployment-image}
```

Substitutions are defined in a 'kankube.yml' file which should be located at the top level of
your repository. Example format:

**kankube.yml**
```yaml
namespaceSubstitutions:
  my_dev_namespace:
    my-deployment-image: gcr.io/google_containers/defaultbackend:1.0
  my_prod_namespace:
    my-deployment-image: gcr.io/google_containers/defaultbackend:0.9
```

Using the above two files you can use kankube to apply or delete my_deployment with:

```
kankube --namespace my_dev_namespace apply my_deployment.yml
kankube --namespace my_dev_namespace delete my_deployment.yml
```

The ability to substitute is useful to share the same configuration values across multiple yaml 
files, or share the same yaml files between different namespaces:

```
kankube --namespace my_prod_namespace apply my_deployment.yml
kankube --namespace my_prod_namespace delete my_deployment.yml
```

## Status

The status arg can be used to programmatically query the status of any *deployment*, *daemonset*,
*job*, or *pod*. eg:

```
$> kankube --namespace my_dev_namespace status my_deployment.yml
INFO:kankube:my_deployment (Deployment) in my_dev_namespace: 1 total, 0 available, 1 unavailable, 1 updated at generation 227 (227)
$> echo $?
1
$> kankube --namespace my_dev_namespace status my_deployment.yml
INFO:kankube:my_deployment (Deployment) in my_dev_namespace: 1 total, 1 available, 0 unavailable, 1 updated at generation 227 (227)
$> echo $?
0
```

## Execute

Execute will execute the provided command in all the pods which match the target resource. To run
a command in the pod created by the deployment example above:

```
kankube --namespace my_dev_namespace exec my_deployment.yml --cmd "echo hi"
```

**WARNING**: the above example uses labels from the deployment to select which pods to exec the
the command in, make sure you labels are unique!

## Subsets

If you have a yaml file which contains multiple kinds of resource, but only wish to act on a subset
of them you can use the --kind flag, eg:

```
kankube --kind deployment apply my_deployment.yml
kankube --kind deployment status my_deployment.yml
```

# Credits

This package was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) and the
[audreyr/cookiecutter-pypackage](https://github.com/audreyr/cookiecutter-pypackage) project template.
