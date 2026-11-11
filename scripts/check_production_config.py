"""Local structural checks only; does not contact hosting accounts."""
import json,tomllib,yaml
from pathlib import Path
root=Path(__file__).resolve().parents[1]
netlify=tomllib.loads((root/'netlify.toml').read_text(encoding='utf-8'))
render=yaml.safe_load((root/'render.yaml').read_text(encoding='utf-8'))
service=render['services'][0]
assert service['runtime']=='docker' and service['numInstances']==1 and service['autoDeployTrigger']=='off'
assert service['disk']['mountPath']=='/var/data' and service['plan']!='free'
env={e['key']:e.get('value') for e in service['envVars']}
assert env['ADVENTURE_DATA_DIR'].startswith(service['disk']['mountPath']+'/')
assert env['ADVENTURE_MAINTENANCE']=='1' and env['ADVENTURE_IMPORT_READY']=='no'
assert all('value' not in e for e in service['envVars'] if e['key'] in ('GEMINI_API_KEY','GEMINI_MODEL','ADVENTURE_ALLOWED_HOSTS','ADVENTURE_ALLOWED_ORIGINS'))
assert netlify['build']['base']=='frontend' and netlify['build']['publish']=='dist'
redirects=(root/'frontend/dist/_redirects').read_text(encoding='utf-8').splitlines()
assert redirects[0].startswith('/api/* https://') and redirects[0].endswith('/api/:splat 200!')
assert redirects[1]=='/* /index.html 200'
ignore=(root/'.dockerignore').read_text(encoding='utf-8')
assert '**/.env' in ignore and 'backend/data' in ignore and 'input' in ignore
result={'status':'PASS','toml_yaml_syntax':'PASS','proxy_api_before_spa':'PASS','single_instance_disk_path':'PASS','maintenance_bootstrap':'PASS','secrets_in_blueprint':False,'hosting_schema_validation':'NOT_RUN','linux_docker_build':'NOT_RUN'}
(root/'reports/production/config-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
