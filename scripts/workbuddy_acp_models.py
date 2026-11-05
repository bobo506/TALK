"""Human-operated registration of available WorkBuddy ACP models."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote
import httpx
from bridges.workbuddy_acp import AcpError, acp_alias, list_models

def choice_payload(model):
    # 内置模型与 models.json 的 custom-local 可能同名；加后缀避免创建角色时混淆。
    display = (model.get('name') or model['modelId']) + '（内置）'
    return {'model_source':'builtin','provider_id':'managed:workbuddy','connection_ref':'native-workbuddy-acp','model_id':model['modelId'],'model_alias':acp_alias(model['modelId']),'model_display_name':display}

def register(api_base, key, models, runner_id, available=None):
    with httpx.Client(base_url=api_base.rstrip('/'), headers={'X-API-Key':key}, trust_env=False, timeout=30) as client:
        me = client.get('/api/members/me'); me.raise_for_status()
        if me.json().get('kind') != 'human': raise ValueError('human operator required')
        catalog = {m['modelId']:m for m in (available if available is not None else list_models())}
        if not models or any(mid not in catalog for mid in models): raise ValueError('model unavailable')
        path = '/api/runners/' + quote(runner_id, safe='') + '/model-choices'
        existing = client.get(path, params={'include_retired':'true'}); existing.raise_for_status()
        rows = existing.json()
        if isinstance(rows,dict): rows = rows.get('data', rows.get('items', []))
        if not isinstance(rows,list): raise ValueError('invalid choices')
        results = []
        for mid in models:
            payload = choice_payload(catalog[mid])
            match = next ( (r for r in rows if all(r.get(k)==payload[k] for k in ('model_source','provider_id','connection_ref','model_id','model_alias'))), None)
            if match:
                results.append({'status':'existing','choice_id':match.get('choice_id')})
            else:
                response = client.post(path, json=payload); response.raise_for_status(); row = response.json()
                results.append({'status':'created','choice_id':row.get('choice_id')})
        return results

def main(argv=None):
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='action',required=True)
    ls=sub.add_parser('list'); ls.add_argument('--endpoint')
    reg=sub.add_parser('register'); reg.add_argument('--api-base',required=True); reg.add_argument('--operator-key-file',required=True); reg.add_argument('--models',required=True); reg.add_argument('--runner-id',default='runner:workbuddy-embedded-cli')
    args=parser.parse_args(argv)
    try:
        if args.action == 'list': result=list_models(args.endpoint)
        else:
            key=Path(args.operator_key_file).read_text(encoding='utf-8').strip()
            if not key: raise ValueError('empty key')
            result=register(args.api_base,key,[m.strip() for m in args.models.split(',') if m.strip()],args.runner_id)
        print(json.dumps(result,ensure_ascii=False)); return 0
    except (AcpError, OSError, ValueError, httpx.HTTPError, KeyError):
        print('[workbuddy-acp] registration_or_runtime_failed',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
