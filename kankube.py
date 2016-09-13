import argparse
import copy
import json
import logging
import os
import sys

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

logger = logging.getLogger('kankube')


def _get_log_name(entry):
    return '{} ({}) in {}'.format(entry.name, entry.kind, entry.namespace)


def get_config(directory=None):
    if directory is None:
        directory = os.getcwd()

    config = None

    while directory:
        if CONFIG_FILE in os.listdir(directory):
            with open(os.path.join(directory, CONFIG_FILE)) as fh:
                config = dict(yaml.safe_load(fh))
                break

        directory = os.path.split(directory)[0]

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


def get_entries(filename, namespace, api, config=None):
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


def get(entries=None):
    for entry in entries:
        entry.reload()
        # json.dumps is the best way to pretty print a dict, pprint is rubbish.
        logger.info('{}\n{}'.format(_get_log_name(entry), json.dumps(entry.obj, indent=4)))


def create(entries=None):
    for entry in entries:
        if not entry.exists():
            logger.info('Creating {}'.format(_get_log_name(entry)))
            entry.create()


def apply(entries=None):
    for entry in entries:
        if entry.exists():
            logger.info('Applying {}'.format(_get_log_name(entry)))
            entry.update()
        else:
            create(entries=[entry])


def delete(entries=None):
    for entry in entries:
        if entry.exists():
            logger.info('Deleting {}'.format(_get_log_name(entry)))
            entry.delete()


def status(entries=None):
    """ Check the status of entries

    Deployment example:
        "status": {
            "availableReplicas": 1,
            "observedGeneration": 4,
            "unavailableReplicas": 2,
            "replicas": 3,
            "updatedReplicas": 2
        }

    :return:
    """
    exit_code = 0

    for entry in entries:
        entry.reload()
        if entry.kind.lower() == 'deployment':
            entry_status = entry.obj.get('status')
            if not entry_status:
                exit_code = 1
                logger.error('{} did not have a status'.format(_get_log_name(entry)))

            total = entry_status['replicas']
            available = entry_status['availableReplicas']
            unavailable = entry_status.get('unavailableReplicas', 0)
            updated = entry_status['updatedReplicas']
            observed_generation = entry_status['observedGeneration']
            latest_generation = entry.obj.get('metadata', {}).get('generation')

            logger.info('{}: {} total, {} available, {} unavailable, {} updated at generation {} ({})'.format(
                _get_log_name(entry), total, available, unavailable, updated, observed_generation,
                latest_generation
            ))

            if observed_generation == latest_generation and \
                    total == available and \
                    total == updated and \
                    unavailable == 0:
                # All is well in the world
                pass
            else:
                exit_code = 1
        else:
            exit_code = 1
            logger.warning('Unable to get status for {}'.format(_get_log_name(entry)))

    return exit_code


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.ERROR)

    parser = argparse.ArgumentParser()
    parser.set_defaults(func=None)

    subparsers = parser.add_subparsers(dest='subparser_name')

    parser.add_argument('--namespace')

    parser.add_argument('--host', default=os.environ.get('KUBERNETES_HOST'))
    parser.add_argument('--token', default=os.environ.get('KUBERNETES_TOKEN'))
    parser.add_argument('--username', default=os.environ.get('KUBERNETES_USERNAME'))
    parser.add_argument('--password', default=os.environ.get('KUBERNETES_PASSWORD'))

    parser.add_argument('--kind', action='append')

    get_parser = subparsers.add_parser('get')
    get_parser.add_argument('filenames', nargs='+')
    get_parser.set_defaults(func=get)

    create_parser = subparsers.add_parser('create')
    create_parser.add_argument('filenames', nargs='+')
    create_parser.set_defaults(func=create)

    apply_parser = subparsers.add_parser('apply')
    apply_parser.add_argument('filenames', nargs='+')
    apply_parser.set_defaults(func=apply)

    delete_parser = subparsers.add_parser('delete')
    delete_parser.add_argument('filenames', nargs='+')
    delete_parser.set_defaults(func=delete)

    delete_parser = subparsers.add_parser('status')
    delete_parser.add_argument('filenames', nargs='+')
    delete_parser.set_defaults(func=status)

    args = parser.parse_args()
    if not args.func:
        parser.print_help()
        parser.exit(1)

    # Figure out how to talk to kubenetes
    pykube_config = None
    if args.host or args.username or args.password or args.token:
        obj = copy.deepcopy(BASIC_CONFIG)
        obj['clusters'][0]['cluster']['server'] = args.host
        obj['users'][0]['user'] = {
            'username': args.username,
            'password': args.password,
            'token': args.token
        }
        pykube_config = pykube.KubeConfig(obj)
    elif os.path.isfile(os.path.expanduser("~/.kube/config")):
        pykube_config = pykube.KubeConfig.from_file(os.path.expanduser("~/.kube/config"))
    else:
        parser.error('You must provide a host, username/password, token, or have a ~/.kube/config file')

    api = pykube.HTTPClient(pykube_config)

    # Get the entries which should be used
    entries = []
    for filename in args.filenames:
        entries.extend(get_entries(filename, args.namespace, api))

    # Apply any filters
    if args.kind:
        entries = [entry for entry in entries if entry.kind.lower() in args.kind]

    # Call the actual function
    exit_code = args.func(entries)

    # Exit nicely
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
