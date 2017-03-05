import argparse
import copy
import logging
import os
import subprocess
import sys
import tempfile

import yaml

NAMESPACE_FILE = '.namespace'
CONFIG_FILE = 'kankube.yml'


class Kind(object):
    kind = None

    def __init__(self, obj, default_namespace=None):
        self.local_obj = copy.deepcopy(obj)
        self.remote_obj = None
        self.default_namespace = default_namespace

    @property
    def name(self):
        return self.local_obj['metadata']['name']

    @property
    def namespace(self):
        return self.local_obj['metadata'].get('namespace') or self.default_namespace

    @property
    def spec(self):
        return self.local_obj.get('spec')

    @property
    def inner_spec(self):
        spec = self.local_obj.get('spec', {})

        if spec.get('template', {}).get('spec'):
            spec = spec['template']['spec']

        return spec or None

    @property
    def labels(self):
        return None

    def get(self, check=None):
        self.remote_obj = call_kubectl(self, 'get', check=check)
        return self.remote_obj

    def get_pods(self):
        return None

    def apply(self, check=None):
        self.remote_obj = call_kubectl(self, 'apply', check=check)
        return self.remote_obj

    def delete(self, check=None):
        self.remote_obj = call_kubectl(self, 'delete', check=check)
        return self.remote_obj

    @classmethod
    def get_class(cls, kind):
        for klass in [
            ConfigMap,
            Deployment,
            Ingress,
            Namespace,
            Pod,
            Secret,
            Service
        ]:
            if klass.kind == kind:
                return klass

        raise ValueError('Unknown kind "{}"'.format(kind))


class ConfigMap(Kind):
    kind = 'ConfigMap'


class Deployment(Kind):
    kind = 'Deployment'

    @property
    def labels(self):
        return self.spec and self.spec.get('template', {}).get('metadata', {}).get('labels')

    def get_pods(self):
        return get_pods(self, selectors=self.labels) if self.labels else None


class Ingress(Kind):
    kind = 'Ingress'


class Namespace(Kind):
    kind = 'Namespace'

    def get_pods(self):
        return get_pods(self)


class Pod(Kind):
    kind = 'Pod'

    def get_pods(self):
        return [self]


class Secret(Kind):
    kind = 'Secret'


class Service(Kind):
    kind = 'Service'

    def get_pods(self):
        selectors = self.local_obj.get('spec', {}).get('selector')
        if selectors:
            return get_pods(self, selectors=selectors)


logger = logging.getLogger('kankube')


def _get_log_name(entry):
    return '{} ({}) in {}'.format(entry.name, entry.kind, entry.namespace)


def get_pods(obj, selectors=None):
    extras = ['get', 'pods', '-o', 'yaml']
    if selectors:
        selectors = ','.join(['{}={}'.format(key, value) for key, value in selectors.items()])
        extras.extend(['--selector', selectors])

    result = call_kubectl(obj, None, extras=extras)
    if result and result.get('items'):
        return [Pod(item, default_namespace=obj.namespace) for item in result['items']]


def call_kubectl(obj, action, check=None, extras=None, mute=False):
    if check is None:
        check = True

    cmd = ['kubectl']
    if obj.namespace:
        cmd.extend(['--namespace', obj.namespace])

    file = None
    if action == 'apply':
        file = tempfile.NamedTemporaryFile('w')
        yaml.safe_dump(obj.local_obj, file)
        cmd.extend(['apply', '-f', file.name])

    elif action == 'delete':
        cmd.extend(['delete', obj.kind.lower(), obj.name])
    elif action == 'get':
        cmd.extend(['get', obj.kind.lower(), obj.name])
        cmd.extend(['-o', 'yaml'])
    elif action == 'exec':
        cmd.extend(['exec', obj.name])

    if extras:
        cmd.extend(extras)

    logger.debug(cmd)

    try:
        try:
            result = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as error:
            if not mute:
                logger.exception('output: %s', error.output if error.output else None)

            if check:
                if error.output:
                    error.output = error.output.decode('utf-8')

                raise
            else:
                result = error.output
    finally:
        if file:
            file.close()

    if '-o' and 'yaml' in cmd:
        return yaml.safe_load(result)
    else:
        return result.decode('utf-8')


def get_config(directory=None):
    if directory is None:
        directory = os.getcwd()

    config = None

    while directory and directory != '/':
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

    while directory and directory != '/':
        if NAMESPACE_FILE in os.listdir(directory):
            with open(os.path.join(directory, NAMESPACE_FILE)) as fh:
                namespace = fh.read().strip()
                break

        directory = os.path.split(directory)[0]

    return namespace


