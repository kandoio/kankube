import argparse
import copy
import logging
import os

import pykube
import yaml

NAMESPACE_FILE = '.namespace'
CONFIG_FILE = 'kankube.yml'

OBJECTS = {
    'ConfigMap': pykube.ConfigMap,
    'Deployment': pykube.Deployment,
    'Ingress': pykube.Ingress,
    'Pod': pykube.Pod,
    'Secret': pykube.Secret,
    'Service': pykube.Service
}

BASIC_CONFIG = {
    "clusters": [
        {
            "name": "self",
            "cluster": {
                "server": None,
            },
        },
    ],
    "users": [
        {
            "name": "self",
            "user": {},
        },
    ],
    "contexts": [
        {
            "name": "self",
            "context": {
                "cluster": "self",
                "user": "self",
            },
        }
    ],
    "current-context": "self",
}

API = None
logger = logging.getLogger('kankube')


def get_config(directory=None):
    if directory is None:
        directory = os.getcwd()

    config = None

    while directory:
        if CONFIG_FILE in os.listdir(directory):
            with open(os.path.join(directory, CONFIG_FILE)) as fh:
                config = list(yaml.safe_load_all(fh))
                break

        directory = os.path.split(directory)[0]

    if config:
        if len(config) > 1:
            raise ValueError('The config file can only contain a single entry!')
        config = config[0]

    return config


def get_substitutions(config, namespace):
    if config:
        return config.get('namespaceSubstitutions', {}).get(namespace)


def get_namespace(directory=None):
    if directory is None:
        directory = os.getcwd()

    namespace = 'default'

    while directory:
        if NAMESPACE_FILE in os.listdir(directory):
            with open(os.path.join(directory, NAMESPACE_FILE)) as fh:
                namespace = fh.read().strip()
                break

        directory = os.path.split(directory)[0]

    return namespace


def get_entries(filename, namespace, api=None, config=None):
    if api is None:
        api = API

    if os.path.isfile(filename):
        file_path = os.path.abspath(filename)
    else:
        file_path = os.path.join(os.getcwd(), filename)

    if not filename.endswith('yml'):
        if os.path.exists(file_path + '.yml'):
            file_path += '.yml'
        else:
            logger.info('Ignoring file {}'.format(filename))
            return []

    if not os.path.exists(file_path):
        raise ValueError('Unknown file {}'.format(file_path))

    if not config:
        config = get_config(os.path.dirname(file_path))

    if not namespace:
        namespace = get_namespace(directory=os.path.dirname(file_path))

    with open(file_path) as fh:
        data = fh.read()
        substitutions = get_substitutions(config, namespace)
        if substitutions:
            data = data.format(**substitutions)

        raw_entries = list(yaml.safe_load_all(data))

    entries = []
    for entry in raw_entries:
        kind = entry['kind']
        klass = OBJECTS[kind]

        entries.append(klass(api, entry, namespace=namespace))

    return entries


def create(filename=None, entries=None, namespace=None):
    if not entries:
        entries = get_entries(filename, namespace)

    for entry in entries:
        if not entry.exists():
            logger.info('Creating {} ({}) in {}'.format(entry.name, entry.kind, entry.namespace))
            entry.create()


def apply(filename=None, entries=None, namespace=None):
    if not entries:
        entries = get_entries(filename, namespace)

    for entry in entries:
        if entry.exists():
            logger.info('Applying {} ({}) in {}'.format(entry.name, entry.kind, entry.namespace))
            entry.update()
        else:
            create(entries=[entry])


def delete(filename=None, entries=None, namespace=None):
    if not entries:
        entries = get_entries(filename, namespace)

    for entry in entries:
        if entry.exists():
            logger.info('Deleting {} ({}) in {}'.format(entry.name, entry.kind, entry.namespace))
            entry.delete()


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.ERROR)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='subparser_name')

    parser.add_argument('--namespace')

    parser.add_argument('--host', default=os.environ.get('KUBERNETES_HOST'))
    parser.add_argument('--token', default=os.environ.get('KUBERNETES_TOKEN'))
    parser.add_argument('--username', default=os.environ.get('KUBERNETES_USERNAME'))
    parser.add_argument('--password', default=os.environ.get('KUBERNETES_PASSWORD'))

    create_parser = subparsers.add_parser('create')
    create_parser.add_argument('filenames', nargs='+')

    apply_parser = subparsers.add_parser('apply')
    apply_parser.add_argument('filenames', nargs='+')

    delete_parser = subparsers.add_parser('delete')
    delete_parser.add_argument('filenames', nargs='+')

    args = parser.parse_args()

    config = None
    if args.host or args.username or args.password or args.token:
        obj = copy.deepcopy(BASIC_CONFIG)
        obj['clusters'][0]['cluster']['server'] = args.host
        obj['users'][0]['user'] = {
            'username': args.username,
            'password': args.password,
            'token': args.token
        }
        config = pykube.KubeConfig(obj)
    elif os.path.isfile(os.path.expanduser("~/.kube/config")):
        config = pykube.KubeConfig.from_file(os.path.expanduser("~/.kube/config"))
    else:
        parser.error('You must provide a host, username/password, token, or have a ~/.kube/config file')

    global API
    API = pykube.HTTPClient(config)

    if args.subparser_name == 'create':
        for filename in args.filenames:
            create(filename=filename, namespace=args.namespace)
    elif args.subparser_name == 'apply':
        for filename in args.filenames:
            apply(filename=filename, namespace=args.namespace)
    elif args.subparser_name == 'delete':
        for filename in args.filenames:
            delete(filename=filename, namespace=args.namespace)

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
