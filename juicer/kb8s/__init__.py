# coding=utf-8
import json
import logging.config

from kubernetes import client
from kubernetes.client.rest import ApiException

logging.config.fileConfig('logging_config.ini')
log = logging.getLogger('juicer.kb8s')


def eval_and_kill_pending_jobs(cluster, timeout=60 * 5):
    configuration = client.Configuration()
    configuration.host = cluster['address']
    configuration.verify_ssl = False
    configuration.debug = False
    if 'general_parameters' not in cluster:
        raise ValueError('Incorrect cluster config.')

    cluster_params = {}
    for parameter in cluster['general_parameters'].split(','):
        key, value = parameter.split('=')
        if key.startswith('kubernetes'):
            cluster_params[key] = value

    token = cluster['auth_token']
    configuration.api_key = {"authorization": "Bearer " + token}
    # noinspection PyUnresolvedReferences
    client.Configuration.set_default(configuration)

    namespace = cluster_params['kubernetes.namespace']

    api = client.ApiClient(configuration)
    batch_api = client.BatchV1Api(api)

    ret = batch_api.list_namespaced_job(namespace=namespace, watch=False)
    for i in ret.items:
        print(i.status)


def delete_kb8s_job(workflow_id, cluster):
    return
    configuration = client.Configuration()
    configuration.host = cluster['address']
    configuration.verify_ssl = False
    configuration.debug = False
    if 'general_parameters' not in cluster:
        raise ValueError('Incorrect cluster config.')

    cluster_params = {}
    for parameter in cluster['general_parameters'].split(','):
        key, value = parameter.split('=')
        if key.startswith('kubernetes'):
            cluster_params[key] = value

    token = cluster['auth_token']
    configuration.api_key = {"authorization": "Bearer " + token}
    # noinspection PyUnresolvedReferences
    client.Configuration.set_default(configuration)

    name = 'job-{}'.format(workflow_id)
    namespace = cluster_params['kubernetes.namespace']

    api = client.ApiClient(configuration)
    batch_api = client.BatchV1Api(api)

    try:
        log.info('Deleting Kubernetes job %s', name)
        batch_api.delete_namespaced_job(
            name, namespace, grace_period_seconds=10, pretty=True)
    except ApiException as e:
        print("Exception when calling BatchV1Api->: {}\n".format(e))


def create_kb8s_job(workflow_id, minion_cmd, cluster):
    configuration = client.Configuration()
    configuration.host = cluster['address']
    configuration.verify_ssl = False
    configuration.debug = False
    if 'general_parameters' not in cluster:
        raise ValueError('Incorrect cluster config.')

    cluster_params = {}
    for parameter in cluster['general_parameters'].split(','):
        key, value = parameter.split('=')
        if key.startswith('kubernetes'):
            cluster_params[key] = value
    env_vars = {
        'HADOOP_CONF_DIR': '/usr/local/juicer/conf',
    }

    token = cluster['auth_token']
    configuration.api_key = {"authorization": "Bearer " + token}
    # noinspection PyUnresolvedReferences
    client.Configuration.set_default(configuration)

    job = client.V1Job(api_version="batch/v1", kind="Job")
    name = 'job-{}'.format(workflow_id)
    container_name = 'juicer-job'
    container_image = cluster_params['kubernetes.container']
    namespace = cluster_params['kubernetes.namespace']
    pull_policy = cluster_params.get('kubernetes.pull_policy', 'Always')

    gpus = int(cluster_params.get('kubernetes.resources.gpus', 0))

    print('-' * 30)
    print('GPU KB8s specification: ' + str(gpus))
    print('-' * 30)
    log.info('GPU specification: %s', gpus)

    job.metadata = client.V1ObjectMeta(namespace=namespace, name=name)
    job.status = client.V1JobStatus()

    # Now we start with the Template...
    template = client.V1PodTemplate()
    template.template = client.V1PodTemplateSpec()

    # Passing Arguments in Env:
    env_list = []
    for env_name, env_value in env_vars.items():
        env_list.append(client.V1EnvVar(name=env_name, value=env_value))

    # Subpath implies that the file is stored as a config map in kb8s
    volume_mounts = [
        client.V1VolumeMount(
            name='juicer-config', sub_path='juicer-config.yaml',
            mount_path='/usr/local/juicer/conf/juicer-config.yaml'),
        client.V1VolumeMount(
            name='hdfs-site', sub_path='hdfs-site.xml',
            mount_path='/usr/local/juicer/conf/hdfs-site.xml'),
        client.V1VolumeMount(
            name='hdfs-pvc',
            mount_path='/srv/storage/'),
    ]
    pvc_claim = client.V1PersistentVolumeClaimVolumeSource(
        claim_name='hdfs-pvc')

    if gpus:
        resources = {'limits': {'nvidia.com/gpu': gpus}}
    else:
        resources = {}

    container = client.V1Container(name=container_name,
                                   image=container_image,
                                   env=env_list, command=minion_cmd,
                                   image_pull_policy=pull_policy,
                                   volume_mounts=volume_mounts,
                                   resources=resources)

    volumes = [
        client.V1Volume(name='juicer-config',
                        config_map=client.V1ConfigMapVolumeSource(
                            name='juicer-config')),
        client.V1Volume(name='hdfs-site',
                        config_map=client.V1ConfigMapVolumeSource(
                            name='hdfs-site')),
        client.V1Volume(name='hdfs-pvc',
                        persistent_volume_claim=pvc_claim),
    ]
    template.template.spec = client.V1PodSpec(
        containers=[container], restart_policy='Never', volumes=volumes)

    # And finally we can create our V1JobSpec!
    job.spec = client.V1JobSpec(ttl_seconds_after_finished=10,
                                template=template.template)
    api = client.ApiClient(configuration)
    batch_api = client.BatchV1Api(api)

    try:
        batch_api.create_namespaced_job(namespace, job, pretty=True)
    except ApiException as e:
        body = json.loads(e.body)
        if body['reason'] == 'AlreadyExists':
            pass
        else:
            print("Exception when calling BatchV1Api->: {}\n".format(e))
