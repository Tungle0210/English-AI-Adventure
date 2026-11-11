"""Local structural checks only; does not contact hosting accounts."""
import json,tomllib,yaml
from pathlib import Path
root=Path(__file__).resolve().parents[1]
netlify=tomllib.loads((root/'netlify.toml').read_text(encoding='utf-8'))
render=yaml.safe_load((root/'render.yaml').read_text(encoding='utf-8'))
service=render['services'][0]
assert service['runtime']=='docker' and service['numInstances']==1 and service['autoDeployTrigger']=='off'
assert service['plan']=='free' and 'disk' not in service
env={e['key']:e.get('value') for e in service['envVars']}
assert env['ADVENTURE_DATA_DIR'].startswith('/tmp/')
assert env['ADVENTURE_CLOUD_ENABLE']=='yes' and env['ADVENTURE_DATABASE_BACKEND']=='postgres' and env['ADVENTURE_STORAGE_BACKEND']=='s3'
assert env['ADVENTURE_MAINTENANCE']=='1' and env['ADVENTURE_IMPORT_READY']=='no'
assert all('value' not in e for e in service['envVars'] if e['key'] in ('GEMINI_API_KEY','GEMINI_MODEL','DATABASE_URL','DATABASE_DIRECT_URL','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','S3_ENDPOINT_URL'))
assert netlify['build']['base']=='frontend' and netlify['build']['publish']=='dist'
redirects=(root/'frontend/dist/_redirects').read_text(encoding='utf-8').splitlines()
assert redirects[0].startswith('/api/* https://') and redirects[0].endswith('/api/:splat 200!')
assert redirects[1]=='/* /index.html 200'
ignore=(root/'.dockerignore').read_text(encoding='utf-8')
assert '**/.env' in ignore and 'backend/data' in ignore and 'input' in ignore
result={'status':'PASS','toml_yaml_syntax':'PASS','proxy_api_before_spa':'PASS','single_instance_neon_ephemeral_cache':'PASS','maintenance_bootstrap':'PASS','secrets_in_blueprint':False,'hosting_schema_validation':'NOT_RUN','linux_docker_build':'NOT_RUN'}
(root/'reports/neon/config-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