def get_entries(filename, namespace, config=None):
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
        klass = Kind.get_class(kind)

        entries.append(klass(entry, default_namespace=namespace))

    return entries


def config(namespace, args):
    if not namespace:
        namespace = get_namespace()

    _config = get_config()
    if not _config:
        raise ValueError('Unable to find config file')

    namespace_config = get_substitutions(_config, namespace)
    if not namespace_config:
        raise ValueError('Namespace {} has no config values'.format(namespace))

    if args.get:
        print(namespace_config.get(args.get), file=sys.stdout)


def get(entries=None):
    for entry in entries:
        obj = entry.get()
        logger.info('{}\n{}'.format(_get_log_name(entry), yaml.safe_dump(obj)))


def apply(entries=None):
    for entry in entries:
        logger.info('Applying {}'.format(_get_log_name(entry)))
        entry.apply()


def delete(entries=None):
    for entry in entries:
        logger.info('Deleting {}'.format(_get_log_name(entry)))
        entry.delete()


def execute(entries, args):
    """ Assumes the labels uniquely identify the pods """
    cmd = args.cmd
    extras = ['--'] + cmd.split(' ')

    for entry in entries:
        pods = entry.get_pods()
        if not pods:
            logger.warning('Unable to find any pods for %s', _get_log_name(entry))
            continue

        for pod in pods:
            exit_code = status([pod])
            if exit_code != 0:
                logger.warning('ignoring %s since it it not available', _get_log_name(pod))
                continue

            failed = False
            try:
                output = call_kubectl(pod, 'exec', mute=True, extras=extras)
            except subprocess.CalledProcessError as error:
                failed = error
                output = error.output

            logger.info('exec result for %s: %s', _get_log_name(pod), output)
            if failed:
                raise failed


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

        status:
            observedGeneration: 2
            replicas: 1
            unavailableReplicas: 1
            updatedReplicas: 1

    :return:
    """
    exit_code = 0

    for entry in entries:
        entry.get()
        if entry.kind.lower() == 'deployment':
            entry_status = entry.remote_obj.get('status')
            if not entry_status:
                exit_code = 1
                logger.error('{} did not have a status'.format(_get_log_name(entry)))

            total = entry_status.get('replicas', 0)
            available = entry_status.get('availableReplicas', 0)
            unavailable = entry_status.get('unavailableReplicas', 0)
            updated = entry_status.get('updatedReplicas', 0)
            observed_generation = entry_status['observedGeneration']
            latest_generation = entry.remote_obj.get('metadata', {}).get('generation')

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
        elif entry.kind.lower() == 'pod':
            pod_status = entry.remote_obj.get('status', {})
            pod_metadata = entry.remote_obj.get('metadata', {})

            phase = pod_status.get('phase')
            msg = '{}: phase {}'.format(_get_log_name(entry), phase)

            deleted_at = pod_metadata.get('deletionTimestamp')
            if deleted_at:
                msg += ', deleted at {}'.format(str(deleted_at))

            logger.info(msg)

            if not phase or phase != 'Running':
                exit_code = 1
            elif deleted_at:
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
    parser.add_argument('--kind', action='append')

    get_parser = subparsers.add_parser('config')
    get_parser.add_argument('--get')
    get_parser.set_defaults(func=config)

    get_parser = subparsers.add_parser('get')
    get_parser.add_argument('filenames', nargs='+')
    get_parser.set_defaults(func=get)

    apply_parser = subparsers.add_parser('apply')
    apply_parser.add_argument('filenames', nargs='+')
    apply_parser.set_defaults(func=apply)

    delete_parser = subparsers.add_parser('delete')
    delete_parser.add_argument('filenames', nargs='+')
    delete_parser.set_defaults(func=delete)

    delete_parser = subparsers.add_parser('status')
    delete_parser.add_argument('filenames', nargs='+')
    delete_parser.set_defaults(func=status)

    delete_parser = subparsers.add_parser('exec')
    delete_parser.add_argument('filenames', nargs='+')
    delete_parser.add_argument('--cmd', required=True)
    delete_parser.set_defaults(func=execute)

    args = parser.parse_args()
    if not args.func:
        parser.print_help()
        parser.exit(1)

    if args.func == config:
        exit_code = args.func(args.namespace, args)
    else:
        # Get the entries which should be used
        entries = []
        for filename in args.filenames:
            entries.extend(get_entries(filename, args.namespace))

        # Apply any filters
        if args.kind:
            entries = [entry for entry in entries if entry.kind.lower() in args.kind]

        # Call the actual function
        if args.func in [execute]:
            exit_code = args.func(entries, args)
        else:
            exit_code = args.func(entries)

    # Exit nicely
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
